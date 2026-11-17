# Case study: what broke and what I changed

Notes from building Release 1, kept because the failures taught more than the parts that
worked first time.

## 1. Quantities printed as "1E+1"

**What happened.** A test replaying a dead-lettered invoice ended in review instead of
auto-approval. The replay logic looked guilty, but the audit trail showed the real reason:
`UNPARSEABLE:line[2]`. The quantity 10 had been rendered as `1E+1`, because I formatted
quantities with `Decimal.normalize()`, which switches to scientific notation for round
numbers. The normaliser correctly refused it.

**Why it hid.** It only shows up when a quantity is a multiple of 10, so most generated
invoices were fine and earlier tests passed by luck.

**Change.** Integral quantities print as integers; a regression test covers 10, 20 and 100.
Lesson: read the audit trail before touching the code that looks responsible.

## 2. A row lock that returned stale data

**What happened.** While writing the extraction job I noticed `lock_invoice` took a
`SELECT ... FOR UPDATE` but could hand back the copy of the row already held in the
session's identity map. A duplicate job delivery could then act on an out-of-date status
while holding the lock.

**Change.** The locked read now uses `populate_existing`, so it always reflects the
database. The job also treats "someone else finished first" as a clean skip. A test runs
two workers on the same job and checks one completes, one skips, and the model result is
stored once.

## 3. A metric that did not count the worst case

**What happened.** The first evaluation counted *false approvals*: bad invoices that were
auto-approved. Reading the noisy-run results, I realised a clean invoice misread by the model
and then auto-approved would post wrong data, and that metric would not count it.

**Change.** A second metric, misread auto-approvals, counts auto-approved invoices with any
wrongly read field. CI gates both at zero.

## 4. The database caught a generator bug

**What happened.** Seeding the "no PO" scenario failed with a foreign-key violation: the
generator still produced goods receipts for a PO that did not exist.

**Change.** Receipts are only seeded against an existing PO. The constraint did its job;
the fix was in the test data, not the schema.

## 5. An SDK major version changed under me

**What happened.** The MCP server failed to import: the installed MCP Python SDK was 2.x,
where `FastMCP` became `MCPServer` and annotation fields became snake_case.

**Change.** I checked the official migration guide and the installed package's signatures
instead of guessing, moved to the 2.x API, and pinned `mcp>=2.3,<3`.

## 6. Two tests that tested my assumptions, not the code

- A tamper-detection test "changed" the first case's label to `CLEAN`, but it already was
  `CLEAN`, so nothing changed.
- A test expected Indian and Western number grouping to differ for a five-digit total; they
  only differ from six digits upward.

Both were fixed to assert something real. Lesson: when a test fails, check the test as hard
as the code.

## 7. Deployment cost shaped the architecture

Render has no free plan for background workers. Rather than pay for two, the worker
container runs the outbox dispatcher alongside Celery. The trade-off, written into
`render.yaml`: if the dispatcher process dies, nothing restarts it until the container
restarts. A Celery worker also polls Redis constantly, which can exhaust a per-command free
tier, so the deploy guide calls that out.

## Still open

- No interviews with accounts-payable practitioners yet (see `discovery-brief.md`).
- No real-model evaluation recorded yet; every published number so far comes from
  simulated extraction and is labelled that way.

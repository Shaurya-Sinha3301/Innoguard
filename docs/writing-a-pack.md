# Writing a pack

A pack teaches InvoiceGuard one document-to-decision workflow. The core already does the rest:
extraction with evidence, the review queue, version-bound approvals, posting, the audit
trail, agent access and metrics. The two packs that exist are the worked examples:
`packs/invoices/` and `packs/expenses/`.

## What a pack is made of

```text
packs/<name>/
  manifest.yaml     what a reviewer sees, and the numbers the rules use
  __init__.py       the Pack object (implements packs/base.py: Pack)
  schema.py         what the model must return, and the prompts
  normalizer.py     typed values from the model's strings
  rules.py          the checks: pure Python, no database
  models.py         plain domain types
  repo.py           loaders that turn database rows into domain types
  generator.py      synthetic cases with ground truth, and their documents
  fakes.py          a perfect extractor and a noisy one, for tests and gates
  evaluation.py     the locked set and the gates
  demo_data.py      sample data for a running system
```

## The rules for the rules

1. **The model reads; code decides.** `normalize` types strings and refuses ambiguity (a date
   that could be read two ways, a number with an unclear separator). `rules.py` produces named
   reasons. Nothing the model says is an instruction.
2. **Every finding is a named reason**, declared in the manifest with a plain-language
   explanation a reviewer can check. A hard finding blocks auto-approval at any confidence.
3. **Use an independent record.** The expenses pack checks the receipt against the card
   statement; invoices check against the PO and receipts. A second source is what catches a
   value the model misread but quoted truthfully.
4. **Three signals, never one score**: extraction confidence, match quality, policy
   eligibility. Reuse `domain/decision.decide`.
5. **Rules take no database.** Loaders in `repo.py` build the inputs; `rules.py` gets plain
   values, so it can be tested with generated cases and run in the evaluation without a
   database.

## The manifest

`manifest.yaml` is validated at start-up (`packs/base.py: Manifest`). It carries the pack's id
and name, the fields, every reason (code, label, explanation, `hard` or `soft`), the
thresholds and tolerances, the queue and case-page layout, and the wording the UI uses
(`case_noun`, `counterparty`, `how_it_works`). It contains no logic.

Keep it honest with tests (see `tests/unit/test_packs.py`): every reason code the rules can
emit is declared; every number in the manifest equals the one the code uses; reason texts
that quote a number quote the right one.

## The Pack object

Implement the methods in `packs/base.py`: `normalize`, `apply_extracted`, `reconcile`,
`context`, `lookup`, plus `extraction_model`, the two prompts and `lookup_names`. Register it
in `packs/registry.py`. `reconcile` returns a `PackReconciliation` (a decision and the facts to
record on the audit event).

The core reaches a pack only through this interface. A test
(`test_the_core_never_names_a_pack`) fails if shared workflow, extraction or job code contains
a pack's name.

## Data

A case is one row in `cases` with `pack_id`. The shared columns hold what every pack has: a
reference, the counterparty, the currency and the amount (approvals and posting are bound to
the amount). Everything else goes in `data` (jsonb). Reference tables the pack needs (an
employee list, a card statement) get their own Alembic migration, and a test applies every
migration and fails on any drift from the models.

## Evaluation (required)

A pack is not finished until it has:

- a **generator** of labelled cases, with the outcome a correct system should reach for each;
- at least **three document layouts**, one **held out** from development;
- a **locked set** pinned by a hash, so it cannot be tuned against quietly;
- **oracle** (perfect reading) and **noisy** (seeded errors a real model could make) runs;
- the shared **gates** in `eval/gates.json`: no bad case auto-approved, and no case
  auto-approved with a misread field.

Oracle and noisy runs test the controls. They are not model accuracy results; say so wherever
you report them.

## Checklist

- [ ] manifest validates; reasons, thresholds and wording written for a reviewer
- [ ] `rules.py` is pure, with a unit test per reason
- [ ] normaliser refuses ambiguity, with tests
- [ ] pack registered; `GET /packs/<id>` returns the manifest
- [ ] migration for any reference tables; schema-drift test passes
- [ ] generator, three layouts, locked set, oracle and noisy gates passing in CI
- [ ] an integration test runs a document through the extraction job and posts it
- [ ] the UI needs only the manifest and a `context` for the case page
- [ ] the core-never-names-a-pack test still passes

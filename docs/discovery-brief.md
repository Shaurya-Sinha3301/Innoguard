# Discovery brief

**Status: interviews not yet conducted.** The design so far is based on public material
about accounts payable and an outside design review. This page holds the questions and will
record what practitioners said and which design changes followed.

## Who to talk to

Two or three people who handle supplier invoices: AP clerks, AP managers or
finance-operations staff. Ask about their actual exception workflow; do not pitch the UI.

## Questions

1. Which mismatches take the most time, and which are accepted automatically under policy?
2. How are partial deliveries, credit notes, returns and price variances handled?
3. What evidence does a reviewer need before approving an exception?
4. Which cases must always go to a human, whatever the system's confidence?
5. What does your system use as an invoice's unique identity?
6. What happens when an invoice, PO or receipt changes after it was reviewed?
7. Which audit fields are mandatory when someone overrides an invoice?
8. How do you measure review time and the cost of a wrong approval?

## What I will record

| Date | Role | Key points | Design change it caused |
| --- | --- | --- | --- |
| | | | |

## Assumptions to test

- A 2% price tolerance and 0% quantity tolerance are reasonable defaults.
- Reviewers want the quoted evidence next to each field more than a confidence number.
- A single value limit (10,000) is enough as a risk tier for Release 1.

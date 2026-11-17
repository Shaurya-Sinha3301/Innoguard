## What and why

## How I checked it

- [ ] `ruff check .` and `pytest` pass locally
- [ ] Evaluation gates pass (`--extractor oracle --gate`, `--extractor noisy --gate`)
- [ ] `npm run build` passes (if `web/` changed)
- [ ] New migration included and applies cleanly (if models changed)

## Risk

What could this break, and how would we notice?

## Docs

- [ ] README, design or runbook updated if behaviour changed

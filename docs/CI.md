# CI Baseline

This repository uses a minimal GitHub Actions CI pipeline in `.github/workflows/ci.yml`.

## Jobs

- `verify-all`
  - Sets up Python 3.13
  - Installs API + script dependencies
  - Runs `python scripts/verify_all.py`

- `ui-tests`
  - Sets up Node.js 20
  - Runs `npm test -- --run` in `apps/ui`
  - Runs Playwright E2E in `apps/ui`

## Local Reproduction

Run the same checks locally:

```bash
python scripts/verify_all.py
npm --prefix apps/ui ci
npm --prefix apps/ui test -- --run
npm --prefix apps/ui run test:e2e
```

Notes:

- `scripts/verify_all.py` now includes schema validation and security audit before DB/tests.
- E2E tests in CI install Playwright browsers automatically.

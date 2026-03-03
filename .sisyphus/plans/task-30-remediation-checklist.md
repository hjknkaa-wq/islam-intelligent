# Task 30 Remediation Checklist (Realtime)

## Milestone 1 - Discovery and Reproduction
- [x] Parse roadmap/status/remediation docs and identify executable scope.
- [x] Run baseline `python scripts/verify_all.py` and confirm baseline health.
- [x] Run required UI commands and reproduce failure in full e2e run.

## Milestone 2 - Bug Fix and Targeted Validation
- [x] Diagnose WebKit timeout root cause (`Ask` button remained disabled).
- [x] Patch UI form hydration/input readiness in `apps/ui/src/components/QueryForm.tsx`.
- [x] Run targeted validation: WebKit citations e2e spec passes.

## Milestone 3 - Final Mandatory Verification
- [x] Run `python scripts/verify_all.py` and save evidence output.
- [x] Run `npm --prefix apps/ui ci` and save evidence output.
- [x] Run `npm --prefix apps/ui test -- --run` and save evidence output.
- [x] Run `npm --prefix apps/ui run test:e2e` and save evidence output.

## Milestone 4 - Closeout
- [x] Update checklist and status docs with final results.
- [x] Create atomic milestone commits with clear messages.
- [x] Produce final change summary, test results, and residual risks.

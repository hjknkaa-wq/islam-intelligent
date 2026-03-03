# Repository Cleanup Evidence Log (2026-03-03)

This log records candidate checks done before any deletion decision.

## Candidate checks

### Candidate: `AGENT.md` (tracked)

Search pattern: `AGENT\.md`

Result files with matches:
- `AGENTS.md`
- `PROPOSAL.md` (moved to `docs/archive/PROPOSAL.md`)

Decision: **not deleted** (was still referenced at cleanup time).

---

### Candidate: `faithful_rag_repo/` (untracked local clone)

Search patterns:
- `faithful_rag_repo`
- `faithful`

Scoped repo-reference checks (outside candidate folder):
- Path `apps/`: no matches
- Path `packages/`: no matches
- Path `scripts/`: no matches
- Path `docs/`: no matches
- Path `data/`: no matches
- Path `.github/`: no matches

AST checks:
- TypeScript literal `'faithful_rag_repo'`: no matches
- Python literal `'faithful_rag_repo'`: no matches

Decision: no in-repo references found; kept as local-only clone and added to `.gitignore`.

---

### Candidate: `ground_cite_repo/` (untracked local clone)

Search patterns:
- `ground_cite_repo`
- `ground[_-]?cite`
- `GroundCite`

Scoped repo-reference checks (outside candidate folder):
- Path `apps/`: no matches
- Path `packages/`: no matches
- Path `scripts/`: no matches
- Path `docs/`: no matches
- Path `data/`: no matches
- Path `.github/`: no matches

AST checks:
- TypeScript literal `'ground_cite_repo'`: no matches
- Python literal `'ground_cite_repo'`: no matches

Decision: no in-repo references found; kept as local-only clone and added to `.gitignore`.

---

## Deletions performed

- **Tracked file deletions:** none
- **Uncertain/stale planning docs:** moved to `docs/archive/` instead of deleted

Moved paths:
- `CODEBASE_ASSESSMENT.md` -> `docs/archive/CODEBASE_ASSESSMENT.md`
- `PROJECT_STATUS.md` -> `docs/archive/PROJECT_STATUS.md`
- `PROPOSAL.md` -> `docs/archive/PROPOSAL.md`
- `REMEDIATION_PLAN.md` -> `docs/archive/REMEDIATION_PLAN.md`
- `MILESTONE_1.md` -> `docs/archive/MILESTONE_1.md`

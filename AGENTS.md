# ISLAM INTELLIGENT — AGENT KNOWLEDGE BASE

**Project:** Palantir-like Islamic Knowledge Intelligence Platform  
**Focus:** Accuracy-first, provenance-backed, hallucination-free  
**Generated:** 2026-03-02

---

## OVERVIEW

Build deterministic pipelines for Islamic knowledge (Quran, Hadith, Tafsir, Fiqh, Sirah). No LLM "magic" — every claim tied to primary source with explicit citation.

---

## STRUCTURE

```
islam-intelligent/
├── AGENTS.md              # This file (project rules)
├── AGENT.md               # Legacy rules (being migrated)
├── opencode.jsonc         # OpenCode orchestrator config
├── .opencode/             # OMO plugin + profiles
│   ├── oh-my-opencode.jsonc   # Agent configurations
│   ├── profiles/              # Runtime profiles
│   └── package.json
└── .sisyphus/             # Task tracking storage
    └── tasks/
```

---

## WHERE TO LOOK

| Need | Location | Notes |
|------|----------|-------|
| Orchestrator config | `opencode.jsonc` | Model selection, global settings |
| Agent definitions | `.opencode/oh-my-opencode.jsonc` | Sisyphus, Prometheus, Hephaestus, Oracle, etc. |
| Runtime profiles | `.opencode/profiles/` | balanced, safe, max-autonomy |
| Task storage | `.sisyphus/tasks/` | Cross-session persistence |

---

## CONVENTIONS

### Citation Requirements (HARD RULES)
- **Al-Quran:** Surah:Ayat + Arabic snippet + translation source
- **Hadith:** Collection + number + chapter + grading + sanad (if available)
- **Tafsir/Fiqh/Sirah:** Work + author + volume/page or canonical section ID
- **Engineering claims:** File paths + symbols + line ranges

### Evidence Format
```
Claim → Source ID + Location → Provenance chain
NO claim without explicit pointer to source document
```

### Engineering Standards
- ETL pipelines: idempotent + checkpointed
- KG edges: store provenance + allow conflicting sources
- RAG: log retrieved evidence + final citations
- Dashboard metrics: query provenance trail

---

## ANTI-PATTERNS (NEVER DO)

| Pattern | Why Forbidden | Correct Approach |
|---------|---------------|------------------|
| Hallucinate sources | Violates accuracy-first principle | Abstain + request retrieval |
| Issue fatwa without primary citation | Religious liability | Require surah:ayah or hadith ref + uncertainty label |
| Drop provenance fields | Breaks audit trail | Every transform preserves source pointers |
| "LLM magic" without verification | Non-deterministic | Schema + validation + spot checks |
| Trust external web sources | Unverified data | Treat as untrusted unless curated |
| Hardcode API keys | Security risk | Use environment variables |

---

## UNIQUE STYLES

### Custom OMO Categories
| Category | Purpose | Model |
|----------|---------|-------|
| `islam-etl` | Ingestion + normalization (Quran/Hadith/Tafsir/Fiqh) | kimi-for-coding/k2p5 |
| `islam-kg` | Ontology + Knowledge Graph modeling | openai/gpt-5.2 |
| `islam-rag` | Multi-hop RAG + grounded generation | openai/gpt-5.3-codex |
| `islam-eval` | Evaluation harness + hallucination checks | openai/gpt-5.2 |
| `islam-security` | Threat modeling + audit logs | openai/gpt-5.2 |

### Agent Hierarchy
- **Sisyphus:** Main orchestrator (kimi-for-coding/k2p5)
- **Prometheus:** Planner — strict milestones + acceptance criteria
- **Hephaestus:** Heavy coding/refactor (gpt-5.3-codex)
- **Oracle:** Read-only architecture consultant
- **Momus:** QA — edge cases, citation gaps
- **Librarian:** Research + docs
- **Explore:** Cheap codebase search

### Key Agent Configs
```jsonc
// Sisyphus prompt_append
"PROJECT RULES:\n- Plan-first for any multi-file change.\n- Never assert Islamic facts without explicit primary citations.\n- If evidence is missing: say 'insufficient sources' and request retrieval/ingestion.\n- Always preserve provenance for every dataset transformation."

// Prometheus prompt_append  
"PLANNING RULES:\n1) Break work into milestones: ingestion → normalization → KG → RAG → UI → eval → hardening.\n2) Every milestone must define: schema, provenance, tests, and rollback strategy.\n3) For accuracy: require 'evidence-first' flows (retrieve → verify → generate)."
```

---

## COMMANDS

No project-specific build/test commands (configuration-only repository).

System commands available via agent permissions:
```bash
# Git (allowed)
git status, git diff, git add, git commit, git log, git blame

# Search (allowed)
rg, fd, ls, cat

# Runtime (allowed)
python, node, bun, npm, pnpm

# Ask required
docker, curl, wget, sed

# Denied
rm, sudo
```

---

## NOTES

- **Runtime fallback enabled:** Auto-switch to backup models on API errors
- **Hashline edit enabled:** Prevents stale-line edits
- **Git hygiene:** Commit footer + Co-authored-by enabled
- **Concurrency:** kimi-for-coding=6, openai/gpt-5.3-codex=1, openai/gpt-5.2=2
- **Background tasks:** Default 4 concurrent, 180s stale timeout
- **Notification:** Force-enabled for all agents

### Provenance Chain
Every transformation must maintain:
1. Source document ID
2. Location within document (ayah number, page, etc.)
3. Transformation applied
4. Timestamp + agent
5. Checksum/hash for integrity

### When Evidence Missing
```
User: "What does Islam say about X?"
Assistant: "Insufficient sources. I have no citations for this topic. 
To answer accurately, I need:
- Quran references (surah:ayah)
- Hadith collection + number
- Or scholarly sources with full bibliographic data

Shall I search for these sources first?"
```

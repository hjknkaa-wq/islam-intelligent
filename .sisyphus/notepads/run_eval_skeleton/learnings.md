Run Eval Skeleton - Learnings
- Implemented a minimal CLI skeleton for eval runs.
- Uses argparse with --suite, --output, --assert to control behavior.
- Attempts to load eval/cases/{suite}.yaml via PyYAML if available; fallback parser otherwise.
- Generates a JSON report with a timestamp when --output is provided.
- Basic assertion path guarded by --assert (deterministic checks).
- Path to YAML is resolved relative to repo root.

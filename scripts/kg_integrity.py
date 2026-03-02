"""KG integrity checks.

Checks:
- Every edge has >= 1 evidence span
- Every evidence_span_id referenced by an edge exists in fixtures

This script intentionally parses fixture YAML as JSON (YAML is a superset of JSON)
to avoid adding external dependencies for this scaffold.
"""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
EDGES_FIXTURE = ROOT / "data" / "fixtures" / "kg_edges.yaml"


def _load_json_yaml(path: Path) -> object:
    return cast(object, json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    if not EDGES_FIXTURE.exists():
        print(f"missing fixture: {EDGES_FIXTURE}", file=sys.stderr)
        return 2

    data = _load_json_yaml(EDGES_FIXTURE)
    if not isinstance(data, dict):
        print("kg_edges.yaml must be a JSON object", file=sys.stderr)
        return 2

    evidence_spans = data.get("evidence_spans")
    edges = data.get("edges")

    if not isinstance(evidence_spans, list):
        print("kg_edges.yaml missing 'evidence_spans' list", file=sys.stderr)
        return 2
    if not isinstance(edges, list):
        print("kg_edges.yaml missing 'edges' list", file=sys.stderr)
        return 2

    evidence_span_ids: set[str] = set()
    for es in evidence_spans:
        if not isinstance(es, dict):
            continue
        es_id = es.get("evidence_span_id")
        if isinstance(es_id, str) and es_id.strip():
            evidence_span_ids.add(es_id)

    violations: list[str] = []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            violations.append(f"edge[{i}] is not an object")
            continue

        edge_id = edge.get("edge_id")
        label = edge_id if isinstance(edge_id, str) and edge_id else f"edge[{i}]"

        es_ids = edge.get("evidence_span_ids")
        if not isinstance(es_ids, list) or len(es_ids) == 0:
            violations.append(f"{label}: missing/empty evidence_span_ids")
            continue

        missing = [es_id for es_id in es_ids if es_id not in evidence_span_ids]
        if missing:
            violations.append(f"{label}: unknown evidence_span_ids: {missing}")

    if violations:
        print("KG integrity violations:", file=sys.stderr)
        for v in violations:
            print(f"- {v}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

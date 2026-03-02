#!/usr/bin/env python3
"""Verify provenance integrity (no broken links, no orphans).

Checks (ORM-based):
- All `text_unit.source_id` values reference an existing `source_document.source_id`
- All `evidence_span.text_unit_id` values reference an existing `text_unit.text_unit_id`
- All `kg_edge_evidence.evidence_span_id` values reference an existing `evidence_span.evidence_span_id`
- Every `kg_edge` has >= 1 `kg_edge_evidence` row
- No orphan KG entities (every `kg_entity` participates in at least one `kg_edge`)

Exit codes:
- 0: no violations
- 1: violations found
- 2: configuration / connection / schema error
"""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

from sqlalchemy import create_engine, exists, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

# Required project models
from islam_intelligent.db import engine as engine_module
from islam_intelligent.domain.models import SourceDocument, TextUnit
from islam_intelligent.kg.models import EvidenceSpan, KgEdge, KgEdgeEvidence, KgEntity
from islam_intelligent.provenance import models as prov_models  # noqa: F401

_ = prov_models


def _resolve_db_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url
    env = (os.getenv("DATABASE_URL") or "").strip()
    if env:
        return env
    return engine_module.DATABASE_URL


def _make_engine(db_url: str) -> Engine:
    # Use the project's default engine when possible (SQLite in-memory scaffold).
    if db_url == engine_module.DATABASE_URL:
        return engine_module.engine
    return create_engine(db_url, future=True)


def _require_tables(engine: Engine, required: list[str]) -> tuple[bool, list[str]]:
    inspector = inspect(engine)
    missing = [t for t in required if not inspector.has_table(t)]
    if missing:
        return False, missing
    return True, []


def _truncate(items: list[str], max_items: int) -> tuple[list[str], int]:
    if max_items < 1:
        return [], len(items)
    if len(items) <= max_items:
        return items, 0
    return items[:max_items], len(items) - max_items


def _broken_text_unit_sources(db: Session) -> list[str]:
    stmt = (
        select(TextUnit.text_unit_id, TextUnit.source_id)
        .outerjoin(SourceDocument, TextUnit.source_id == SourceDocument.source_id)
        .where(SourceDocument.source_id.is_(None))
    )
    rows = cast(list[tuple[str, str]], list(db.execute(stmt).tuples().all()))
    return [
        f"text_unit_id={text_unit_id} missing source_document.source_id={source_id}"
        for text_unit_id, source_id in rows
    ]


def _broken_evidence_span_text_units(db: Session) -> list[str]:
    stmt = (
        select(EvidenceSpan.evidence_span_id, EvidenceSpan.text_unit_id)
        .outerjoin(TextUnit, EvidenceSpan.text_unit_id == TextUnit.text_unit_id)
        .where(TextUnit.text_unit_id.is_(None))
    )
    rows = cast(list[tuple[str, str]], list(db.execute(stmt).tuples().all()))
    return [
        f"evidence_span_id={evidence_span_id} missing text_unit.text_unit_id={text_unit_id}"
        for evidence_span_id, text_unit_id in rows
    ]


def _broken_kg_edge_evidence_spans(db: Session) -> list[str]:
    stmt = (
        select(KgEdgeEvidence.edge_id, KgEdgeEvidence.evidence_span_id)
        .outerjoin(
            EvidenceSpan,
            KgEdgeEvidence.evidence_span_id == EvidenceSpan.evidence_span_id,
        )
        .where(EvidenceSpan.evidence_span_id.is_(None))
    )
    rows = cast(list[tuple[str, str]], list(db.execute(stmt).tuples().all()))
    return [
        f"kg_edge_evidence edge_id={edge_id} missing evidence_span.evidence_span_id={evidence_span_id}"
        for edge_id, evidence_span_id in rows
    ]


def _broken_kg_edge_evidence_edges(db: Session) -> list[str]:
    stmt = (
        select(KgEdgeEvidence.edge_id, KgEdgeEvidence.evidence_span_id)
        .outerjoin(KgEdge, KgEdgeEvidence.edge_id == KgEdge.edge_id)
        .where(KgEdge.edge_id.is_(None))
    )
    rows = cast(list[tuple[str, str]], list(db.execute(stmt).tuples().all()))
    return [
        f"kg_edge_evidence evidence_span_id={evidence_span_id} missing kg_edge.edge_id={edge_id}"
        for edge_id, evidence_span_id in rows
    ]


def _edges_missing_evidence(db: Session) -> list[str]:
    stmt = (
        select(KgEdge.edge_id)
        .outerjoin(KgEdgeEvidence, KgEdge.edge_id == KgEdgeEvidence.edge_id)
        .where(KgEdgeEvidence.edge_id.is_(None))
    )
    edge_ids = cast(list[str], db.execute(stmt).scalars().all())
    return [f"kg_edge.edge_id={edge_id} has no evidence spans" for edge_id in edge_ids]


def _orphan_kg_entities(db: Session) -> list[str]:
    edge_ref = (
        select(1)
        .select_from(KgEdge)
        .where(
            or_(
                KgEdge.subject_entity_id == KgEntity.entity_id,
                KgEdge.object_entity_id == KgEntity.entity_id,
            )
        )
    )
    stmt = select(
        KgEntity.entity_id, KgEntity.entity_type, KgEntity.canonical_name
    ).where(~exists(edge_ref))
    rows = cast(list[tuple[str, str, str]], list(db.execute(stmt).tuples().all()))
    return [
        f"kg_entity.entity_id={entity_id} (type={entity_type}, name={canonical_name}) has no kg_edge"
        for entity_id, entity_type, canonical_name in rows
    ]


def _print_check(
    *,
    name: str,
    violations: list[str],
    max_examples: int,
    verbose: bool,
) -> bool:
    if not violations:
        if verbose:
            print(f"[PASS] {name}")
        return True

    examples, remaining = _truncate(violations, max_examples)
    print(f"[FAIL] {name} ({len(violations)} violation(s))", file=sys.stderr)
    for v in examples:
        print(f"- {v}", file=sys.stderr)
    if remaining:
        print(f"(+{remaining} more)", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify provenance integrity (broken links + orphan entities)",
    )
    parser.add_argument(
        "--check",
        required=True,
        choices=["no_broken_links"],
        help="Verification suite to run",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Optional override for DATABASE_URL",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=50,
        help="Max violations to print per check (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print PASS lines as well",
    )
    args = parser.parse_args()

    db_url = _resolve_db_url(cast(str | None, args.db_url))
    engine = _make_engine(db_url)

    try:
        with engine.connect() as conn:
            conn.execute(select(1))
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        return 2

    ok, missing = _require_tables(
        engine,
        required=[
            "source_document",
            "text_unit",
            "evidence_span",
            "kg_entity",
            "kg_edge",
            "kg_edge_evidence",
        ],
    )
    if not ok:
        print(
            "ERROR: Missing required table(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    max_examples = cast(int, args.max_examples)
    verbose = cast(bool, args.verbose)
    db = SessionLocal()
    try:
        violations_found = False

        if not _print_check(
            name="text_unit.source_id -> source_document.source_id",
            violations=_broken_text_unit_sources(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if not _print_check(
            name="evidence_span.text_unit_id -> text_unit.text_unit_id",
            violations=_broken_evidence_span_text_units(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if not _print_check(
            name="kg_edge_evidence.evidence_span_id -> evidence_span.evidence_span_id",
            violations=_broken_kg_edge_evidence_spans(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if not _print_check(
            name="kg_edge_evidence.edge_id -> kg_edge.edge_id",
            violations=_broken_kg_edge_evidence_edges(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if not _print_check(
            name="kg_edge has >= 1 evidence span",
            violations=_edges_missing_evidence(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if not _print_check(
            name="kg_entity participates in at least one kg_edge",
            violations=_orphan_kg_entities(db),
            max_examples=max_examples,
            verbose=verbose,
        ):
            violations_found = True

        if violations_found:
            return 1

        print("[OK] Provenance integrity verified: no broken links, no orphan entities")
        return 0
    except Exception as e:
        print(f"ERROR: Verification failed: {e}", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

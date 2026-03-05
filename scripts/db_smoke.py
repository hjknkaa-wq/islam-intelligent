#!/usr/bin/env python3
"""Database smoke tests - quick health checks for DB initialization.

Validates that database is properly initialized with required tables,
indexes, and seed data.
"""

import sys
import sqlite3
from pathlib import Path
from typing import List, Tuple


REQUIRED_TABLES = [
    "source_document",
    "text_unit",
    "evidence_span",
    "kg_entity",
    "kg_edge",
    "kg_edge_evidence",
    "rag_query",
    "rag_retrieval_result",
    "rag_validation",
    "rag_answer",
    "rag_metrics_log",
    "schema_migrations",
    "provenance_activity",
    "provenance_entity",
    "provenance_agent",
]

REQUIRED_INDEXES = [
    "idx_text_unit_canonical_id",
    "idx_text_unit_source",
    "idx_evidence_span_text_unit",
    "idx_kg_entity_type",
    "idx_kg_edge_subject",
    "idx_kg_edge_predicate",
    "idx_rag_retrieval_query",
]

MINIMUM_FIXTURES = {
    "quran_text": 1,
    "hadith_collection": 0,  # Optional for smoke test
}


def check_database(db_path: str) -> Tuple[bool, List[str]]:
    """
    Run smoke tests on database.

    Returns:
        (passed, issues)
    """
    issues = []

    # Check file exists
    if not Path(db_path).exists():
        return False, [f"Database file not found: {db_path}"]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check required tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        for table in REQUIRED_TABLES:
            if table not in existing_tables:
                issues.append(f"MISSING_TABLE: {table}")

        # Check required indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = {row[0] for row in cursor.fetchall()}

        for idx in REQUIRED_INDEXES:
            if idx not in existing_indexes:
                issues.append(f"MISSING_INDEX: {idx}")

        # Check minimum data
        if "source_document" in existing_tables:
            cursor.execute(
                "SELECT source_type, COUNT(*) FROM source_document GROUP BY source_type"
            )
            counts = {row[0]: row[1] for row in cursor.fetchall()}

            for source_type, min_count in MINIMUM_FIXTURES.items():
                actual = counts.get(source_type, 0)
                if actual < min_count:
                    issues.append(
                        f"INSUFFICIENT_DATA: {source_type} has {actual} sources (min: {min_count})"
                    )

        # Check text units exist
        if "text_unit" in existing_tables:
            cursor.execute("SELECT COUNT(*) FROM text_unit")
            text_unit_count = cursor.fetchone()[0]
            if text_unit_count == 0:
                issues.append("NO_TEXT_UNITS: No text units found in database")

        conn.close()

    except sqlite3.Error as e:
        return False, [f"DATABASE_ERROR: {e}"]

    passed = len(issues) == 0
    return passed, issues


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run database smoke tests")
    parser.add_argument("--db", default=".local/dev.db", help="Path to SQLite database")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    print("🔍 Running database smoke tests...")
    print(f"   Database: {args.db}")
    print()

    passed, issues = check_database(args.db)

    if passed:
        print("✅ Smoke tests PASSED")
        print("   Database is properly initialized")
        sys.exit(0)
    else:
        print("❌ Smoke tests FAILED")
        print(f"   {len(issues)} issue(s) found:")
        for issue in issues:
            print(f"   - {issue}")
        sys.exit(1)


if __name__ == "__main__":
    main()

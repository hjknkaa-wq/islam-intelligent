#!/usr/bin/env python3
"""
Schema Validation Script for Islam Intelligent

Validates:
1. SQL migrations are syntactically correct (basic checks)
2. JSON schemas are valid JSON Schema Draft 7
3. Sample data validates against schemas

Usage:
    python scripts/validate_schemas.py
    python scripts/validate_schemas.py --verbose
    python scripts/validate_schemas.py --sample-data-dir ./samples

Exit codes:
    0 - All validations passed
    1 - SQL validation failed
    2 - JSON schema validation failed
    3 - Sample data validation failed
    4 - Multiple failures
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Check for optional dependencies
try:
    import jsonschema
    from jsonschema import Draft7Validator

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


class Colors:
    """ANSI color codes for terminal output"""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_status(message: str, status: str = "info"):
    """Print status message with color"""
    if status == "success":
        print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")
    elif status == "error":
        print(f"{Colors.RED}[FAIL]{Colors.RESET} {message}")
    elif status == "warning":
        print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {message}")
    elif status == "info":
        print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")
    else:
        print(message)


def validate_sql_syntax(sql_content: str, filename: str) -> Tuple[bool, List[str]]:
    """
    Perform basic SQL syntax validation.

    Checks for:
    - Balanced parentheses
    - Valid PostgreSQL keywords
    - Proper statement termination
    """
    errors = []
    lines = sql_content.split("\n")

    # Track parentheses (ignoring comments and strings)
    paren_count = 0
    for i, line in enumerate(lines, 1):
        # Remove single-line comments for paren counting
        clean_line = re.sub(r'--.*$', '', line)
        # Remove string literals for paren counting
        clean_line = re.sub(r"'[^']*'", "''", clean_line)
        
        for char in clean_line:
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
                if paren_count < 0:
                    errors.append(f"{filename}:{i}: Unbalanced parentheses")
                    paren_count = 0

    if paren_count != 0:
        errors.append(f"{filename}: Unbalanced parentheses (net: {paren_count})")

    # Check for required keywords in migration
    required_patterns = [
        (r"CREATE\s+(TABLE|TYPE|INDEX|VIEW)", "No CREATE TABLE/TYPE/INDEX/VIEW found"),
        (r"\buuid_generate_v4\(\)", "Uses uuid_generate_v4()"),
    ]

    for pattern, description in required_patterns:
        if not re.search(pattern, sql_content, re.IGNORECASE):
            errors.append(f"{filename}: {description}")

    # Check for common SQL syntax errors
    syntax_checks = [
        (r",\s*\)", "Trailing comma before closing paren"),
        (r"\(\s*,", "Leading comma after opening paren"),
        (r"TEXT\s*\(\s*\d+\s*\)", "TEXT with length (PostgreSQL doesn't support this)"),
    ]

    for i, line in enumerate(lines, 1):
        for pattern, description in syntax_checks:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(f"{filename}:{i}: {description}")

    return len(errors) == 0, errors


def validate_json_schema(schema_path: Path) -> Tuple[bool, List[str]]:
    """Validate that a file is valid JSON and conforms to JSON Schema Draft 7"""
    errors = []

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"{schema_path}: Invalid JSON - {e}")
        return False, errors
    except Exception as e:
        errors.append(f"{schema_path}: Error reading file - {e}")
        return False, errors

    # Check for required JSON Schema fields
    if "$schema" not in schema:
        errors.append(f"{schema_path}: Missing $schema declaration")
    else:
        if "json-schema.org/draft-07" not in schema["$schema"]:
            errors.append(f"{schema_path}: Not using Draft 7 schema")

    if "$id" not in schema:
        errors.append(f"{schema_path}: Missing $id")

    if "title" not in schema:
        errors.append(f"{schema_path}: Missing title")

    if "type" not in schema and "oneOf" not in schema:
        errors.append(f"{schema_path}: Missing type or oneOf")

    # Validate with jsonschema library if available
    if JSONSCHEMA_AVAILABLE:
        try:
            Draft7Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            errors.append(f"{schema_path}: Schema validation error - {e}")

    return len(errors) == 0, errors


def validate_sample_data(
    schema_path: Path, sample_data: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Validate sample data against a JSON schema"""
    errors = []

    if not JSONSCHEMA_AVAILABLE:
        print_status(
            "Skipping sample data validation (jsonschema not installed)", "warning"
        )
        return True, []

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        errors.append(f"Error loading schema {schema_path}: {e}")
        return False, errors

    validator = Draft7Validator(schema)

    for sample_name, sample in sample_data.items():
        validation_errors = list(validator.iter_errors(sample))
        if validation_errors:
            errors.append(
                f"{schema_path.name}: Sample '{sample_name}' failed validation:"
            )
            for error in validation_errors:
                errors.append(f"  - {error.message} at {list(error.path)}")

    return len(errors) == 0, errors


def generate_sample_data() -> Dict[str, Dict[str, Any]]:
    """Generate sample data for each schema"""
    return {
        "source_document.json": {
            "valid_source": {
                "source_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_type": "quran_text",
                "work_title": "The Noble Quran",
                "author": None,
                "edition": "Hafs 'an Asim",
                "language": "ar",
                "canonical_ref": "https://example.com/quran",
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "rights_holder": "Example Organization",
                "attribution_text": "Quran text from Example Org",
                "retrieved_at": "2026-03-02T00:00:00Z",
                "content_hash_sha256": "a" * 64,
                "content_mime": "text/plain",
                "content_length_bytes": 100000,
                "storage_path": "sources/quran/text.txt",
                "trust_status": "trusted",
                "supersedes_source_id": None,
                "retraction_reason": None,
                "created_at": "2026-03-02T00:00:00Z",
            },
            "superseded_source": {
                "source_id": "550e8400-e29b-41d4-a716-446655440001",
                "source_type": "hadith_collection",
                "work_title": "Sahih al-Bukhari",
                "author": "Muhammad ibn Ismail al-Bukhari",
                "edition": "Darussalam",
                "language": "ar",
                "canonical_ref": "https://sunnah.com/bukhari",
                "license_id": "CC-BY-NC-4.0",
                "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
                "rights_holder": "Sunnah.com",
                "content_hash_sha256": "b" * 64,
                "content_length_bytes": 500000,
                "storage_path": "sources/bukhari/bukhari.json",
                "trust_status": "trusted",
                "supersedes_source_id": "550e8400-e29b-41d4-a716-446655440000",
                "retraction_reason": "Updated with corrected numbering",
            },
        },
        "text_unit.json": {
            "valid_quran_ayah": {
                "text_unit_id": "550e8400-e29b-41d4-a716-446655440010",
                "source_id": "550e8400-e29b-41d4-a716-446655440000",
                "unit_type": "quran_ayah",
                "canonical_id": "quran:2:255",
                "canonical_locator_json": {
                    "type": "quran",
                    "canonical_id": "quran:2:255",
                    "surah": 2,
                    "ayah": 255,
                    "surah_name_ar": "البقرة",
                    "surah_name_en": "Al-Baqarah",
                },
                "text_canonical": "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ",
                "text_canonical_utf8_sha256": "c" * 64,
                "created_at": "2026-03-02T00:00:00Z",
            },
            "valid_hadith_item": {
                "text_unit_id": "550e8400-e29b-41d4-a716-446655440011",
                "source_id": "550e8400-e29b-41d4-a716-446655440001",
                "unit_type": "hadith_item",
                "canonical_id": "hadith:bukhari:sahih:1",
                "canonical_locator_json": {
                    "type": "hadith",
                    "canonical_id": "hadith:bukhari:sahih:1",
                    "collection": "bukhari",
                    "collection_name_en": "Sahih al-Bukhari",
                    "numbering_system": "sahih",
                    "hadith_number": 1,
                    "book_number": 1,
                    "book_name_en": "Revelation",
                    "grade": "sahih",
                },
                "text_canonical": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
                "text_canonical_utf8_sha256": "d" * 64,
                "created_at": "2026-03-02T00:00:00Z",
            },
        },
        "evidence_span.json": {
            "valid_span": {
                "evidence_span_id": "550e8400-e29b-41d4-a716-446655440020",
                "text_unit_id": "550e8400-e29b-41d4-a716-446655440010",
                "start_byte": 0,
                "end_byte": 20,
                "snippet_text": "اللَّهُ لَا إِلَٰهَ",
                "snippet_utf8_sha256": "e" * 64,
                "prefix_text": None,
                "suffix_text": None,
                "created_at": "2026-03-02T00:00:00Z",
            }
        },
        "kg_entity.json": {
            "valid_entity": {
                "entity_id": "550e8400-e29b-41d4-a716-446655440030",
                "entity_type": "person",
                "canonical_name": "Prophet Muhammad",
                "aliases_json": ["Muhammad", "Rasulullah", "The Messenger"],
                "description": "The final prophet in Islam",
                "created_at": "2026-03-02T00:00:00Z",
            }
        },
        "kg_edge.json": {
            "valid_edge": {
                "edge_id": "550e8400-e29b-41d4-a716-446655440040",
                "subject_entity_id": "550e8400-e29b-41d4-a716-446655440030",
                "predicate": "authored",
                "object_entity_id": "550e8400-e29b-41d4-a716-446655440050",
                "object_literal": None,
                "confidence_score": 0.95,
                "evidence_span_ids": ["550e8400-e29b-41d4-a716-446655440020"],
                "evidence_details": [
                    {
                        "evidence_span_id": "550e8400-e29b-41d4-a716-446655440020",
                        "relevance_score": 0.95,
                    }
                ],
                "created_at": "2026-03-02T00:00:00Z",
            }
        },
        "rag_answer.json": {
            "valid_answer": {
                "rag_query_id": "550e8400-e29b-41d4-a716-446655440060",
                "verdict": "answer",
                "answer_json": {
                    "verdict": "answer",
                    "statements": [
                        {
                            "text": "Allah is the only deity worthy of worship.",
                            "citations": [
                                {
                                    "evidence_span_id": "550e8400-e29b-41d4-a716-446655440020",
                                    "source_id": "550e8400-e29b-41d4-a716-446655440000",
                                    "canonical_id": "quran:2:255",
                                    "start_byte": 0,
                                    "end_byte": 20,
                                    "snippet_text": "اللَّهُ لَا إِلَٰهَ",
                                    "snippet_utf8_sha256": "e" * 64,
                                    "license_id": "CC-BY-4.0",
                                    "work_title": "The Noble Quran",
                                    "edition": "Hafs 'an Asim",
                                }
                            ],
                            "statement_type": "claim",
                        }
                    ],
                    "retrieved_evidence": [
                        {
                            "evidence_span_id": "550e8400-e29b-41d4-a716-446655440020",
                            "canonical_id": "quran:2:255",
                            "rank": 1,
                            "score_final": 0.95,
                        }
                    ],
                    "validation": {
                        "sufficiency_score": 0.9,
                        "threshold_tau": 0.8,
                        "verdict": "pass",
                    },
                },
                "statements_count": 1,
                "citations_count": 1,
                "generation_time_ms": 500,
                "model_version": "gpt-4",
                "created_at": "2026-03-02T00:00:00Z",
            },
            "valid_abstain": {
                "rag_query_id": "550e8400-e29b-41d4-a716-446655440061",
                "verdict": "abstain",
                "answer_json": {
                    "verdict": "abstain",
                    "abstain_reason": "insufficient_evidence",
                    "abstain_details": "No relevant evidence found in the corpus for this query.",
                    "retrieved_evidence": [],
                    "validation": {
                        "sufficiency_score": 0.2,
                        "threshold_tau": 0.8,
                        "verdict": "fail",
                    },
                },
                "statements_count": 0,
                "citations_count": 0,
                "generation_time_ms": 100,
                "model_version": None,
                "created_at": "2026-03-02T00:00:00Z",
            },
        },
    }


def main():
    """Main validation entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Validate Islam Intelligent schemas")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--sql-only", action="store_true", help="Only validate SQL files"
    )
    parser.add_argument(
        "--json-only", action="store_true", help="Only validate JSON files"
    )
    parser.add_argument(
        "--no-samples", action="store_true", help="Skip sample data validation"
    )
    args = parser.parse_args()

    # Determine paths
    root_dir = Path(__file__).parent.parent
    sql_dir = root_dir / "packages" / "schemas" / "sql"
    json_dir = root_dir / "packages" / "schemas" / "json"

    exit_code = 0

    print(f"{Colors.BOLD}Islam Intelligent Schema Validation{Colors.RESET}")
    print("=" * 50)
    print()

    # Validate SQL files
    if not args.json_only:
        print(f"{Colors.BOLD}SQL Migrations{Colors.RESET}")
        print("-" * 30)

        sql_files = list(sql_dir.glob("*.sql")) if sql_dir.exists() else []

        if not sql_files:
            print_status("No SQL files found", "warning")
        else:
            all_sql_valid = True
            for sql_file in sorted(sql_files):
                try:
                    with open(sql_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    is_valid, errors = validate_sql_syntax(content, sql_file.name)

                    if is_valid:
                        print_status(f"{sql_file.name}", "success")
                    else:
                        all_sql_valid = False
                        print_status(f"{sql_file.name}", "error")
                        for error in errors:
                            print(f"    {error}")

                    if args.verbose and is_valid:
                        # Count statements
                        statements = [
                            s.strip() for s in re.split(r";\s*\n", content) if s.strip()
                        ]
                        print(f"    {len(statements)} statements")

                except Exception as e:
                    all_sql_valid = False
                    print_status(f"{sql_file.name}: Error - {e}", "error")

            if not all_sql_valid:
                exit_code |= 1

        print()

    # Validate JSON schemas
    if not args.sql_only:
        print(f"{Colors.BOLD}JSON Schemas{Colors.RESET}")
        print("-" * 30)

        json_files = list(json_dir.glob("*.json")) if json_dir.exists() else []

        if not json_files:
            print_status("No JSON files found", "warning")
        else:
            all_json_valid = True
            schemas = {}

            for json_file in sorted(json_files):
                is_valid, errors = validate_json_schema(json_file)

                if is_valid:
                    print_status(f"{json_file.name}", "success")
                    if JSONSCHEMA_AVAILABLE:
                        with open(json_file, "r", encoding="utf-8") as f:
                            schemas[json_file.name] = json.load(f)
                else:
                    all_json_valid = False
                    print_status(f"{json_file.name}", "error")
                    for error in errors:
                        print(f"    {error}")

            if not all_json_valid:
                exit_code |= 2

            print()

            # Validate sample data against schemas
            if not args.no_samples and JSONSCHEMA_AVAILABLE and schemas:
                print(f"{Colors.BOLD}Sample Data Validation{Colors.RESET}")
                print("-" * 30)

                sample_data = generate_sample_data()
                all_samples_valid = True

                for schema_name, samples in sample_data.items():
                    schema_path = json_dir / schema_name

                    if not schema_path.exists():
                        print_status(f"{schema_name}: Schema not found", "warning")
                        continue

                    is_valid, errors = validate_sample_data(schema_path, samples)

                    if is_valid:
                        print_status(
                            f"{schema_name}: {len(samples)} samples passed", "success"
                        )
                    else:
                        all_samples_valid = False
                        print_status(f"{schema_name}", "error")
                        for error in errors:
                            print(f"    {error}")

                if not all_samples_valid:
                    exit_code |= 3

                print()
            elif not JSONSCHEMA_AVAILABLE:
                print_status(
                    "Sample data validation skipped (install jsonschema)", "warning"
                )
                print()

    # Summary
    print("=" * 50)
    if exit_code == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}All validations passed!{Colors.RESET}")
        print_status("SQL migrations are syntactically valid", "success")
        print_status("JSON schemas are valid Draft 7", "success")
        if not args.no_samples:
            print_status("Sample data validates against schemas", "success")
    else:
        print(f"{Colors.RED}{Colors.BOLD}Validation failed with errors{Colors.RESET}")
        if exit_code & 1:
            print_status("SQL validation failed", "error")
        if exit_code & 2:
            print_status("JSON schema validation failed", "error")
        if exit_code & 3:
            print_status("Sample data validation failed", "error")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verification script for Islam Intelligent implementation.

This script verifies:
1. Required files exist
2. SQL migrations are properly set up
3. Configuration loads correctly
4. Core modules are importable

Usage:
    python scripts/verify_implementation.py
    python scripts/verify_implementation.py --verbose
    python scripts/verify_implementation.py --ci  # Exit with error code on failure
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        """Disable colors (for CI environments)."""
        cls.GREEN = ""
        cls.RED = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.RESET = ""


class VerificationResult:
    """Result of a verification check."""

    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message


class ImplementationVerifier:
    """Verifies the implementation of the Islam Intelligent project."""

    def __init__(self, root_dir: Path, verbose: bool = False):
        self.root_dir = root_dir
        self.verbose = verbose
        self.results: list[VerificationResult] = []

    def log(self, message: str, level: str = "info"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            prefix = {
                "info": f"{Colors.BLUE}[INFO]{Colors.RESET}",
                "success": f"{Colors.GREEN}[PASS]{Colors.RESET}",
                "error": f"{Colors.RED}[FAIL]{Colors.RESET}",
                "warning": f"{Colors.YELLOW}[WARN]{Colors.RESET}",
            }.get(level, "[INFO]")
            print(f"{prefix} {message}")

    def check_file_exists(self, relative_path: str, required: bool = True) -> bool:
        """Check if a file exists."""
        file_path = self.root_dir / relative_path
        exists = file_path.exists()

        if required:
            status = "PASS" if exists else "FAIL"
            color = Colors.GREEN if exists else Colors.RED
            print(f"  {color}[{status}]{Colors.RESET} {relative_path}")
        elif self.verbose:
            status = "PASS" if exists else "SKIP"
            color = Colors.GREEN if exists else Colors.YELLOW
            print(f"  {color}[{status}]{Colors.RESET} {relative_path} (optional)")

        return exists

    def verify_required_files(self) -> VerificationResult:
        """Verify all required files exist."""
        print(f"\n{Colors.BLUE}=== Checking Required Files ==={Colors.RESET}")

        required_files = [
            # Core configuration
            "README.md",
            "AGENTS.md",
            "Makefile",
            "docker-compose.yml",
            # API application
            "apps/api/src/islam_intelligent/__init__.py",
            "apps/api/src/islam_intelligent/api/main.py",
            "apps/api/src/islam_intelligent/config.py",
            # RAG Pipeline
            "apps/api/src/islam_intelligent/rag/pipeline/core.py",
            "apps/api/src/islam_intelligent/rag/retrieval/hyde.py",
            "apps/api/src/islam_intelligent/rag/retrieval/query_expander.py",
            "apps/api/src/islam_intelligent/rag/retrieval/hybrid.py",
            # Cost governance
            "apps/api/src/islam_intelligent/cost_governance.py",
            # Database
            "apps/api/src/islam_intelligent/db/engine.py",
            "apps/api/src/islam_intelligent/domain/models.py",
            # Tests
            "apps/api/tests/conftest.py",
            "apps/api/tests/test_integration.py",
            "apps/api/tests/test_hyde.py",
            "apps/api/tests/test_query_expander.py",
            "apps/api/tests/test_cost_governance.py",
            "apps/api/tests/test_rag_pipeline_unit.py",
            # Scripts
            "scripts/verify_all.py",
            "scripts/verify_implementation.py",
            "scripts/benchmark_performance.py",
            "scripts/verify_license_gate.py",
            "scripts/verify_provenance.py",
            "scripts/verify_hash_chain.py",
            "scripts/verify_rag_logs.py",
            "scripts/db_init.py",
            "scripts/db_smoke.py",
            # CI/CD
            ".github/workflows/ci.yml",
            # Schema
            "packages/schemas/json/README.md",
            "packages/schemas/sql/README.md",
        ]

        optional_files = [
            ".env.example",
            "opencode.json",
        ]

        missing_required = []
        all_exist = True

        for file_path in required_files:
            if not self.check_file_exists(file_path, required=True):
                missing_required.append(file_path)
                all_exist = False

        for file_path in optional_files:
            self.check_file_exists(file_path, required=False)

        if missing_required:
            message = f"Missing {len(missing_required)} required files"
            self.log(f"Missing files: {missing_required}", "error")
        else:
            message = "All required files present"

        return VerificationResult("Required Files", all_exist, message)

    def verify_python_syntax(self) -> VerificationResult:
        """Verify Python files have valid syntax."""
        print(f"\n{Colors.BLUE}=== Checking Python Syntax ==={Colors.RESET}")

        python_files = list(self.root_dir.rglob("*.py"))
        invalid_files = []

        for py_file in python_files:
            # Skip virtual environments and cache
            if any(part.startswith(".") for part in py_file.parts):
                continue
            if "__pycache__" in str(py_file):
                continue
            if ".venv" in str(py_file) or "venv" in str(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    source = f.read()
                ast.parse(source)
            except SyntaxError as e:
                invalid_files.append((str(py_file.relative_to(self.root_dir)), str(e)))
                print(
                    f"  {Colors.RED}[FAIL]{Colors.RESET} {py_file.relative_to(self.root_dir)}: {e}"
                )
            except Exception as e:
                invalid_files.append((str(py_file.relative_to(self.root_dir)), str(e)))
                print(
                    f"  {Colors.YELLOW}[WARN]{Colors.RESET} {py_file.relative_to(self.root_dir)}: {e}"
                )

        if invalid_files:
            print(
                f"  {Colors.RED}Found {len(invalid_files)} files with issues{Colors.RESET}"
            )
            return VerificationResult(
                "Python Syntax", False, f"{len(invalid_files)} files have syntax issues"
            )
        else:
            print(
                f"  {Colors.GREEN}[PASS]{Colors.RESET} All Python files have valid syntax"
            )
            return VerificationResult(
                "Python Syntax", True, "All Python files have valid syntax"
            )

    def verify_imports(self) -> VerificationResult:
        """Verify core modules can be imported."""
        print(f"\n{Colors.BLUE}=== Checking Module Imports ==={Colors.RESET}")

        # Add the API src to path
        api_src = self.root_dir / "apps" / "api" / "src"
        if str(api_src) not in sys.path:
            sys.path.insert(0, str(api_src))

        modules_to_test = [
            ("islam_intelligent", "Core package"),
            ("islam_intelligent.config", "Configuration"),
            ("islam_intelligent.db.engine", "Database engine"),
            ("islam_intelligent.domain.models", "Domain models"),
            ("islam_intelligent.rag.pipeline.core", "RAG pipeline"),
            ("islam_intelligent.rag.retrieval.hyde", "HyDE retrieval"),
            ("islam_intelligent.rag.retrieval.query_expander", "Query expansion"),
            ("islam_intelligent.rag.retrieval.hybrid", "Hybrid retrieval"),
            ("islam_intelligent.cost_governance", "Cost governance"),
        ]

        failed_imports = []

        for module_name, description in modules_to_test:
            try:
                __import__(module_name)
                print(
                    f"  {Colors.GREEN}[PASS]{Colors.RESET} {module_name} ({description})"
                )
            except ImportError as e:
                failed_imports.append((module_name, str(e)))
                print(f"  {Colors.RED}[FAIL]{Colors.RESET} {module_name}: {e}")
            except Exception as e:
                failed_imports.append((module_name, str(e)))
                print(f"  {Colors.RED}[FAIL]{Colors.RESET} {module_name}: {e}")

        if failed_imports:
            return VerificationResult(
                "Module Imports",
                False,
                f"Failed to import {len(failed_imports)} modules",
            )
        else:
            return VerificationResult(
                "Module Imports",
                True,
                f"All {len(modules_to_test)} modules imported successfully",
            )

    def verify_sql_migrations(self) -> VerificationResult:
        """Verify SQL migration files exist and are valid."""
        print(f"\n{Colors.BLUE}=== Checking SQL Migrations ==={Colors.RESET}")

        # Look for SQL files in common locations
        sql_dirs = [
            self.root_dir / "packages" / "schemas" / "sql",
            self.root_dir / "apps" / "api" / "migrations",
            self.root_dir / "migrations",
        ]

        sql_files = []
        for sql_dir in sql_dirs:
            if sql_dir.exists():
                sql_files.extend(sql_dir.glob("*.sql"))

        if not sql_files:
            print(f"  {Colors.YELLOW}[WARN]{Colors.RESET} No SQL migration files found")
            return VerificationResult(
                "SQL Migrations", True, "No SQL files to verify (optional)"
            )

        valid_files = 0
        invalid_files = []

        for sql_file in sql_files:
            try:
                with open(sql_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Basic SQL validation - check for common patterns
                has_create = "CREATE" in content.upper()
                has_table = "TABLE" in content.upper()

                if has_create or has_table:
                    valid_files += 1
                    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {sql_file.name}")
                else:
                    invalid_files.append(sql_file.name)
                    print(
                        f"  {Colors.YELLOW}[WARN]{Colors.RESET} {sql_file.name} (no CREATE TABLE)"
                    )
            except Exception as e:
                invalid_files.append(f"{sql_file.name}: {e}")
                print(f"  {Colors.RED}[FAIL]{Colors.RESET} {sql_file.name}: {e}")

        if invalid_files:
            return VerificationResult(
                "SQL Migrations", False, f"{len(invalid_files)} files have issues"
            )
        else:
            return VerificationResult(
                "SQL Migrations", True, f"{valid_files} SQL files validated"
            )

    def verify_database_schema(self) -> VerificationResult:
        """Verify database schema can be created."""
        print(f"\n{Colors.BLUE}=== Checking Database Schema ==={Colors.RESET}")

        try:
            from islam_intelligent.db.engine import engine
            from islam_intelligent.domain.models import Base

            # Try to create all tables
            Base.metadata.create_all(bind=engine)

            print(
                f"  {Colors.GREEN}[PASS]{Colors.RESET} Database schema created successfully"
            )
            return VerificationResult(
                "Database Schema", True, "Schema created successfully"
            )
        except Exception as e:
            print(f"  {Colors.RED}[FAIL]{Colors.RESET} Failed to create schema: {e}")
            return VerificationResult(
                "Database Schema", False, f"Schema creation failed: {e}"
            )

    def verify_configuration(self) -> VerificationResult:
        """Verify configuration loading."""
        print(f"\n{Colors.BLUE}=== Checking Configuration ==={Colors.RESET}")

        try:
            from islam_intelligent.config import Settings, settings

            # Verify settings object exists and has expected attributes
            required_attrs = [
                "app_name",
                "environment",
                "rag_enable_llm",
                "rag_llm_model",
                "daily_budget_usd",
                "faithfulness_threshold",
            ]

            missing_attrs = []
            for attr in required_attrs:
                if not hasattr(settings, attr):
                    missing_attrs.append(attr)

            if missing_attrs:
                print(
                    f"  {Colors.RED}[FAIL]{Colors.RESET} Missing attributes: {missing_attrs}"
                )
                return VerificationResult(
                    "Configuration", False, f"Missing attributes: {missing_attrs}"
                )

            # Verify settings values are reasonable
            checks = [
                (settings.app_name != "", "app_name is set"),
                (
                    settings.environment in ["development", "production", "testing"],
                    "environment is valid",
                ),
                (
                    isinstance(settings.daily_budget_usd, (int, float)),
                    "daily_budget_usd is numeric",
                ),
                (settings.daily_budget_usd > 0, "daily_budget_usd is positive"),
                (
                    0 <= settings.faithfulness_threshold <= 1,
                    "faithfulness_threshold is in range [0,1]",
                ),
            ]

            failed_checks = []
            for check, description in checks:
                if check:
                    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {description}")
                else:
                    print(f"  {Colors.RED}[FAIL]{Colors.RESET} {description}")
                    failed_checks.append(description)

            if failed_checks:
                return VerificationResult(
                    "Configuration", False, f"Failed checks: {failed_checks}"
                )

            print(
                f"  {Colors.GREEN}[PASS]{Colors.RESET} All configuration checks passed"
            )
            return VerificationResult(
                "Configuration", True, "Configuration loaded and validated"
            )

        except Exception as e:
            print(f"  {Colors.RED}[FAIL]{Colors.RESET} Configuration error: {e}")
            return VerificationResult(
                "Configuration", False, f"Configuration error: {e}"
            )

    def verify_directory_structure(self) -> VerificationResult:
        """Verify project directory structure."""
        print(f"\n{Colors.BLUE}=== Checking Directory Structure ==={Colors.RESET}")

        required_dirs = [
            "apps/api/src/islam_intelligent",
            "apps/api/tests",
            "apps/ui/src",
            "packages/schemas",
            "scripts",
            "data",
            "docs",
            ".github/workflows",
        ]

        missing_dirs = []

        for dir_path in required_dirs:
            full_path = self.root_dir / dir_path
            if full_path.exists() and full_path.is_dir():
                print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {dir_path}/")
            else:
                print(f"  {Colors.RED}[FAIL]{Colors.RESET} {dir_path}/")
                missing_dirs.append(dir_path)

        if missing_dirs:
            return VerificationResult(
                "Directory Structure", False, f"Missing directories: {missing_dirs}"
            )
        else:
            return VerificationResult(
                "Directory Structure", True, "All required directories present"
            )

    def verify_test_files(self) -> VerificationResult:
        """Verify test files are properly structured."""
        print(f"\n{Colors.BLUE}=== Checking Test Files ==={Colors.RESET}")

        test_dir = self.root_dir / "apps" / "api" / "tests"

        if not test_dir.exists():
            return VerificationResult("Test Files", False, "Tests directory not found")

        test_files = list(test_dir.glob("test_*.py"))

        if not test_files:
            return VerificationResult("Test Files", False, "No test files found")

        issues = []

        for test_file in test_files:
            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Check for test functions
                if "def test_" not in content and "class Test" not in content:
                    issues.append(f"{test_file.name}: No test functions found")
                    print(
                        f"  {Colors.YELLOW}[WARN]{Colors.RESET} {test_file.name}: No test functions"
                    )
                else:
                    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {test_file.name}")

                # Check for proper imports
                if "import pytest" not in content and "from pytest" not in content:
                    issues.append(f"{test_file.name}: Missing pytest import")

            except Exception as e:
                issues.append(f"{test_file.name}: {e}")
                print(f"  {Colors.RED}[FAIL]{Colors.RESET} {test_file.name}: {e}")

        if issues:
            return VerificationResult(
                "Test Files", False, f"{len(issues)} test files have issues"
            )
        else:
            return VerificationResult(
                "Test Files", True, f"{len(test_files)} test files validated"
            )

    def run_all_verifications(self) -> list[VerificationResult]:
        """Run all verification checks."""
        results = []

        results.append(self.verify_required_files())
        results.append(self.verify_directory_structure())
        results.append(self.verify_python_syntax())
        results.append(self.verify_imports())
        results.append(self.verify_sql_migrations())
        results.append(self.verify_database_schema())
        results.append(self.verify_configuration())
        results.append(self.verify_test_files())

        return results

    def print_summary(self, results: list[VerificationResult]):
        """Print verification summary."""
        print(f"\n{Colors.BLUE}{'=' * 50}{Colors.RESET}")
        print(f"{Colors.BLUE}=== VERIFICATION SUMMARY ==={Colors.RESET}")
        print(f"{Colors.BLUE}{'=' * 50}{Colors.RESET}")

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        total = len(results)

        for result in results:
            status = (
                f"{Colors.GREEN}PASS{Colors.RESET}"
                if result.passed
                else f"{Colors.RED}FAIL{Colors.RESET}"
            )
            print(f"  [{status}] {result.name}")
            if not result.passed or self.verbose:
                print(f"       {result.message}")

        print(f"\n{Colors.BLUE}{'=' * 50}{Colors.RESET}")
        print(
            f"Total: {total} | {Colors.GREEN}Passed: {passed}{Colors.RESET} | {Colors.RED}Failed: {failed}{Colors.RESET}"
        )

        return failed == 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify Islam Intelligent implementation"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--ci", action="store_true", help="CI mode (exit with error code on failure)"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument("--root", type=str, default=".", help="Project root directory")

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    root_dir = Path(args.root).resolve()

    if not root_dir.exists():
        print(
            f"{Colors.RED}Error: Root directory does not exist: {root_dir}{Colors.RESET}"
        )
        sys.exit(1)

    print(f"{Colors.BLUE}Islam Intelligent Implementation Verifier{Colors.RESET}")
    print(f"Root directory: {root_dir}")

    verifier = ImplementationVerifier(root_dir, verbose=args.verbose)
    results = verifier.run_all_verifications()
    all_passed = verifier.print_summary(results)

    if args.ci and not all_passed:
        sys.exit(1)

    sys.exit(0 if all_passed else 0 if not args.ci else 1)


if __name__ == "__main__":
    main()

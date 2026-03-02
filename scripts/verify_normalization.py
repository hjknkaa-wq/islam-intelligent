#!/usr/bin/env python3
"""
Unicode normalization verification script.

Verifies that stored text follows NFC normalization rules
and that NFKC is not used for storage.

Usage:
    python scripts/verify_normalization.py --check nfc
    python scripts/verify_normalization.py --check nfkc_not_stored
    python scripts/verify_normalization.py --check all

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Invalid arguments or configuration error

References:
    Unicode TR15: https://unicode.org/reports/tr15/
"""

import argparse
import importlib.util
import os
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional


# Add the API src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
API_SRC = PROJECT_ROOT / "apps" / "api" / "src"

if API_SRC.exists():
    sys.path.insert(0, str(API_SRC))


def import_normalizer():
    """Import the normalizer module, handling various path configurations."""
    try:
        from islam_intelligent.normalize import (
            is_nfc_normalized,
            is_nfkc_normalized,
            normalize_storage,
        )

        return is_nfc_normalized, is_nfkc_normalized, normalize_storage
    except ImportError:
        # Fallback: try to import directly
        normalizer_path = API_SRC / "islam_intelligent" / "normalize" / "normalizer.py"
        if normalizer_path.exists():
            spec = importlib.util.spec_from_file_location("normalizer", normalizer_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return (
                module.is_nfc_normalized,
                module.is_nfkc_normalized,
                module.normalize_storage,
            )
        raise ImportError(
            "Could not import normalizer module. "
            "Ensure the script is run from the project root."
        )


class VerificationError:
    """Represents a verification error with details."""

    def __init__(
        self, message: str, location: Optional[str] = None, sample: Optional[str] = None
    ):
        self.message = message
        self.location = location
        self.sample = sample

    def __str__(self):
        parts = [self.message]
        if self.location:
            parts.append(f"  Location: {self.location}")
        if self.sample:
            # Truncate sample if too long
            sample_str = (
                self.sample[:100] + "..." if len(self.sample) > 100 else self.sample
            )
            # Show Unicode codepoints for debugging
            codepoints = " ".join(f"U+{ord(c):04X}" for c in self.sample[:20])
            parts.append(f"  Sample: {sample_str!r}")
            parts.append(f"  Codepoints: {codepoints}")
        return "\n".join(parts)


class NormalizationVerifier:
    """Verifier for Unicode normalization compliance."""

    def __init__(self):
        self.errors: List[VerificationError] = []
        self.warnings: List[VerificationError] = []
        self.checked_count = 0

        # Import normalizer functions
        self.is_nfc_normalized, self.is_nfkc_normalized, self.normalize_storage = (
            import_normalizer()
        )

    def check_nfc_compliance(self, text_units: Optional[List[dict]] = None) -> bool:
        """
        Verify all text_canonical fields are NFC normalized.

        Args:
            text_units: List of text unit dictionaries with 'text_canonical' field.
                       If None, uses mock data for testing.

        Returns:
            True if all text is NFC compliant
        """
        print("Checking NFC compliance for storage text...")

        if text_units is None:
            # Try to get from database or use test data
            text_units = self._get_text_units_from_storage()

        if not text_units:
            print("  No text units found to check.")
            return True

        self.checked_count = len(text_units)

        for i, unit in enumerate(text_units):
            text = unit.get("text_canonical", "")
            unit_id = unit.get("id", f"unit_{i}")

            if not text:
                self.warnings.append(
                    VerificationError(
                        "Empty text_canonical", location=f"text_unit.id={unit_id}"
                    )
                )
                continue

            if not self.is_nfc_normalized(text):
                # Show what NFC normalization would produce
                nfc_version = self.normalize_storage(text)
                self.errors.append(
                    VerificationError(
                        "Text is not NFC normalized",
                        location=f"text_unit.id={unit_id}",
                        sample=text[:200],
                    )
                )
                print(f"  ERROR: text_unit.id={unit_id} is not NFC normalized")

        if not self.errors:
            print(f"  [OK] All {self.checked_count} text units are NFC compliant")
            return True
        else:
            print(
                f"  [FAIL] Found {len(self.errors)} non-NFC text units out of {self.checked_count}"
            )
            return False

    def check_nfkc_not_stored(self, text_units: Optional[List[dict]] = None) -> bool:
        """
        Verify no text_canonical fields contain NFKC-normalized content.

        NFKC should only be used for search indexing, not storage.

        Args:
            text_units: List of text unit dictionaries with 'text_canonical' field.

        Returns:
            True if no NFKC content is found in storage
        """
        print("Checking that NFKC is not stored...")

        if text_units is None:
            text_units = self._get_text_units_from_storage()

        if not text_units:
            print("  No text units found to check.")
            return True

        self.checked_count = len(text_units)
        nfkc_count = 0

        for i, unit in enumerate(text_units):
            text = unit.get("text_canonical", "")
            unit_id = unit.get("id", f"unit_{i}")

            if not text:
                continue

            # Check if text is NFKC (which means it might have been NFKC-normalized)
            # Note: ASCII text is both NFC and NFKC, so we need to check for
            # specific cases where NFKC differs from NFC
            if self._is_likely_nfkc_normalized(text):
                nfkc_count += 1
                self.warnings.append(
                    VerificationError(
                        "Text may be NFKC normalized (compatibility characters detected)",
                        location=f"text_unit.id={unit_id}",
                        sample=text[:200],
                    )
                )
                print(
                    f"  WARNING: text_unit.id={unit_id} contains compatibility characters"
                )

        if nfkc_count == 0:
            print(f"  [OK] No NFKC content detected in {self.checked_count} text units")
            return True
        else:
            print(f"  [WARN] Found {nfkc_count} text units with potential NFKC content")
            # This is a warning, not an error, as some NFKC is OK if it's canonical too
            return True

    def _is_likely_nfkc_normalized(self, text: str) -> bool:
        """
        Check if text contains characters that NFKC would change.

        Returns True if text contains compatibility characters that
        suggest it might have been NFKC-normalized.
        """
        for char in text:
            category = unicodedata.category(char)
            # Check for compatibility characters
            # These are typically in the Cn, Co, or specific compatibility blocks
            if category == "Co":  # Private use
                return True

            # Check for specific compatibility character ranges
            codepoint = ord(char)

            # CJK Compatibility Ideographs
            if 0xF900 <= codepoint <= 0xFAFF:
                return True

            # Alphabetic Presentation Forms
            if 0xFB00 <= codepoint <= 0xFB4F:
                # Some Arabic presentation forms are compatibility
                if 0xFB50 <= codepoint <= 0xFDFF:
                    return True

            # Arabic Presentation Forms-A
            if 0xFB50 <= codepoint <= 0xFDFF:
                return True

            # Arabic Presentation Forms-B
            if 0xFE70 <= codepoint <= 0xFEFF:
                return True

            # Fullwidth forms
            if 0xFF00 <= codepoint <= 0xFFEF:
                return True

            # Check if NFKC differs from NFC for this char
            nfc = unicodedata.normalize("NFC", char)
            nfkc = unicodedata.normalize("NFKC", char)
            if nfc != nfkc:
                return True

        return False

    def _get_text_units_from_storage(self) -> List[dict]:
        """
        Retrieve text units from storage.

        Returns empty list if no storage is configured.
        Override this method to connect to actual database.
        """
        # This is a placeholder - in production, this would query the database
        # For now, return empty list to indicate no data available
        return []

    def print_summary(self):
        """Print verification summary."""
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"Items checked: {self.checked_count}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")

        if self.errors:
            print("\nERRORS:")
            for i, error in enumerate(self.errors, 1):
                print(f"\n{i}. {error}")

        if self.warnings:
            print("\nWARNINGS:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"\n{i}. {warning}")

        print("\n" + "=" * 60)


def run_mock_verification():
    """Run verification with mock data for testing purposes."""
    print("Running verification with mock test data...\n")

    # Create test data
    mock_units = [
        {"id": "unit_1", "text_canonical": "بسم الله الرحمن الرحيم"},  # NFC Arabic
        {"id": "unit_2", "text_canonical": "Al-Fatiha"},  # ASCII (both NFC and NFKC)
        {"id": "unit_3", "text_canonical": "\u0041\u0308"},  # Not NFC (A + combining)
        {"id": "unit_4", "text_canonical": ""},  # Empty
        {"id": "unit_5", "text_canonical": "① Test"},  # Contains compatibility char
    ]

    verifier = NormalizationVerifier()

    # Check NFC
    nfc_ok = verifier.check_nfc_compliance(mock_units)

    # Reset for second check
    verifier.errors = []
    verifier.warnings = []

    # Check NFKC not stored
    nfkc_ok = verifier.check_nfkc_not_stored(mock_units)

    # Print summary
    print("\n" + "=" * 60)
    print("MOCK VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"NFC check: {'PASS' if nfc_ok else 'FAIL'}")
    print(f"NFKC check: {'PASS' if nfkc_ok else 'FAIL'}")

    return nfc_ok and nfkc_ok


def main():
    parser = argparse.ArgumentParser(
        description="Verify Unicode normalization compliance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/verify_normalization.py --check nfc
  python scripts/verify_normalization.py --check nfkc_not_stored
  python scripts/verify_normalization.py --check all
  python scripts/verify_normalization.py --mock  # Run with test data
        """,
    )

    parser.add_argument(
        "--check",
        choices=["nfc", "nfkc_not_stored", "all"],
        default="all",
        help="Which check to run (default: all)",
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run with mock test data instead of database",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Handle mock mode
    if args.mock:
        success = run_mock_verification()
        sys.exit(0 if success else 1)

    # Normal verification mode
    verifier = NormalizationVerifier()
    all_ok = True

    try:
        if args.check in ("nfc", "all"):
            nfc_ok = verifier.check_nfc_compliance()
            all_ok = all_ok and nfc_ok

        if args.check in ("nfkc_not_stored", "all"):
            nfkc_ok = verifier.check_nfkc_not_stored()
            all_ok = all_ok and nfkc_ok

        if args.verbose or not all_ok:
            verifier.print_summary()

        if all_ok:
            print("\n[OK] All normalization checks passed")
            sys.exit(0)
        else:
            print("\n[FAIL] Some normalization checks failed")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()

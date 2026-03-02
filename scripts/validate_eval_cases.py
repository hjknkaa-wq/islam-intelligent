# Evaluation Case Validator
# Validates golden.yaml cases against schema requirements

import yaml
import sys
from pathlib import Path


def validate_case(case: dict, index: int) -> list:
    """Validate a single eval case. Returns list of errors."""
    errors = []
    case_id = case.get("case_id", f"case_{index}")

    # Required fields
    required = ["case_id", "query", "expected_verdict", "notes"]
    for field in required:
        if field not in case:
            errors.append(f"{case_id}: Missing required field '{field}'")

    # Verdict validation
    if "expected_verdict" in case:
        if case["expected_verdict"] not in ["answer", "abstain"]:
            errors.append(f"{case_id}: Invalid verdict '{case['expected_verdict']}'")

    # Citation requirements
    if case.get("expected_verdict") == "answer":
        if "required_citations" not in case:
            errors.append(f"{case_id}: Answerable case must have required_citations")
        elif len(case.get("required_citations", [])) == 0:
            errors.append(
                f"{case_id}: Answerable case must have at least 1 required citation"
            )

    if case.get("expected_verdict") == "abstain":
        if case.get("required_citations"):
            if len(case["required_citations"]) > 0:
                errors.append(
                    f"{case_id}: Abstention case should have empty required_citations"
                )

    return errors


def main() -> int:
    """Main validation entry point."""
    cases_file = Path(__file__).parent.parent / "eval" / "cases" / "golden.yaml"

    print("=" * 60)
    print("EVAL CASE VALIDATION")
    print("=" * 60)

    try:
        with open(cases_file) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"FAIL: Could not load {cases_file}: {e}")
        return 1

    cases = data.get("cases", [])
    all_errors = []

    print(f"\nLoaded {len(cases)} cases")

    for i, case in enumerate(cases):
        errors = validate_case(case, i)
        all_errors.extend(errors)
        if not errors:
            print(f"OK: {case.get('case_id', i)} - {case.get('expected_verdict')}")

    # Summary
    print("\n" + "=" * 60)

    stats = {
        "answerable": sum(1 for c in cases if c.get("expected_verdict") == "answer"),
        "abstain": sum(1 for c in cases if c.get("expected_verdict") == "abstain"),
    }

    print(f"Answerable: {stats['answerable']}")
    print(f"Abstention: {stats['abstain']}")

    if all_errors:
        print(f"\nERRORS ({len(all_errors)}):")
        for error in all_errors:
            print(f"  - {error}")
        print("\nFAILED: Case validation failed")
        return 1
    else:
        print("\nSUCCESS: All cases valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())

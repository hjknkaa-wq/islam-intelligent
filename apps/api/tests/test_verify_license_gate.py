from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "verify_license_gate.py"


def _load_module():
    """
    Load and return the verify_license_gate module from the SCRIPT_PATH file.
    
    Registers the loaded module in sys.modules before executing it so subsequent imports
    refer to the same module object.
    
    Raises:
        RuntimeError: If a module specification or loader cannot be created for SCRIPT_PATH.
    
    Returns:
        module: The imported module object.
    """
    spec = importlib.util.spec_from_file_location("verify_license_gate", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_source_table(db_path: Path) -> None:
    """
    Create the required source_document table in the SQLite database at db_path.
    
    The table will be created with the following columns:
    - source_id (TEXT PRIMARY KEY)
    - work_title (TEXT NOT NULL)
    - license_id (TEXT NOT NULL)
    - trust_status (TEXT NOT NULL)
    
    Parameters:
        db_path (Path): Path to the SQLite database file; the file will be created if it does not exist.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE source_document (
            source_id TEXT PRIMARY KEY,
            work_title TEXT NOT NULL,
            license_id TEXT NOT NULL,
            trust_status TEXT NOT NULL
        )"""
        )
        conn.commit()
    finally:
        conn.close()


def test_verify_license_gate_accepts_unlicense(tmp_path):
    module = _load_module()
    db_path = tmp_path / "dev.db"
    _create_source_table(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO source_document (source_id, work_title, license_id, trust_status) VALUES (?, ?, ?, ?)",
            ("src_1", "Hadith API", "UNLICENSE", "trusted"),
        )
        conn.commit()
    finally:
        conn.close()

    passed, violations = module.verify_license_gate(str(db_path))
    assert passed is True
    assert violations == []


def test_verify_license_gate_rejects_unknown_license(tmp_path):
    """
    Verifies that verify_license_gate reports a failure and an UNKNOWN_LICENSE violation for a source with an unrecognized license.
    
    Inserts a row with license_id "NOT_A_LICENSE" into a temporary SQLite database and asserts that verify_license_gate returns a failing result and includes a violation containing "UNKNOWN_LICENSE".
    
    Parameters:
        tmp_path (pathlib.Path): Temporary directory provided by pytest for creating the test database file.
    """
    module = _load_module()
    db_path = tmp_path / "dev.db"
    _create_source_table(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO source_document (source_id, work_title, license_id, trust_status) VALUES (?, ?, ?, ?)",
            ("src_2", "Unknown Source", "NOT_A_LICENSE", "trusted"),
        )
        conn.commit()
    finally:
        conn.close()

    passed, violations = module.verify_license_gate(str(db_path))
    assert passed is False
    assert any("UNKNOWN_LICENSE" in violation for violation in violations)

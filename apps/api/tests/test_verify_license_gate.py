from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "verify_license_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_license_gate", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_source_table(db_path: Path) -> None:
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

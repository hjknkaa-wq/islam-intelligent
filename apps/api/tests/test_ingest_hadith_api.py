from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "ingest_hadith_api.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ingest_hadith_api", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """CREATE TABLE source_document (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            work_title TEXT NOT NULL,
            author TEXT,
            language TEXT NOT NULL,
            license_id TEXT NOT NULL,
            license_url TEXT NOT NULL,
            rights_holder TEXT,
            attribution_text TEXT,
            content_hash_sha256 TEXT NOT NULL,
            content_mime TEXT NOT NULL,
            content_length_bytes INTEGER NOT NULL,
            storage_path TEXT NOT NULL,
            trust_status TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE text_unit (
            text_unit_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            canonical_id TEXT NOT NULL UNIQUE,
            canonical_locator_json TEXT NOT NULL,
            text_canonical TEXT NOT NULL,
            text_canonical_utf8_sha256 TEXT NOT NULL
        )"""
        )
        conn.commit()
    finally:
        conn.close()


def _sample_payload() -> str:
    payload = {
        "metadata": {"section": {"1": "Revelation"}},
        "hadiths": [
            {
                "hadithnumber": 1,
                "text": "Hadith text one",
                "grades": [{"grade": "Sahih"}],
                "reference": {"book": 1, "hadith": 1},
            },
            {
                "hadithnumber": 2,
                "text": "Hadith text two",
                "grades": [{"grade": "Sahih"}],
                "reference": {"book": 1, "hadith": 2},
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _patch_download(module, monkeypatch, payload_text: str) -> None:
    def _fake_download(primary_url: str, fallback_url: str, timeout_sec: int):
        del fallback_url, timeout_sec
        if "editions/ara-bukhari" in primary_url:
            return payload_text, primary_url
        if "editions.min.json" in primary_url or "editions.json" in primary_url:
            index_payload = {
                "bukhari": {
                    "collection": [
                        {"book": "bukhari", "name": "ara-bukhari"},
                    ]
                }
            }
            return json.dumps(index_payload), primary_url
        raise RuntimeError(f"Unexpected URL in test: {primary_url}")

    monkeypatch.setattr(module, "_download_text_with_fallback", _fake_download)


def test_ingest_hadith_api_is_idempotent(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "dev.db"
    checkpoint_path = tmp_path / "checkpoint.json"
    _create_test_db(db_path)

    monkeypatch.setattr(module, "_assert_safe_source_policy", lambda: None)
    _patch_download(module, monkeypatch, _sample_payload())

    args = module.CliArgs(
        db_path=db_path,
        editions=["ara-bukhari"],
        all_supported_arabic=False,
        api_ref="1",
        batch_size=2,
        timeout_sec=5,
        checkpoint_file=checkpoint_path,
        resume=False,
    )

    created, skipped, processed, editions = module.ingest_hadith_from_api(args)
    assert created == 2
    assert skipped == 0
    assert processed == 2
    assert editions == ["ara-bukhari"]

    created2, skipped2, processed2, editions2 = module.ingest_hadith_from_api(args)
    assert created2 == 0
    assert skipped2 == 2
    assert processed2 == 2
    assert editions2 == ["ara-bukhari"]

    conn = sqlite3.connect(db_path)
    try:
        hadith_count = conn.execute(
            "SELECT COUNT(*) FROM text_unit WHERE unit_type = 'hadith_item'"
        ).fetchone()[0]
        source_count = conn.execute("SELECT COUNT(*) FROM source_document").fetchone()[
            0
        ]
    finally:
        conn.close()

    assert hadith_count == 2
    assert source_count == 1


def test_ingest_hadith_api_resume_from_checkpoint(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "dev.db"
    checkpoint_path = tmp_path / "checkpoint.json"
    _create_test_db(db_path)

    monkeypatch.setattr(module, "_assert_safe_source_policy", lambda: None)
    _patch_download(module, monkeypatch, _sample_payload())

    source_key = "hadith_api_1_ara-bukhari"
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, source_key))
    canonical_1 = "hadith:bukhari:sahih:1"
    text_unit_id_1 = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical_1))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO source_document
            (source_id, source_type, work_title, author, language,
             license_id, license_url, rights_holder, attribution_text,
             content_hash_sha256, content_mime, content_length_bytes,
             storage_path, trust_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                "hadith_collection",
                "Hadith API (ara-bukhari)",
                "hadith-api contributors",
                "ar",
                "UNLICENSE",
                "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/LICENSE",
                "Public domain dedication via The Unlicense",
                "Source: hadith-api",
                "a" * 64,
                "application/json; charset=utf-8",
                1,
                "https://example.invalid",
                "trusted",
            ),
        )
        conn.execute(
            """INSERT INTO text_unit
            (text_unit_id, source_id, unit_type, canonical_id,
             canonical_locator_json, text_canonical, text_canonical_utf8_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                text_unit_id_1,
                source_id,
                "hadith_item",
                canonical_1,
                json.dumps({"collection": "bukhari", "numbering_system": "sahih"}),
                "Hadith text one",
                "b" * 64,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    checkpoint_path.write_text(
        json.dumps(
            {
                "edition": "ara-bukhari",
                "last_hadith_number": 1,
                "canonical_id": canonical_1,
            }
        ),
        encoding="utf-8",
    )

    args = module.CliArgs(
        db_path=db_path,
        editions=["ara-bukhari"],
        all_supported_arabic=False,
        api_ref="1",
        batch_size=10,
        timeout_sec=5,
        checkpoint_file=checkpoint_path,
        resume=True,
    )

    created, skipped, processed, editions = module.ingest_hadith_from_api(args)
    assert created == 1
    assert skipped == 0
    assert processed == 1
    assert editions == ["ara-bukhari"]


def test_safe_source_policy_requires_marker(tmp_path, monkeypatch):
    module = _load_module()
    audit_path = tmp_path / "LICENSE_AUDIT.md"
    audit_path.write_text(
        "# test\n\n#### something_else\n- status: SAFE\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "LICENSE_AUDIT_PATH", audit_path)

    with pytest.raises(RuntimeError):
        module._assert_safe_source_policy()

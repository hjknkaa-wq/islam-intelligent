"""KG edge evidence enforcement tests."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedFunction=false, reportUnusedImport=false

import hashlib
import json

import pytest

from islam_intelligent.provenance import models as _prov_models  # noqa: F401

from islam_intelligent.db.engine import SessionLocal, engine
from islam_intelligent.domain.models import Base, SourceDocument, TextUnit
from islam_intelligent.kg import edge_manager, entity_manager
from islam_intelligent.kg.models import EvidenceSpan


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def _insert_evidence_span(evidence_span_id: str = "es_test_001") -> str:
    text = "evidence"
    text_bytes = text.encode("utf-8")
    snippet_hash = hashlib.sha256(text_bytes).hexdigest()
    text_hash = hashlib.sha256(text_bytes).hexdigest()
    content_hash = hashlib.sha256(b"{}").hexdigest()
    manifest_hash = hashlib.sha256(b"manifest").hexdigest()
    db = SessionLocal()
    try:
        # Satisfy EvidenceSpan(text_unit_id) FK -> TextUnit(text_unit_id) FK -> SourceDocument(source_id)
        source_id = "src_test_001"
        db.add(
            SourceDocument(
                source_id=source_id,
                version=1,
                source_type="quran",
                trust_status="trusted",
                title="test",
                author="test",
                language="en",
                content_json=json.dumps({"text": text}),
                content_sha256=content_hash,
                manifest_sha256=manifest_hash,
            )
        )
        db.add(
            TextUnit(
                text_unit_id="tu_test_001",
                source_id=source_id,
                unit_type="quran_ayah",
                canonical_id="quran:1:1",
                canonical_locator_json="{}",
                text_canonical=text,
                text_canonical_utf8_sha256=text_hash,
            )
        )
        db.flush()
        db.add(
            EvidenceSpan(
                evidence_span_id=evidence_span_id,
                text_unit_id="tu_test_001",
                start_byte=0,
                end_byte=len(text_bytes),
                snippet_text=text,
                snippet_utf8_sha256=snippet_hash,
                prefix_text="",
                suffix_text="",
            )
        )
        db.commit()
    finally:
        db.close()
    return evidence_span_id


def test_rejects_edge_creation_without_evidence_span_ids():
    subject_id = entity_manager.create_entity("concept", "Allah")

    with pytest.raises(ValueError, match="evidence_span_ids"):
        edge_manager.create_edge(
            subject_entity_id=subject_id,
            predicate="is described by",
            object_literal="Ayat al-Kursi",
        )


def test_rejects_edge_creation_with_empty_evidence_span_ids():
    subject_id = entity_manager.create_entity("concept", "Allah")

    with pytest.raises(ValueError, match="evidence_span_ids"):
        edge_manager.create_edge(
            subject_entity_id=subject_id,
            predicate="is described by",
            object_literal="Ayat al-Kursi",
            evidence_span_ids=[],
        )


def test_accepts_edge_creation_with_valid_evidence_span_ids():
    subject_id = entity_manager.create_entity("concept", "Allah")
    es_id = _insert_evidence_span("es_ok_001")

    edge_id = edge_manager.create_edge(
        subject_entity_id=subject_id,
        predicate="is described by",
        object_literal="Ayat al-Kursi",
        evidence_span_ids=[es_id],
        confidence=1.0,
    )

    edge = edge_manager.get_edge(edge_id)
    assert edge["edge_id"] == edge_id
    assert edge["evidence_span_ids"] == [es_id]


def test_entity_to_entity_edge_with_evidence():
    subject_id = entity_manager.create_entity("chapter", "Surah Al-Fatiha")
    obj_id = entity_manager.create_entity("phrase", "Bismillah")
    es_id = _insert_evidence_span("es_ok_002")

    edge_id = edge_manager.create_edge(
        subject_entity_id=subject_id,
        predicate="contains",
        object_entity_id=obj_id,
        evidence_span_ids=[es_id],
        confidence=1.0,
    )

    edge = edge_manager.get_edge(edge_id)
    assert edge["object_entity_id"] == obj_id
    assert edge["object_literal"] is None


def test_entity_to_literal_edge_with_evidence():
    subject_id = entity_manager.create_entity("person", "Prophet Muhammad")
    es_id = _insert_evidence_span("es_ok_003")

    edge_id = edge_manager.create_edge(
        subject_entity_id=subject_id,
        predicate="narrated",
        object_literal="Hadith on intentions",
        evidence_span_ids=[es_id],
        confidence=1.0,
    )

    edge = edge_manager.get_edge(edge_id)
    assert edge["object_entity_id"] is None
    assert edge["object_literal"] == "Hadith on intentions"

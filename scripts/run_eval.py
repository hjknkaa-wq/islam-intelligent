#!/usr/bin/env python3
"""Evaluation runner for citation-required and abstention metrics.

Runs eval cases from eval/cases/<suite>.yaml and emits a JSON report.

Usage:
  python scripts/run_eval.py --suite golden --output eval/report.json
  python scripts/run_eval.py --suite golden --assert-defaults
  python scripts/run_eval.py --suite golden --assert citation_required_pass_rate==1.0 --assert "abstention_f1>=0.95"
"""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVAL_CASES_DIR = ROOT / "eval" / "cases"


def _json_dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def _sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_yaml(path: Path) -> dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        raw = cast(object, yaml.safe_load(f))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    data: dict[str, object] = {}
    for k, v in raw.items():
        if isinstance(k, str):
            data[k] = v
    return data


def _maybe_parse_json(text: str) -> dict[str, object] | None:
    try:
        obj = cast(object, json.loads(text))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    out: dict[str, object] = {}
    for k, v in obj.items():
        if isinstance(k, str):
            out[k] = v
    return out


def _canonical_requirement_satisfied(required: str, found: set[str]) -> bool:
    req = required.strip()
    if not req:
        return False
    if req.endswith(":"):
        return any(cid.startswith(req) for cid in found)
    return req in found


def _safe_div(num: float, den: float, *, empty: float) -> float:
    if den == 0:
        return empty
    return num / den


@dataclass(frozen=True)
class Assertion:
    metric: str
    op: str
    value: float

    def check(self, metrics: dict[str, object]) -> tuple[bool, str]:
        if self.metric not in metrics:
            return False, f"unknown metric: {self.metric}"
        raw = metrics[self.metric]
        try:
            actual = float(str(raw))
        except Exception:
            return False, f"metric not numeric: {self.metric}={raw!r}"

        ok = {
            "==": actual == self.value,
            "!=": actual != self.value,
            ">=": actual >= self.value,
            "<=": actual <= self.value,
            ">": actual > self.value,
            "<": actual < self.value,
        }[self.op]
        return ok, f"{self.metric}{self.op}{self.value} (actual={actual})"


_ASSERT_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(==|!=|>=|<=|>|<)\s*([0-9]+(?:\.[0-9]+)?)\s*$"
)


DEFAULT_ASSERTS: list[str] = [
    "citation_required_pass_rate==1.0",
    "locator_resolve_pass_rate==1.0",
    "abstention_f1>=0.95",
]


def _parse_assertions(raw: list[str]) -> list[Assertion]:
    out: list[Assertion] = []
    for item in raw:
        m = _ASSERT_RE.match(item)
        if not m:
            raise ValueError(
                "invalid --assert format; expected like citation_required_pass_rate==1.0"
            )
        out.append(Assertion(metric=m.group(1), op=m.group(2), value=float(m.group(3))))
    return out


def _normalize_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    return v


def _compute_failure_taxonomy(cases: list[dict[str, object]]) -> dict[str, int]:
    """Categorize why answerable cases fail the citation/verification gates."""

    taxonomy = {
        "missing_citations": 0,
        "untrusted_sources": 0,
        "citation_verification_failed": 0,
        "other": 0,
    }

    for case in cases:
        if case.get("expected_verdict") != "answer":
            continue

        pred = case.get("predicted_verdict")
        cr_pass = case.get("citation_required_pass")
        lr_pass = case.get("locator_resolve_pass")

        fully_ok = pred == "answer" and cr_pass is True and lr_pass is True
        if fully_ok:
            continue

        reason = _normalize_reason(case.get("fail_reason")) or _normalize_reason(
            case.get("abstain_reason")
        )

        if reason in ("untrusted_sources", "all_sources_untrusted"):
            taxonomy["untrusted_sources"] += 1
            continue

        if pred == "answer":
            # Missing citations only makes sense for an answer verdict.
            if cr_pass is False or reason in (
                "verification_failed",
                "missing_citations",
            ):
                taxonomy["missing_citations"] += 1
                continue

            # Locator resolution/hash checks are part of citation verification.
            if lr_pass is False or reason == "citation_verification_failed":
                taxonomy["citation_verification_failed"] += 1
                continue
        else:
            if reason == "citation_verification_failed":
                taxonomy["citation_verification_failed"] += 1
                continue
            if reason in ("verification_failed", "missing_citations"):
                taxonomy["missing_citations"] += 1
                continue

        taxonomy["other"] += 1

    return taxonomy


def _http_json(
    method: str, url: str, payload: dict[str, object] | None = None
) -> dict[str, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = cast(http.client.HTTPResponse, urllib.request.urlopen(req, timeout=30))
    try:
        body_bytes = resp.read()
    finally:
        resp.close()

    body = body_bytes.decode("utf-8")
    obj = _maybe_parse_json(body)
    if obj is None:
        raise ValueError(f"non-JSON response from {url}")
    return obj


def _ensure_import_path() -> None:
    api_src = ROOT / "apps" / "api" / "src"
    sys.path.insert(0, str(api_src))


def _init_db_and_load_fixtures() -> None:
    """Create tables, load fixtures, and create resolvable evidence spans."""

    _ensure_import_path()

    from islam_intelligent.db.engine import SessionLocal, engine
    from islam_intelligent.domain.models import Base, SourceDocument, TextUnit
    from islam_intelligent.kg.models import EvidenceSpan
    from islam_intelligent.provenance import models as _prov_models

    _ = _prov_models

    from islam_intelligent.domain.span_builder import create_span
    from islam_intelligent.ingest.text_unit_builder import (
        create_hadith_item,
        create_quran_ayah,
        validate_canonical_id,
    )

    Base.metadata.create_all(bind=engine)

    fixtures_dir = ROOT / "data" / "fixtures"
    quran_path = fixtures_dir / "quran_minimal.yaml"
    hadith_path = fixtures_dir / "hadith_minimal.yaml"

    def _create_source(db, fixture: dict[str, object]) -> str:
        import uuid

        meta = fixture.get("metadata")
        if not isinstance(meta, dict) or not isinstance(meta.get("source_id"), str):
            raise ValueError("fixture missing metadata.source_id")
        logical_id = meta["source_id"]
        source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, logical_id))

        existing = (
            db.query(SourceDocument)
            .filter(SourceDocument.source_id == source_id)
            .first()
        )
        if existing is not None:
            return existing.source_id

        text_units = fixture.get("text_units", [])
        if not isinstance(text_units, list):
            text_units = []
        all_text = "\n".join(
            (u.get("text") or u.get("text_ar") or "")
            for u in text_units
            if isinstance(u, dict)
        )
        content_sha256 = _sha256_utf8(all_text)
        content_json = json.dumps(fixture, ensure_ascii=False)
        manifest = {
            "source_id": source_id,
            "version": 1,
            "source_type": meta.get("source_type", "unknown"),
            "title": meta.get("work_title"),
            "author": meta.get("author"),
            "language": meta.get("language", "ar"),
            "content_sha256": content_sha256,
        }
        manifest_sha256 = _sha256_utf8(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        )

        doc = SourceDocument(
            source_id=source_id,
            source_type=meta.get("source_type", "unknown"),
            title=meta.get("work_title"),
            author=meta.get("author"),
            language=meta.get("language", "ar"),
            content_json=content_json,
            content_sha256=content_sha256,
            manifest_sha256=manifest_sha256,
        )
        db.add(doc)
        db.commit()
        return source_id

    def _load_text_units(db) -> None:
        for path in (quran_path, hadith_path):
            if not path.exists():
                raise FileNotFoundError(f"missing fixture: {path}")

            fixture = _load_yaml(path)
            source_id = _create_source(db, fixture)
            units = fixture.get("text_units", [])
            if not isinstance(units, list):
                raise ValueError(f"fixture text_units must be a list: {path}")

            for unit_data in units:
                if not isinstance(unit_data, dict):
                    continue

                canonical_id = unit_data.get("canonical_id")
                if not isinstance(canonical_id, str):
                    continue
                ok, err = validate_canonical_id(canonical_id)
                if not ok:
                    raise ValueError(
                        f"invalid canonical_id in {path}: {canonical_id} ({err})"
                    )

                exists = (
                    db.query(TextUnit)
                    .filter(TextUnit.canonical_id == canonical_id)
                    .first()
                )
                if exists is not None:
                    continue

                if canonical_id.startswith("quran:"):
                    rec = create_quran_ayah(
                        source_id=source_id,
                        surah=int(unit_data["surah"]),
                        ayah=int(unit_data["ayah"]),
                        text=str(unit_data["text"]),
                        surah_name_ar=unit_data.get("surah_name_ar"),
                        surah_name_en=unit_data.get("surah_name_en"),
                        juz=unit_data.get("juz"),
                    )
                elif canonical_id.startswith("hadith:"):
                    rec = create_hadith_item(
                        source_id=source_id,
                        collection=str(unit_data["collection"]),
                        numbering_system=str(unit_data["numbering_system"]),
                        hadith_number=str(unit_data["hadith_number"]),
                        text_ar=str(unit_data["text_ar"]),
                        text_en=unit_data.get("text_en"),
                        book_name=unit_data.get("book_name"),
                        chapter_name=unit_data.get("chapter_name"),
                        chapter_number=unit_data.get("chapter_number"),
                        grading=unit_data.get("grading"),
                        topics=unit_data.get("topics"),
                    )
                else:
                    continue

                db.add(
                    TextUnit(
                        text_unit_id=rec["text_unit_id"],
                        source_id=rec["source_id"],
                        unit_type=rec["unit_type"],
                        canonical_id=rec["canonical_id"],
                        canonical_locator_json=json.dumps(
                            rec["canonical_locator_json"], ensure_ascii=False
                        ),
                        text_canonical=rec["text_canonical"],
                        text_canonical_utf8_sha256=rec["text_canonical_utf8_sha256"],
                    )
                )
            db.commit()

        # Create one evidence span per text unit with evidence_span_id==text_unit_id
        all_units = db.query(TextUnit).all()
        for tu in all_units:
            existing = (
                db.query(EvidenceSpan)
                .filter(EvidenceSpan.evidence_span_id == tu.text_unit_id)
                .first()
            )
            if existing is not None:
                continue

            text_bytes = tu.text_canonical.encode("utf-8")
            if not text_bytes:
                continue

            start_byte = 0
            end_byte = len(text_bytes)
            span = create_span(
                text_unit_id=tu.text_unit_id,
                start_byte=start_byte,
                end_byte=end_byte,
                text_unit_text=tu.text_canonical,
            )
            db.add(
                EvidenceSpan(
                    evidence_span_id=tu.text_unit_id,
                    text_unit_id=tu.text_unit_id,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    snippet_text=span["snippet_text"],
                    snippet_utf8_sha256=span["snippet_hash"],
                    prefix_text=span["prefix"],
                    suffix_text=span["suffix"],
                )
            )
        db.commit()

    db = SessionLocal()
    try:
        _load_text_units(db)
    finally:
        db.close()


def _call_pipeline(query: str) -> dict[str, object]:
    _ensure_import_path()
    from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline

    pipeline = RAGPipeline(RAGConfig())
    return pipeline.query(query)


def _resolve_evidence_local(evidence_span_id: str) -> dict[str, object] | None:
    _ensure_import_path()
    from islam_intelligent.db.engine import SessionLocal
    from islam_intelligent.domain.models import TextUnit
    from islam_intelligent.kg.models import EvidenceSpan

    db = SessionLocal()
    try:
        span = (
            db.query(EvidenceSpan)
            .filter(EvidenceSpan.evidence_span_id == evidence_span_id)
            .first()
        )
        if span is None:
            return None
        tu = (
            db.query(TextUnit)
            .filter(TextUnit.text_unit_id == span.text_unit_id)
            .first()
        )
        if tu is None:
            return None

        snippet_text = span.snippet_text or ""
        return {
            "evidence_span_id": span.evidence_span_id,
            "canonical_id": tu.canonical_id,
            "snippet_text": snippet_text,
            "snippet_hash": span.snippet_utf8_sha256,
            "locator": _maybe_parse_json(tu.canonical_locator_json) or {},
        }
    finally:
        db.close()


def _resolve_evidence_http(
    api_base_url: str, evidence_span_id: str
) -> dict[str, object] | None:
    url = api_base_url.rstrip("/") + f"/evidence/{evidence_span_id}"
    try:
        data = _http_json("GET", url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return data


def _extract_citations(result: dict[str, object]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    statements = result.get("statements")
    if not isinstance(statements, list):
        return citations
    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        cits = stmt.get("citations")
        if not isinstance(cits, list):
            continue
        for c in cits:
            if isinstance(c, dict):
                citations.append(c)
    return citations


def _citation_required_pass(
    case: dict[str, object], result: dict[str, object]
) -> tuple[bool, dict[str, object]]:
    details: dict[str, object] = {}
    if result.get("verdict") != "answer":
        details["reason"] = "not_answer"
        return False, details

    statements = result.get("statements")
    if not isinstance(statements, list) or len(statements) == 0:
        details["reason"] = "no_statements"
        return False, details

    all_ok = True
    found_canonical_ids: set[str] = set()
    missing_statement_citations = 0
    invalid_citations = 0

    for stmt in statements:
        if not isinstance(stmt, dict):
            all_ok = False
            continue

        cits = stmt.get("citations")
        if not isinstance(cits, list) or len(cits) == 0:
            missing_statement_citations += 1
            all_ok = False
            continue

        for c in cits:
            if not isinstance(c, dict):
                invalid_citations += 1
                all_ok = False
                continue

            es_id = c.get("evidence_span_id")
            cid = c.get("canonical_id")
            snippet = c.get("snippet")
            if not isinstance(es_id, str) or not es_id.strip():
                invalid_citations += 1
                all_ok = False
                continue
            if not isinstance(cid, str) or not cid.strip():
                invalid_citations += 1
                all_ok = False
                continue
            if not isinstance(snippet, str) or not snippet.strip():
                invalid_citations += 1
                all_ok = False
                continue
            found_canonical_ids.add(cid)

    required = case.get("required_citations", [])
    required_ok = True
    if isinstance(required, list):
        for req in required:
            if not isinstance(req, str):
                required_ok = False
                continue
            if not _canonical_requirement_satisfied(req, found_canonical_ids):
                required_ok = False
    else:
        required_ok = False

    details.update(
        {
            "missing_statement_citations": missing_statement_citations,
            "invalid_citations": invalid_citations,
            "found_canonical_ids": sorted(found_canonical_ids),
            "required_citations_satisfied": required_ok,
        }
    )
    return bool(all_ok and required_ok), details


def _locator_resolve_pass(
    result: dict[str, object], *, api_base_url: str | None
) -> tuple[bool, dict[str, object]]:
    details: dict[str, object] = {}
    if result.get("verdict") != "answer":
        details["reason"] = "not_answer"
        return False, details

    citations = _extract_citations(result)
    if len(citations) == 0:
        details["reason"] = "no_citations"
        return False, details

    resolved = 0
    mismatched = 0
    bad_hash = 0
    missing = 0
    errors: list[str] = []

    for c in citations:
        es_id = c.get("evidence_span_id")
        cid = c.get("canonical_id")
        if not isinstance(es_id, str) or not es_id.strip():
            missing += 1
            continue
        if not isinstance(cid, str) or not cid.strip():
            missing += 1
            continue

        try:
            if api_base_url:
                ev = _resolve_evidence_http(api_base_url, es_id)
            else:
                ev = _resolve_evidence_local(es_id)
        except Exception as e:
            errors.append(f"resolve_error:{es_id}:{type(e).__name__}")
            ev = None

        if ev is None:
            missing += 1
            continue
        resolved += 1

        ev_cid = ev.get("canonical_id")
        if not isinstance(ev_cid, str) or ev_cid != cid:
            mismatched += 1

        snippet_text = ev.get("snippet_text")
        snippet_hash = ev.get("snippet_hash")
        if (
            isinstance(snippet_text, str)
            and isinstance(snippet_hash, str)
            and snippet_hash
        ):
            if _sha256_utf8(snippet_text) != snippet_hash:
                bad_hash += 1
        else:
            bad_hash += 1

    ok = (
        resolved > 0
        and mismatched == 0
        and bad_hash == 0
        and missing == 0
        and not errors
    )
    details.update(
        {
            "citations_total": len(citations),
            "citations_resolved": resolved,
            "canonical_id_mismatch": mismatched,
            "hash_failures": bad_hash,
            "missing_or_unresolvable": missing,
            "errors": errors,
        }
    )
    return bool(ok), details


def _run_suite(suite: str, *, api_base_url: str | None) -> dict[str, object]:
    suite_path = EVAL_CASES_DIR / f"{suite}.yaml"
    data = _load_yaml(suite_path)
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"suite must contain a 'cases' list: {suite_path}")

    if api_base_url is None:
        _init_db_and_load_fixtures()

    results: list[dict[str, object]] = []

    tp = fp = fn = 0
    answerable_total = 0
    citation_required_pass = 0
    locator_resolve_pass = 0

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case[{idx}] must be a mapping")
        case_id = case.get("case_id", f"case_{idx}")
        query = case.get("query")
        expected_verdict = case.get("expected_verdict")
        if (
            not isinstance(case_id, str)
            or not isinstance(query, str)
            or not isinstance(expected_verdict, str)
        ):
            raise ValueError(f"case[{idx}] missing required fields")

        err: str | None = None
        result: dict[str, object]
        try:
            if api_base_url:
                result = _http_json(
                    "POST", api_base_url.rstrip("/") + "/rag/query", {"query": query}
                )
            else:
                result = _call_pipeline(query)
        except Exception as e:
            result = cast(
                dict[str, object],
                {"verdict": "abstain", "statements": [], "abstain_reason": "error"},
            )
            err = f"query_error:{type(e).__name__}:{e}"

        predicted_verdict = result.get("verdict")
        if predicted_verdict not in ("answer", "abstain"):
            predicted_verdict = "abstain"

        if expected_verdict == "abstain" and predicted_verdict == "abstain":
            tp += 1
        elif expected_verdict == "answer" and predicted_verdict == "abstain":
            fp += 1
        elif expected_verdict == "abstain" and predicted_verdict == "answer":
            fn += 1

        case_out: dict[str, object] = {
            "case_id": case_id,
            "query": query,
            "expected_verdict": expected_verdict,
            "predicted_verdict": predicted_verdict,
            "error": err,
            "abstain_reason": result.get("abstain_reason"),
            "fail_reason": result.get("fail_reason"),
            "retrieved_count": result.get("retrieved_count"),
            "sufficiency_score": result.get("sufficiency_score"),
        }

        if expected_verdict == "answer":
            answerable_total += 1
            cr_ok, cr_details = _citation_required_pass(case, result)
            lr_ok, lr_details = _locator_resolve_pass(result, api_base_url=api_base_url)
            case_out["citation_required_pass"] = cr_ok
            case_out["locator_resolve_pass"] = lr_ok
            case_out["citation_required_details"] = cr_details
            case_out["locator_resolve_details"] = lr_details
            if cr_ok:
                citation_required_pass += 1
            if lr_ok:
                locator_resolve_pass += 1
        else:
            case_out["citation_required_pass"] = None
            case_out["locator_resolve_pass"] = None

        results.append(case_out)

    precision = _safe_div(tp, tp + fp, empty=1.0)
    recall = _safe_div(tp, tp + fn, empty=1.0)
    f1 = _safe_div(2 * precision * recall, precision + recall, empty=0.0)

    metrics: dict[str, object] = {
        "total_cases": len(cases),
        "answerable_total": answerable_total,
        "unanswerable_total": sum(
            1
            for c in cases
            if isinstance(c, dict) and c.get("expected_verdict") == "abstain"
        ),
        "citation_required_pass_rate": _safe_div(
            citation_required_pass, answerable_total, empty=0.0
        ),
        "locator_resolve_pass_rate": _safe_div(
            locator_resolve_pass, answerable_total, empty=0.0
        ),
        "abstention_precision": precision,
        "abstention_recall": recall,
        "abstention_f1": f1,
        "abstention_tp": tp,
        "abstention_fp": fp,
        "abstention_fn": fn,
    }

    taxonomy = _compute_failure_taxonomy(results)

    return {
        "suite": suite,
        "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
        "api_base_url": api_base_url,
        "metrics": metrics,
        "failure_taxonomy": taxonomy,
        "cases": results,
        "suite_metadata": data.get("metadata", {}),
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(_json_dumps(report) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run evaluation suites")
    _ = parser.add_argument(
        "--suite", default="golden", help="Suite name (e.g., golden)"
    )
    _ = parser.add_argument(
        "--output",
        default=str(ROOT / "eval" / "report.json"),
        help="Output JSON report path",
    )
    _ = parser.add_argument(
        "--api-base-url",
        default=None,
        help="If set, POST to {base}/rag/query and resolve via {base}/evidence/{id}",
    )
    _ = parser.add_argument(
        "--assert",
        dest="assertions",
        action="append",
        default=[],
        help=(
            "Assertion gate, e.g. citation_required_pass_rate==1.0 (repeatable). "
            "Quote/escape values containing '>' or '<', e.g. --assert \"abstention_f1>=0.95\""
        ),
    )
    _ = parser.add_argument(
        "--assert-defaults",
        action="store_true",
        help=(
            "Apply default CI thresholds: "
            + ", ".join(DEFAULT_ASSERTS)
            + " (can be combined with --assert)"
        ),
    )

    args_ns = parser.parse_args(argv)
    suite = cast(str, getattr(args_ns, "suite"))
    output = cast(str, getattr(args_ns, "output"))
    api_base_url = cast(str | None, getattr(args_ns, "api_base_url")) or None
    output_path = Path(output)
    raw_assertions_cli = cast(list[str], getattr(args_ns, "assertions"))
    assert_defaults = cast(bool, getattr(args_ns, "assert_defaults"))

    try:
        report = _run_suite(suite, api_base_url=api_base_url)
        _write_report(output_path, report)
    except Exception as e:
        fail_report: dict[str, object] = {
            "suite": suite,
            "generated_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            "api_base_url": api_base_url,
            "error": f"{type(e).__name__}: {e}",
        }
        try:
            _write_report(output_path, fail_report)
        except Exception:
            pass
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        print("FAIL: report.metrics missing", file=sys.stderr)
        return 2

    # Print failure taxonomy (helps CI triage).
    taxonomy = report.get("failure_taxonomy")
    if not isinstance(taxonomy, dict):
        cases_obj = report.get("cases")
        if isinstance(cases_obj, list):
            taxonomy = _compute_failure_taxonomy(
                [c for c in cases_obj if isinstance(c, dict)]
            )
        else:
            taxonomy = {
                "missing_citations": 0,
                "untrusted_sources": 0,
                "citation_verification_failed": 0,
                "other": 0,
            }

    missing_citations = int(taxonomy.get("missing_citations", 0) or 0)
    untrusted_sources = int(taxonomy.get("untrusted_sources", 0) or 0)
    citation_verification_failed = int(
        taxonomy.get("citation_verification_failed", 0) or 0
    )
    other = int(taxonomy.get("other", 0) or 0)

    print("Failure taxonomy (answerable cases):")
    print(f"- missing_citations: {missing_citations}")
    print(f"- untrusted_sources: {untrusted_sources}")
    print(f"- citation_verification_failed: {citation_verification_failed}")
    if other:
        print(f"- other: {other}")

    raw_assertions = list(raw_assertions_cli)
    if assert_defaults:
        raw_assertions = list(DEFAULT_ASSERTS) + raw_assertions

    try:
        assertions = _parse_assertions(raw_assertions)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2

    failed: list[str] = []
    for a in assertions:
        ok, msg = a.check(metrics)
        if not ok:
            failed.append(msg)

    if failed:
        print("ASSERTIONS FAILED:", file=sys.stderr)
        for msg in failed:
            print(f"- {msg}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

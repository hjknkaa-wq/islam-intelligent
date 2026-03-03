#!/usr/bin/env python3
"""CI-style security audit.

Checks:
- Scan repository for accidental secrets (API keys, passwords, tokens, private keys)
- Assert no HTTP DELETE endpoints exist in apps/api/src/islam_intelligent/api/
- Assert data/ is treated as append-only (no delete ops; no write/truncate modes to data/ paths)

Exit codes:
  0 - all checks passed
  1 - one or more checks failed
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import cast


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    check: str
    file: Path
    line: int
    message: str


def _is_binary_chunk(chunk: bytes) -> bool:
    return b"\x00" in chunk


def _read_text_file(path: Path, *, max_bytes: int) -> str | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > max_bytes:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if _is_binary_chunk(data[:8192]):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _iter_repo_files(root: Path) -> Iterable[Path]:
    exclude_dir_names = {
        ".git",
        ".sisyphus",
        ".venv",
        "venv",
        "node_modules",
        ".next",
        ".turbo",
        ".cache",
        "coverage",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
    }
    exclude_exts = {
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".dll",
        ".exe",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".pdf",
        ".zip",
        ".7z",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".sqlite",
        ".db",
    }

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place.
        dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]
        base = Path(dirpath)
        for name in filenames:
            p = base / name
            if p.suffix.lower() in exclude_exts:
                continue
            yield p


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _redact(value: str) -> str:
    v = value.strip().strip("\"'")
    if len(v) <= 8:
        return "<redacted>"
    return v[:4] + "..." + v[-4:]


def _looks_like_placeholder_secret(raw_value: str) -> bool:
    v = raw_value.strip().strip("\"'").lower()
    if not v:
        return True

    if v in {
        "xxx",
        "xxxx",
        "token",
        "secret",
        "password",
        "api_key",
        "apikey",
        "openai_api_key",
    }:
        return True

    normalized = re.sub(r"[^a-z0-9]", "", v)
    placeholder_markers = (
        "your",
        "replace",
        "example",
        "sample",
        "dummy",
        "placeholder",
        "changeme",
    )
    if any(marker in normalized for marker in placeholder_markers):
        return True

    return False


def _scan_for_secrets(*, root: Path, max_file_bytes: int) -> list[Finding]:
    # NOTE: skip this audit script to avoid self-matches.
    self_path = (root / "scripts" / "security_audit.py").resolve()

    # High-confidence patterns.
    patterns: list[tuple[str, re.Pattern[str]]] = [
        (
            "private_key_block",
            re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----"),
        ),
        ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
        ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
        ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
        ("github_pat_v2", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
        ("slack_token", re.compile(r"\bxox(?:b|p|a|r|s)-[0-9A-Za-z-]{10,}\b")),
        (
            "jwt_like",
            re.compile(
                r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
            ),
        ),
    ]

    # Generic assignment patterns with heuristics (reduce false positives).
    # Only match *string literal* values to avoid triggering on object keys / code.
    generic_quoted = re.compile(
        r"(?i)\b("
        + r"api[_-]?key|api[_-]?token|access[_-]?token|refresh[_-]?token|"
        + r"password|passwd|pwd|secret|client[_-]?secret|bearer"
        + r")\b\s*(?:=|:)\s*([\"'])(.{8,256}?)\2"
    )
    env_line = re.compile(
        r"(?im)^(?:export\s+)?("
        + r"api[_-]?key|api[_-]?token|access[_-]?token|refresh[_-]?token|"
        + r"password|passwd|pwd|secret|client[_-]?secret|bearer"
        + r")\s*=\s*([^\s#]{8,256})\s*$"
    )

    placeholder = re.compile(
        r"(?i)\b(changeme|change-me|example|sample|dummy|placeholder|your[_-]?(?:key|token|password|secret))\b"
    )

    findings: list[Finding] = []
    for p in _iter_repo_files(root):
        try:
            if p.resolve() == self_path:
                continue
        except OSError:
            continue

        text = _read_text_file(p, max_bytes=max_file_bytes)
        if text is None:
            continue

        for name, rx in patterns:
            for m in rx.finditer(text):
                line = _line_number(text, m.start())
                findings.append(
                    Finding(
                        check="secrets",
                        file=p,
                        line=line,
                        message=f"Possible secret ({name}): {_redact(m.group(0))}",
                    )
                )

        for m in generic_quoted.finditer(text):
            key = (m.group(1) or "").lower()
            raw_val = (m.group(3) or "").strip()
            if not raw_val:
                continue
            if placeholder.search(raw_val):
                continue
            if _looks_like_placeholder_secret(raw_val):
                continue
            # Heuristics: require some entropy-ish variety.
            if len(raw_val) < 12:
                continue
            has_alpha = any(c.isalpha() for c in raw_val)
            has_digit = any(c.isdigit() for c in raw_val)
            has_symbol = any((not c.isalnum()) for c in raw_val)
            if sum([has_alpha, has_digit, has_symbol]) < 2:
                continue
            line = _line_number(text, m.start())
            findings.append(
                Finding(
                    check="secrets",
                    file=p,
                    line=line,
                    message=f"Possible secret assignment ({key}): {_redact(raw_val)}",
                )
            )

        # Allow unquoted KEY=VALUE detection in env-like files only.
        if p.name.startswith(".env") or p.suffix.lower() in {".env", ".ini"}:
            for m in env_line.finditer(text):
                key = (m.group(1) or "").lower()
                raw_val = (m.group(2) or "").strip()
                if not raw_val:
                    continue
                if placeholder.search(raw_val):
                    continue
                if _looks_like_placeholder_secret(raw_val):
                    continue
                if len(raw_val) < 12:
                    continue
                has_alpha = any(c.isalpha() for c in raw_val)
                has_digit = any(c.isdigit() for c in raw_val)
                has_symbol = any((not c.isalnum()) for c in raw_val)
                if sum([has_alpha, has_digit, has_symbol]) < 2:
                    continue
                line = _line_number(text, m.start())
                findings.append(
                    Finding(
                        check="secrets",
                        file=p,
                        line=line,
                        message=f"Possible env secret ({key}): {_redact(raw_val)}",
                    )
                )

    return findings


def _simulate_secret_detection() -> tuple[bool, str]:
    google_key = "AIza" + ("A" * 35)
    ghp_token = "ghp_" + ("A" * 36)
    sample = "\n".join(
        [
            'password = "CorrectHorseBatteryStaple123!"',
            f'api_key = "{google_key}"',
            f'token = "{ghp_token}"',
        ]
    )

    hits = 0
    high_conf = [
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        re.compile(r"(?i)\bpassword\b\s*(?:=|:)\s*([\"'])(.{8,256}?)\1"),
    ]
    for rx in high_conf:
        if rx.search(sample):
            hits += 1
    if hits >= 2:
        return True, f"[OK] --simulate-secret: detector triggered ({hits} pattern(s))"
    return False, "[FAIL] --simulate-secret: detector did not trigger as expected"


def _scan_for_delete_endpoints(*, api_root: Path, max_file_bytes: int) -> list[Finding]:
    findings: list[Finding] = []
    if not api_root.exists():
        findings.append(
            Finding(
                check="no_delete_endpoints",
                file=api_root,
                line=1,
                message="API directory not found",
            )
        )
        return findings

    decorator_delete = re.compile(r"^\s*@\s*(?:router|app)\.delete\s*\(", re.I | re.M)
    decorator_api_route_delete = re.compile(
        r"^\s*@\s*(?:router|app)\.api_route\s*\(.*?methods\s*=\s*\[[^\]]*\b['\"]DELETE['\"]",
        re.I | re.M,
    )
    add_api_route_delete = re.compile(
        r"\b(?:router|app)\.add_api_route\s*\(.*?methods\s*=\s*\[[^\]]*\b['\"]DELETE['\"]",
        re.I | re.S,
    )

    for p in api_root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        text = _read_text_file(p, max_bytes=max_file_bytes)
        if text is None:
            continue

        for rx, label in [
            (decorator_delete, "@router.delete/@app.delete"),
            (decorator_api_route_delete, "@router.api_route(... methods=[DELETE])"),
            (add_api_route_delete, "add_api_route(... methods=[DELETE])"),
        ]:
            for m in rx.finditer(text):
                line = _line_number(text, m.start())
                findings.append(
                    Finding(
                        check="no_delete_endpoints",
                        file=p,
                        line=line,
                        message=f"DELETE endpoint definition found ({label})",
                    )
                )
    return findings


def _scan_data_append_only(*, root: Path, max_file_bytes: int) -> list[Finding]:
    findings: list[Finding] = []
    data_dir = root / "data"
    curated_dir = data_dir / "curated"
    raw_dir = data_dir / "raw"

    if not data_dir.exists():
        findings.append(
            Finding(
                check="data_append_only",
                file=data_dir,
                line=1,
                message="data/ directory missing",
            )
        )
        return findings
    if not curated_dir.exists():
        findings.append(
            Finding(
                check="data_append_only",
                file=curated_dir,
                line=1,
                message="data/curated/ directory missing",
            )
        )

    # Code-level guardrails: forbid delete ops and write/truncate modes targeting data/.
    delete_ops = re.compile(
        r"\b(?:os\.(?:remove|unlink)|shutil\.rmtree|Path\([^\)]*\)\.unlink|\.unlink\(|\.rmdir\()\b"
    )
    open_write = re.compile(
        r"\bopen\(\s*[rfbu]*[\"']([^\"']*data[\\/][^\"']*)[\"']\s*,\s*[\"']([^\"']+)[\"']"
    )
    path_write = re.compile(
        r"\bPath\(\s*[\"']([^\"']*data[\\/][^\"']*)[\"']\s*\)\.(write_text|write_bytes)\("
    )

    for p in _iter_repo_files(root):
        if p.suffix.lower() != ".py":
            continue
        text = _read_text_file(p, max_bytes=max_file_bytes)
        if text is None:
            continue

        # Delete ops mentioning data/ on the same line.
        for i, line_text in enumerate(text.splitlines(), start=1):
            if "data/" in line_text or "data\\" in line_text:
                if delete_ops.search(line_text):
                    findings.append(
                        Finding(
                            check="data_append_only",
                            file=p,
                            line=i,
                            message="Delete operation references data/ (append-only violation)",
                        )
                    )

        for m in open_write.finditer(text):
            file_path = m.group(1)
            mode = m.group(2)
            # Allow append and exclusive-create; forbid truncating/overwriting modes.
            bad = any(x in mode for x in ["w", "+"])
            if bad and ("a" not in mode) and ("x" not in mode):
                findings.append(
                    Finding(
                        check="data_append_only",
                        file=p,
                        line=_line_number(text, m.start()),
                        message=f"open() writes to data/ with mode '{mode}' ({file_path})",
                    )
                )

        for m in path_write.finditer(text):
            findings.append(
                Finding(
                    check="data_append_only",
                    file=p,
                    line=_line_number(text, m.start()),
                    message=f"Path.{m.group(2)}() writes to data/ ({m.group(1)})",
                )
            )

    # If raw_dir exists, ensure it is a directory.
    if raw_dir.exists() and not raw_dir.is_dir():
        findings.append(
            Finding(
                check="data_append_only",
                file=raw_dir,
                line=1,
                message="data/raw exists but is not a directory",
            )
        )

    return findings


def _format_findings(findings: list[Finding]) -> str:
    lines: list[str] = []
    for f in findings:
        rel = f.file
        try:
            rel = f.file.relative_to(ROOT)
        except Exception:
            pass
        lines.append(f"- [{f.check}] {rel}:{f.line} {f.message}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Security audit (secrets + API + data invariants)"
    )
    _ = parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=1_000_000,
        help="Max bytes to scan per file (default: 1,000,000)",
    )
    _ = parser.add_argument(
        "--simulate-secret",
        action="store_true",
        help="Run a self-test to ensure secret detection triggers",
    )
    args = parser.parse_args()

    max_file_bytes = cast(int, args.max_file_bytes)
    simulate_secret = cast(bool, args.simulate_secret)

    if simulate_secret:
        ok, msg = _simulate_secret_detection()
        print(msg)
        if not ok:
            return 1

    all_findings: list[Finding] = []
    all_findings.extend(_scan_for_secrets(root=ROOT, max_file_bytes=max_file_bytes))
    api_dir = ROOT / "apps" / "api" / "src" / "islam_intelligent" / "api"
    all_findings.extend(
        _scan_for_delete_endpoints(api_root=api_dir, max_file_bytes=max_file_bytes)
    )
    all_findings.extend(
        _scan_data_append_only(root=ROOT, max_file_bytes=max_file_bytes)
    )

    if all_findings:
        print(
            f"[FAIL] Security audit failed ({len(all_findings)} issue(s))",
            file=sys.stderr,
        )
        print(_format_findings(all_findings), file=sys.stderr)
        return 1

    print("[OK] Security audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

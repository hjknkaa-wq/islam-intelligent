#!/usr/bin/env python3
"""Single entrypoint for all verification.

Runs checks in a fixed order and exits non-zero on the first failure.
Emits JSONL (one JSON object per line) to stdout for machine readability.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO, cast


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
DEFAULT_EVIDENCE_PATH = ROOT / ".sisyphus" / "evidence" / "task-29-verify-all.txt"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_line(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True)


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


@dataclass(frozen=True)
class Step:
    step_id: str
    title: str
    cmd: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None
    optional: bool = False


class Emitter:
    def __init__(self, *, evidence_path: Path | None) -> None:
        self._evidence_path: Path | None = evidence_path
        self._fh: TextIO | None = None

        if self._evidence_path is not None:
            self._evidence_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self._evidence_path.open("w", encoding="utf-8")

    def emit(self, event: dict[str, object]) -> None:
        line = _json_line(event)
        _ = sys.stdout.write(line + "\n")
        _ = sys.stdout.flush()
        if self._fh is not None:
            _ = self._fh.write(line + "\n")
            _ = self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _tail(text: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _run_step(emitter: Emitter, step: Step, *, stdout_tail_chars: int) -> int:
    started_ts = _utc_now_iso()
    start_time = time.monotonic()
    emitter.emit(
        {
            "type": "step_start",
            "ts": started_ts,
            "step": step.step_id,
            "title": step.title,
            "cmd": step.cmd,
            "cwd": str(step.cwd) if step.cwd else str(ROOT),
            "optional": step.optional,
        }
    )

    env = os.environ.copy()
    if step.env:
        env.update(step.env)

    try:
        proc = subprocess.run(
            step.cmd,
            cwd=str(step.cwd or ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        emitter.emit(
            {
                "type": "step_end",
                "ts": _utc_now_iso(),
                "step": step.step_id,
                "status": "fail",
                "exit_code": 127,
                "duration_ms": duration_ms,
                "error": f"FileNotFoundError: {e}",
            }
        )
        return 127
    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        emitter.emit(
            {
                "type": "step_end",
                "ts": _utc_now_iso(),
                "step": step.step_id,
                "status": "fail",
                "exit_code": 1,
                "duration_ms": duration_ms,
                "error": f"{type(e).__name__}: {e}",
            }
        )
        return 1

    duration_ms = int((time.monotonic() - start_time) * 1000)
    exit_code = int(proc.returncode)
    status = "pass" if exit_code == 0 else "fail"

    emitter.emit(
        {
            "type": "step_end",
            "ts": _utc_now_iso(),
            "step": step.step_id,
            "status": status,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "stdout_tail": _tail(proc.stdout or "", max_chars=stdout_tail_chars),
            "stderr_tail": _tail(proc.stderr or "", max_chars=stdout_tail_chars),
            "stdout_truncated": bool(proc.stdout)
            and len(proc.stdout) > stdout_tail_chars,
            "stderr_truncated": bool(proc.stderr)
            and len(proc.stderr) > stdout_tail_chars,
        }
    )
    return exit_code


def _build_steps(*, db_path: Path, check_invariants: bool, e2e: bool) -> list[Step]:
    db_path = db_path.resolve()
    db_url = _sqlite_url(db_path)

    steps: list[Step] = []

    if check_invariants:
        steps.append(
            Step(
                step_id="db_init",
                title="DB init (migrations)",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "db_init.py"),
                    "--sqlite",
                    str(db_path),
                ],
            )
        )
    else:
        steps.append(
            Step(
                step_id="db_reset_seed",
                title="DB reset + seed",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "dev_reset_and_seed.py"),
                    "--db-path",
                    str(db_path),
                ],
            )
        )

        steps.append(
            Step(
                step_id="pytest",
                title="pytest",
                cmd=[sys.executable, "-m", "pytest"],
                cwd=ROOT / "apps" / "api",
            )
        )

        steps.append(
            Step(
                step_id="eval",
                title="eval thresholds (--assert-defaults)",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "run_eval.py"),
                    "--assert-defaults",
                ],
            )
        )

        if e2e:
            steps.append(
                Step(
                    step_id="ui_e2e",
                    title="UI e2e (playwright)",
                    cmd=["npx", "playwright", "test"],
                    cwd=ROOT / "apps" / "ui",
                    optional=True,
                )
            )

    steps.extend(
        [
            Step(
                step_id="verify_provenance",
                title="provenance integrity",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "verify_provenance.py"),
                    "--check",
                    "no_broken_links",
                    "--db-url",
                    db_url,
                ],
            ),
            Step(
                step_id="verify_manifest",
                title="source manifests",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "verify_manifest.py"),
                    "--all",
                    "--db-path",
                    str(db_path),
                ],
            ),
            Step(
                step_id="verify_hash_chain",
                title="provenance hash chain",
                cmd=[
                    sys.executable,
                    str(ROOT / "scripts" / "verify_hash_chain.py"),
                    "--db-url",
                    db_url,
                ],
            ),
        ]
    )
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all verification checks")
    _ = parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    _ = parser.add_argument(
        "--check-invariants",
        action="store_true",
        help="Quick checks only (skip pytest/eval/e2e; run DB init + integrity verifications)",
    )
    _ = parser.add_argument(
        "--e2e",
        action="store_true",
        help="Include UI e2e tests (npx playwright test)",
    )
    _ = parser.add_argument(
        "--evidence-path",
        default=str(DEFAULT_EVIDENCE_PATH),
        help=f"Write JSONL transcript to this path (default: {DEFAULT_EVIDENCE_PATH})",
    )
    _ = parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Do not write evidence transcript file",
    )
    _ = parser.add_argument(
        "--stdout-tail-chars",
        type=int,
        default=8000,
        help="Max chars of each step stdout/stderr to include (default: 8000)",
    )
    args_ns = parser.parse_args(argv)
    db_path_raw = cast(str, getattr(args_ns, "db_path"))
    check_invariants = cast(bool, getattr(args_ns, "check_invariants"))
    e2e = cast(bool, getattr(args_ns, "e2e"))
    evidence_path_raw = cast(str, getattr(args_ns, "evidence_path"))
    no_evidence = cast(bool, getattr(args_ns, "no_evidence"))
    stdout_tail_chars = int(cast(int, getattr(args_ns, "stdout_tail_chars")))

    db_path = Path(str(db_path_raw)).expanduser()
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()

    evidence_path: Path | None = None
    if not bool(no_evidence):
        evidence_path = Path(str(evidence_path_raw)).expanduser()
        if not evidence_path.is_absolute():
            evidence_path = (Path.cwd() / evidence_path).resolve()

    emitter = Emitter(evidence_path=evidence_path)
    started = _utc_now_iso()

    steps = _build_steps(
        db_path=db_path,
        check_invariants=bool(check_invariants),
        e2e=bool(e2e),
    )

    emitter.emit(
        {
            "type": "run_start",
            "ts": started,
            "argv": list(sys.argv if argv is None else [sys.argv[0], *argv]),
            "root": str(ROOT),
            "db_path": str(db_path),
            "check_invariants": bool(check_invariants),
            "e2e": bool(e2e),
        }
    )

    results: list[dict[str, object]] = []
    exit_code = 0
    failed_step: str | None = None

    try:
        for step in steps:
            code = _run_step(emitter, step, stdout_tail_chars=int(stdout_tail_chars))
            results.append(
                {
                    "step": step.step_id,
                    "title": step.title,
                    "exit_code": int(code),
                }
            )
            if code != 0:
                exit_code = int(code)
                failed_step = step.step_id
                break
    finally:
        emitter.emit(
            {
                "type": "run_end",
                "ts": _utc_now_iso(),
                "status": "pass" if exit_code == 0 else "fail",
                "exit_code": exit_code,
                "failed_step": failed_step,
                "results": results,
            }
        )
        emitter.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

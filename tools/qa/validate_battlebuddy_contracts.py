"""Validate BattleBuddy Contract v1 JSON envelopes.

Phase 3: Validation & QA Integration.

- Emits clear, schema-referenced failures.
- Does NOT auto-fix anything.

Validation modes:
- Full JSON Schema Draft 2020-12 validation is REQUIRED. This check fails if
    the `jsonschema` package (with Draft 2020-12 support) is not available.

Exit codes:
  0 - all contract envelopes validated (or basic validation passed)
  1 - one or more contract envelopes failed validation
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class Finding:
    path: str
    error: str


DEFAULT_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "OUTPUTS",
}


_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _repo_root() -> Path:
    # tools/qa/validate_battlebuddy_contracts.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _iter_contract_files(root: Path, *, skip_dirs: set[str]) -> Iterable[Path]:
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for name in filenames:
            if name.lower().endswith(".contract.v1.json"):
                yield Path(dirpath) / name


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _format_json_path(segments: Iterable[object]) -> str:
    parts: List[str] = []
    for s in segments:
        if isinstance(s, int):
            parts.append(f"[{s}]")
        else:
            if not parts:
                parts.append(str(s))
            else:
                parts.append(f".{s}")
    return "".join(parts) if parts else "<root>"


def _basic_validate_contract(doc: Any, *, file_path: Path) -> List[str]:
    errs: List[str] = []

    if not isinstance(doc, dict):
        return ["Document must be a JSON object."]

    allowed_top = {"contract_id", "schema_version", "timestamp", "input", "output"}
    extra = sorted(set(doc.keys()) - allowed_top)
    if extra:
        errs.append(f"Unexpected top-level keys: {extra}")

    if doc.get("contract_id") != "AUERNYX.BattleBuddy.Contract.v1":
        errs.append("contract_id must equal 'AUERNYX.BattleBuddy.Contract.v1'")

    if doc.get("schema_version") != 1:
        errs.append("schema_version must equal 1")

    ts = doc.get("timestamp")
    if not isinstance(ts, str) or not _TIMESTAMP_RE.match(ts):
        errs.append("timestamp must be ISO-8601 (e.g. 2025-12-31T00:00:00Z)")

    inp = doc.get("input")
    if not isinstance(inp, dict):
        errs.append("input must be an object")

    if "output" in doc and doc.get("output") is not None and not isinstance(doc.get("output"), dict):
        errs.append("output (when present) must be an object")

    # Some quick structural checks that commonly bite people.
    if isinstance(inp, dict):
        if "stage" not in inp:
            errs.append("input.stage is required")
        if "case" not in inp:
            errs.append("input.case is required")

    return errs


def _get_full_schema_validator(schema_path: Path):
    try:
        from jsonschema.validators import Draft202012Validator  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Missing required dependency 'jsonschema' with Draft 2020-12 support. "
            "Install it in the repo venv (e.g., pip install -r tools/qa/requirements.txt)."
        ) from e

    schema = _load_json(schema_path)
    return Draft202012Validator(schema)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate BattleBuddy Contract v1 envelopes.")
    parser.add_argument(
        "--root",
        default=str(_repo_root()),
        help="Root folder to scan (default: repo root)",
    )
    parser.add_argument(
        "--include-outputs",
        action="store_true",
        help="Include OUTPUTS/ in scanning (default: skipped)",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=50,
        help="Max failures to print (default: 50)",
    )
    parser.add_argument(
        "--schema",
        default=str(_repo_root() / "AGENTS" / "SCHEMAS" / "BattleBuddy_Contract_v1.schema.json"),
        help="Path to BattleBuddy Contract v1 schema",
    )

    args = parser.parse_args(list(argv))

    root = Path(args.root)
    schema_path = Path(args.schema)

    skip_dirs = set(DEFAULT_SKIP_DIRS)
    if args.include_outputs:
        skip_dirs.discard("OUTPUTS")

    if not schema_path.exists():
        print(f"ERROR: Missing schema: {schema_path}")
        return 1

    try:
        validator = _get_full_schema_validator(schema_path)
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"Schema required: {schema_path}")
        return 1

    findings: List[Finding] = []
    total = 0

    for path in _iter_contract_files(root, skip_dirs=skip_dirs):
        total += 1
        try:
            doc = _load_json(path)
        except Exception as e:  # noqa: BLE001
            findings.append(Finding(path=str(path), error=f"JSON parse error: {e}"))
            continue

        errors = sorted(validator.iter_errors(doc), key=lambda er: list(er.absolute_path))
        for er in errors:
            at = _format_json_path(er.absolute_path)
            findings.append(
                Finding(
                    path=str(path),
                    error=f"Schema violation at {at}: {er.message} (schema: {schema_path})",
                )
            )

    print(f"battlebuddy contract files scanned: {total}")
    print("validation mode: full (jsonschema Draft 2020-12)")

    print(f"contract validation findings: {len(findings)}")

    for f in findings[: max(args.max_failures, 0)]:
        print(f"FAIL {f.path}")
        print(f"  {f.error}")

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

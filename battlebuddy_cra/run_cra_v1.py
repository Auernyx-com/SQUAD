from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema


@dataclass(frozen=True)
class CraPaths:
    repo_root: Path
    schema_in: Path
    schema_out: Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(schema_path: Path, instance: object) -> None:
    schema = _load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(instance)


def _repo_root_from_here() -> Path:
    # battlebuddy_cra/run_cra_v1.py -> repo root
    return Path(__file__).resolve().parents[1]


def _paths() -> CraPaths:
    root = _repo_root_from_here()
    return CraPaths(
        repo_root=root,
        schema_in=root / "battlebuddy_cra" / "schema" / "cra.schema.json",
        schema_out=root / "battlebuddy_cra" / "schema" / "cra_output.schema.json",
    )


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Path sanitizers — break the argparse-argument → file-operation data flow
# so that user-supplied paths are validated before any I/O occurs.
# ---------------------------------------------------------------------------

_ALLOWED_JSON_SUFFIX = ".json"
_ALLOWED_TEXT_SUFFIXES = {".txt", ".md", ".json"}


def _require_json_path(raw: str) -> Path:
    """Validate a user-supplied path intended for a JSON file.

    Resolves the path and checks the extension.  Raises SystemExit for
    any value that would not be a .json file, preventing user-controlled
    strings from flowing into file operations without a validation gate.
    """
    resolved = Path(raw).expanduser().resolve()
    if resolved.suffix.lower() != _ALLOWED_JSON_SUFFIX:
        raise SystemExit(f"Expected a .json file path, got: {raw!r}")
    return resolved


def _require_text_path(raw: str) -> Path:
    """Validate a user-supplied path intended for a plain-text or markdown file."""
    resolved = Path(raw).expanduser().resolve()
    if resolved.suffix.lower() not in _ALLOWED_TEXT_SUFFIXES:
        raise SystemExit(f"Expected a text/markdown/json file path (.txt, .md, .json), got: {raw!r}")
    return resolved


def _load_handshake_module(repo_root: Path):
    """Load BattleBuddyHandshake without requiring package installs.

    This is intentionally a dynamic import to keep the repo drop-in: callers
    can run CRA without having to install/packaging-wire the agents folder.
    """

    hs_path = repo_root / "AGENTS" / "CORE" / "BATTLEBUDDY" / "bb_handshake_v1.py"
    if not hs_path.exists():
        raise FileNotFoundError(f"Handshake module not found at: {hs_path}")

    spec = importlib.util.spec_from_file_location("bb_handshake_v1", str(hs_path))
    if spec is None or spec.loader is None:
        raise ImportError("Failed to create import spec for handshake module")

    mod = importlib.util.module_from_spec(spec)
    sys.modules["bb_handshake_v1"] = mod
    spec.loader.exec_module(mod)

    if not hasattr(mod, "BattleBuddyHandshake") or not hasattr(mod, "BBOutput"):
        raise ImportError("Handshake module missing expected exports: BattleBuddyHandshake / BBOutput")

    return mod


def _cra_handshake_questions() -> list[str]:
    # Schema-aligned questionnaire for battlebuddy_cra/schema/cra.schema.json.
    # Questions only: no recommendations, no predictions, no medical interpretation.
    return [
        "CRA input: what is your current claim status (not_filed, filed_pending, denied, appeal_pending, unknown)?",
        "Evidence presence (tri-state yes/no/unknown): do you have service records available?",
        "Evidence presence (tri-state yes/no/unknown): do you have current medical documentation you already possess (presence only; no condition names/details)?",
        "Evidence presence (tri-state yes/no/unknown): do you have a nexus opinion letter/opinion (presence only)?",
        "Evidence presence (tri-state yes/no/unknown): do you have any buddy/lay statements (presence only)?",
        "Evidence presence (tri-state yes/no/unknown): do you have continuity evidence (presence only; e.g., records showing ongoing issue over time, without quoting medical details)?",
        "Administrative context: what is your representation status (none, vso, attorney, unknown)?",
        "Administrative context (tri-state yes/no/unknown): have you received prior VA decision letters?",
        "Administrative context: what appeal lane is used (none, hlr, supplemental, board, unknown)?",
        "Barriers: which apply (difficulty_obtaining_records, confusion_about_process, missed_deadlines, lack_of_representation, conflicting_information_received)?",
        "Safety check: does the text include medical/clinical details or record interpretation requests that would require CRA refusal (yes/no)?",
    ]


def _print_handshake(text: str, *, repo_root: Path, output_format: str, quiet: bool) -> None:
    hs = _load_handshake_module(repo_root)
    bb = hs.BattleBuddyHandshake()
    out = bb.generate(text)

    # Start output on a fresh line to avoid long command-line wrap artifacts
    # bleeding into the first printed line in some terminals/capture UIs.
    print("")

    if not quiet:
        print(out.observations)

        if out.refused:
            if out.refusal_reason:
                print(f"RefusalReason: {out.refusal_reason}")
            if out.flags:
                print(f"Flags: {', '.join([str(x) for x in out.flags])}")
            print("")

    if output_format == "cra":
        print("Questions (CRA schema-aligned):" if not quiet else "Questions:")
        for q in _cra_handshake_questions():
            print(f"- {q}")
        return

    if out.questions:
        print("Questions:")
        for q in out.questions:
            print(f"- {q}")

    if out.reflective_enabled and out.reflective_questions:
        print("\nReflective questions (optional):")
        for q in out.reflective_questions:
            print(f"- {q}")


def _case_dir_from_case_id(repo_root: Path, case_id: str) -> Path:
    return repo_root / "CASES" / "ACTIVE" / case_id


def _default_input_path(case_dir: Path) -> Path:
    return case_dir / "ARTIFACTS" / "CRA" / "cra.input.v1.json"


def _default_output_path(case_dir: Path) -> Path:
    return case_dir / "ARTIFACTS" / "CRA" / "cra.report.v1.json"


def _avoid_collision(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    n = 1
    while True:
        candidate = parent / f"{stem}__{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1
        if n > 999:
            raise RuntimeError(f"Collision limit exceeded for output path: {path}")


def _presence_from_yes_no_unknown(value: str) -> str:
    if value == "yes":
        return "present"
    if value == "no":
        return "missing"
    return "unknown"


def _add_gap(gaps: List[Dict[str, Any]], gap: str, presence: str, rationale: str) -> None:
    gaps.append({"gap": gap, "presence": presence, "safe_rationale": rationale})


def _build_ok_report(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence = input_payload.get("evidence_presence") or {}
    admin = input_payload.get("administrative_context") or {}

    gaps: List[Dict[str, Any]] = []

    service_records = str(evidence.get("service_records_available"))
    diagnosis_docs = str(evidence.get("current_diagnosis_documentation_exists"))
    nexus = str(evidence.get("nexus_opinion_exists"))
    lay = str(evidence.get("lay_statements_present"))
    continuity = str(evidence.get("continuity_evidence_present"))

    prior_decisions = str(admin.get("prior_va_decisions_received"))
    appeal_lane = str(admin.get("appeal_lane_used"))
    rep = str(admin.get("representation_status"))

    # Evidence gaps
    p = _presence_from_yes_no_unknown(service_records)
    if p != "present":
        _add_gap(
            gaps,
            "service_records_missing_or_unknown",
            p,
            "Service records availability is not confirmed; record requests may be needed to verify presence.",
        )

    p = _presence_from_yes_no_unknown(diagnosis_docs)
    if p != "present":
        _add_gap(
            gaps,
            "current_diagnosis_docs_missing_or_unknown",
            p,
            "Current medical documentation is marked missing/unknown; CRA does not evaluate content, only presence.",
        )

    p = _presence_from_yes_no_unknown(nexus)
    if p != "present":
        _add_gap(
            gaps,
            "nexus_opinion_missing_or_unknown",
            p,
            "A nexus opinion is marked missing/unknown; CRA does not evaluate content, only presence.",
        )

    p = _presence_from_yes_no_unknown(lay)
    if p != "present":
        _add_gap(
            gaps,
            "lay_statements_missing_or_unknown",
            p,
            "Lay statements are marked missing/unknown; these can support timelines and observed impacts without medical detail.",
        )

    p = _presence_from_yes_no_unknown(continuity)
    if p != "present":
        _add_gap(
            gaps,
            "continuity_evidence_missing_or_unknown",
            p,
            "Continuity evidence is marked missing/unknown; CRA does not interpret records, only maps presence.",
        )

    # Admin gaps
    p = _presence_from_yes_no_unknown(prior_decisions)
    if p != "present":
        _add_gap(
            gaps,
            "prior_decision_missing_or_unknown",
            p,
            "Prior VA decision letters are marked missing/unknown; keep decision letters for deadlines and stated reasons.",
        )

    if appeal_lane == "unknown":
        _add_gap(
            gaps,
            "appeal_lane_unknown",
            "unknown",
            "Appeal lane is unknown; lane choice can affect deadlines and required forms.",
        )

    if rep in {"none", "unknown"}:
        presence = "missing" if rep == "none" else "unknown"
        _add_gap(
            gaps,
            "representation_missing_or_unknown",
            presence,
            "Representation status is missing/unknown; accredited representation can reduce process friction.",
        )

    barriers = list(input_payload.get("veteran_reported_barriers") or [])

    if gaps:
        readiness = "incomplete_common_gaps"
    elif barriers:
        readiness = "administrative_barriers_detected"
    else:
        readiness = "procedurally_ready_verification_pending"

    patterns: List[str] = []
    if any(g["gap"] == "nexus_opinion_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        patterns.append("missing_nexus_is_common_denial_reason")
    if any(g["gap"] == "continuity_evidence_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        patterns.append("continuity_gaps_can_block_service_connection")
    if any(g["gap"] == "service_records_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        patterns.append("service_records_requests_can_take_time")
    if any(g["gap"] == "appeal_lane_unknown" for g in gaps):
        patterns.append("appeal_lane_choice_has_deadlines")
    if any(g["gap"] == "representation_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        patterns.append("representation_can_reduce_process_friction")

    # Dedupe while preserving order
    patterns = list(dict.fromkeys(patterns))

    next_steps: List[Dict[str, Any]] = []

    def add_step(step: str, notes: Optional[str] = None) -> None:
        if any(s.get("step") == step for s in next_steps):
            return
        item: Dict[str, Any] = {"step": step}
        if notes:
            item["notes"] = notes
        next_steps.append(item)

    if any(g["gap"] == "service_records_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        add_step("request_service_records", "Confirm whether service records can be obtained via official channels.")

    if any(g["gap"] == "prior_decision_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        add_step("obtain_prior_va_decision_letters", "Keep decision letters for timelines, deadlines, and stated reasons.")

    if any(g["gap"] == "representation_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        add_step("seek_accredited_representation", "Use accredited options (VSO/attorney) and track who is the POA.")

    if any(g["gap"] == "appeal_lane_unknown" for g in gaps):
        add_step("confirm_appeal_lane_and_deadlines", "Confirm lane choice and deadlines in writing; avoid medical details.")

    if any(g["gap"] == "lay_statements_missing_or_unknown" and g["presence"] != "present" for g in gaps):
        add_step("collect_lay_statements", "Focus on timelines/observable impacts; avoid diagnosis labels.")

    add_step("build_one_page_timeline", "Write key dates and outcomes; avoid medical details.")

    return {
        "module": "battlebuddy.cra",
        "version": "1.0.0",
        "created_at": _now_iso(),
        "status": "ok",
        "summary": {
            "readiness": readiness,
            "notes": ["This is a process-only gap map; it does not assess eligibility or outcomes."],
        },
        "gap_map": gaps,
        "procedural_patterns": patterns,
        "next_safe_steps": next_steps[:10],
    }


def _build_refusal_report() -> Dict[str, Any]:
    return {
        "module": "battlebuddy.cra",
        "version": "1.0.0",
        "created_at": _now_iso(),
        "status": "refused",
        "refusal": {
            "reason_codes": ["unsafe_content_detected"],
            "message": "I can’t analyze medical records or determine service connection. I can help identify common documentation or process gaps that affect claims outcomes.",
        },
    }


def run(*, input_path: Path) -> Dict[str, Any]:
    paths = _paths()

    payload_obj = _load_json(input_path)
    if not isinstance(payload_obj, dict):
        raise ValueError("CRA input must be a JSON object")

    _validate(paths.schema_in, payload_obj)

    unsafe = payload_obj.get("unsafe_content_detected")
    refused = bool(isinstance(unsafe, dict) and unsafe.get("present") is True)

    out = _build_refusal_report() if refused else _build_ok_report(payload_obj)
    _validate(paths.schema_out, out)

    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BattleBuddy CRA runner (v1) — process-only schema-driven report generator (no fetches)."
    )

    parser.add_argument("--input", help="Path to CRA input JSON")
    parser.add_argument("--case-id", help="Case ID under CASES/ACTIVE (writes to ARTIFACTS/CRA)")
    parser.add_argument("--case-dir", help="Explicit case directory path (writes to ARTIFACTS/CRA)")
    parser.add_argument("--out", help="Explicit output path (writes report JSON)")

    parser.add_argument(
        "--handshake-only",
        action="store_true",
        help="Print handshake observations/questions from free text and exit (does not run CRA).",
    )
    parser.add_argument(
        "--handshake-text",
        help="Free text for handshake mode (not stored; printed as questions only).",
    )
    parser.add_argument(
        "--handshake-file",
        help="Path to a text/markdown file used for handshake mode (not stored; printed as questions only).",
    )
    parser.add_argument(
        "--handshake-format",
        choices=["general", "cra"],
        default="general",
        help="Handshake output format: general questions, or CRA schema-aligned questionnaire.",
    )
    parser.add_argument(
        "--handshake-quiet",
        action="store_true",
        help="Handshake-only mode: suppress observations/flags and print questions only.",
    )

    args = parser.parse_args()

    paths = _paths()

    if args.handshake_only:
        if bool(args.handshake_text) == bool(args.handshake_file):
            raise SystemExit("--handshake-only requires exactly one of --handshake-text or --handshake-file")

        if args.handshake_file:
            text = _read_text_file(_require_text_path(args.handshake_file))
        else:
            text = str(args.handshake_text or "")

        _print_handshake(
            text,
            repo_root=paths.repo_root,
            output_format=str(args.handshake_format),
            quiet=bool(args.handshake_quiet),
        )
        return 0

    case_dir: Optional[Path] = None
    if args.case_dir:
        case_dir = Path(args.case_dir).expanduser().resolve()
    elif args.case_id:
        case_dir = _case_dir_from_case_id(paths.repo_root, str(args.case_id).strip().upper()).resolve()

    if args.input:
        input_path = _require_json_path(args.input)
    elif case_dir is not None:
        input_path = _default_input_path(case_dir)
    else:
        raise SystemExit("Provide --input OR (--case-id / --case-dir).")

    if not input_path.exists():
        hint = ""
        if case_dir is not None:
            hint = f" Expected at: {_default_input_path(case_dir)}"
        raise SystemExit(f"Input not found: {input_path}.{hint}")

    report = run(input_path=input_path)

    if args.out:
        out_path = _require_json_path(args.out)
    elif case_dir is not None:
        out_path = _default_output_path(case_dir)
    else:
        raise SystemExit("Provide --out if not writing into a case folder.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = _avoid_collision(out_path)

    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(str(out_path))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

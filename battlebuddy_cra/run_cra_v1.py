from __future__ import annotations

import argparse
import json
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
            "Current diagnosis documentation is marked missing/unknown; CRA does not evaluate content, only presence.",
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

    args = parser.parse_args()

    paths = _paths()

    case_dir: Optional[Path] = None
    if args.case_dir:
        case_dir = Path(args.case_dir).expanduser().resolve()
    elif args.case_id:
        case_dir = _case_dir_from_case_id(paths.repo_root, str(args.case_id).strip().upper()).resolve()

    if args.input:
        input_path = Path(args.input).expanduser().resolve()
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
        out_path = Path(args.out).expanduser().resolve()
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

"""
Pathfinder Coordinator v1

Routes a veteran case through the Division swarm.

Routing rules (Foundational — immutable):
  1. Founding law SHA-256 verified before any Division runs. Mismatch = fail closed.
  2. Crisis gate runs first. If flagged, crisis Division blocks all others until resolved.
  3. Every Division result — including SKIPPED and FAILED — is recorded. Nothing dropped.
  4. Quorum: at least one Division must return COMPLETED for synthesis to be actionable.

Routing rules (Mutable — subject to registry updates):
  - Active Divisions resolved from config/divisions.json at runtime.
  - Domain-to-Division mapping resolved from config/division-registry.json.
  - Non-crisis Divisions run in parallel where possible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FOUNDING_LAW_SHA256 = "dc0fcb428e24948c5471798bf3c0b77cafade1c68e1aecb39aa13eef264f2f87"
_INTAKE_SCHEMA    = "squad-bat.coordinator-intake.v1"
_RESULT_SCHEMA    = "squad-bat.coordinator-result.v1"
_CRISIS_DOMAINS   = {"CRISIS", "MENTAL_HEALTH"}

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Founding law verification
# ---------------------------------------------------------------------------

def assert_founding_law() -> None:
    law_path = REPO_ROOT / "GOVERNANCE" / "LAWS" / "veteran_data_sovereignty.v1.md"
    if not law_path.exists():
        _fail_closed(f"FOUNDING_LAW_MISSING: {law_path}")
    digest = hashlib.sha256(law_path.read_bytes()).hexdigest()
    if digest != _FOUNDING_LAW_SHA256:
        _fail_closed(
            f"FOUNDING_LAW_TAMPERED: expected {_FOUNDING_LAW_SHA256}, got {digest}. "
            "All coordinator operations blocked."
        )


def _fail_closed(reason: str) -> None:
    raise SystemExit(f"[PATHFINDER-COORDINATOR FAIL-CLOSED] {reason}")


# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------

def load_division_registry() -> dict[str, Any]:
    reg_path = REPO_ROOT / "config" / "division-registry.json"
    if not reg_path.exists():
        _fail_closed(f"Division registry not found: {reg_path}")
    with open(reg_path, encoding="utf-8") as f:
        return json.load(f)


def load_divisions_config() -> dict[str, Any]:
    cfg_path = REPO_ROOT / "config" / "divisions.json"
    if not cfg_path.exists():
        _fail_closed(f"Divisions config not found: {cfg_path}")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def resolve_divisions_for_domains(
    domains: list[str],
    registry: dict[str, Any],
    divisions_cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (matched, gaps).
    matched: list of {division_id, domain, entry, ...} for active Divisions.
    gaps: list of {domain, reason} for domains with no active Division.
    """
    active_divisions = divisions_cfg.get("divisions", {})
    reg_modules = {m["id"]: m for m in registry.get("modules", [])}

    matched: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    seen_divisions: set[str] = set()

    for domain in domains:
        found = False
        for mod_id, mod in reg_modules.items():
            if domain in mod.get("domains", []) and mod_id not in seen_divisions:
                div_cfg = active_divisions.get(mod_id, {})
                matched.append({
                    "division_id": mod_id,
                    "domain": domain,
                    "entry": div_cfg.get("entry", ""),
                    "founding_law_sha256": mod.get("founding_law_sha256", ""),
                })
                seen_divisions.add(mod_id)
                found = True
                break
        if not found:
            gaps.append({"domain": domain, "reason": "No active Division registered for this domain"})

    return matched, gaps


# ---------------------------------------------------------------------------
# Division invocation
# ---------------------------------------------------------------------------

def invoke_division(
    division: dict[str, Any],
    intake: dict[str, Any],
) -> dict[str, Any]:
    """
    Invokes a single Division and returns a DivisionResult dict.
    Currently calls the PowerShell DivisionInvoke layer via subprocess.
    Falls back to a DEGRADED result on any error — never raises.
    """
    import subprocess

    division_id = division["division_id"]
    domain = division["domain"]
    start_ms = int(time.monotonic() * 1000)

    invoke_script = REPO_ROOT / "consumers" / "divisions" / "Invoke-HousingDivision.ps1"
    if not invoke_script.exists():
        return _division_skipped(division_id, domain, "No consumer script found", start_ms)

    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(invoke_script)],
            input=json.dumps(intake),
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration_ms = int(time.monotonic() * 1000) - start_ms

        if result.returncode == 0:
            return {
                "division_id": division_id,
                "domain": domain,
                "status": "COMPLETED",
                "confidence": "MEDIUM",
                "result_summary": result.stdout.strip()[:500] or "Division completed.",
                "next_actions": [],
                "duration_ms": duration_ms,
            }
        else:
            return {
                "division_id": division_id,
                "domain": domain,
                "status": "FAILED",
                "confidence": "VERIFY_REQUIRED",
                "result_summary": (result.stderr.strip() or "Division exited non-zero.")[:500],
                "next_actions": [],
                "duration_ms": duration_ms,
            }
    except subprocess.TimeoutExpired:
        return _division_skipped(division_id, domain, "Division timed out (120s)", start_ms)
    except Exception as exc:
        return _division_skipped(division_id, domain, f"Invocation error: {exc}", start_ms)


def _division_skipped(
    division_id: str, domain: str, reason: str, start_ms: int
) -> dict[str, Any]:
    return {
        "division_id": division_id,
        "domain": domain,
        "status": "SKIPPED",
        "confidence": "VERIFY_REQUIRED",
        "result_summary": reason,
        "next_actions": [],
        "duration_ms": int(time.monotonic() * 1000) - start_ms,
    }


# ---------------------------------------------------------------------------
# Crisis gate
# ---------------------------------------------------------------------------

def run_crisis_gate(
    intake: dict[str, Any],
    divisions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    If crisis is flagged, invoke the crisis/mental-health Division first.
    Block all other Divisions until it resolves.
    Returns (crisis_gate_result, crisis_division_results).
    """
    crisis = intake.get("crisis", {})
    if not crisis.get("flagged", False):
        return {"flagged": False, "resolved": True}, []

    crisis_divs = [d for d in divisions if d["domain"] in _CRISIS_DOMAINS]
    if not crisis_divs:
        return {
            "flagged": True,
            "resolved": False,
            "outcome_note": "Crisis flagged but no crisis Division is registered. Routing blocked.",
        }, []

    crisis_div = crisis_divs[0]
    result = invoke_division(crisis_div, intake)
    resolved = result["status"] == "COMPLETED"

    return {
        "flagged": True,
        "resolved": resolved,
        "division_invoked": crisis_div["division_id"],
        "outcome_note": result.get("result_summary", ""),
    }, [result]


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize(
    division_results: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = [r for r in division_results if r["status"] == "COMPLETED"]
    quorum_met = len(completed) > 0

    all_actions: list[str] = []
    domain_summaries: dict[str, str] = {}
    for r in division_results:
        domain_summaries[r["domain"]] = r.get("result_summary", "No result.")
        all_actions.extend(r.get("next_actions", []))

    if not quorum_met:
        primary_path = (
            "No Division returned a completed result. Manual review required. "
            "Contact your local VA navigator or Veterans Service Organization (VSO)."
        )
        confidence = "VERIFY_REQUIRED"
    elif len(completed) == 1:
        primary_path = completed[0].get("result_summary", "See Division result.")
        confidence = completed[0].get("confidence", "MEDIUM")
    else:
        domains_covered = ", ".join(r["domain"] for r in completed)
        primary_path = (
            f"Multiple programs identified across: {domains_covered}. "
            "Review domain summaries below for next steps in each area."
        )
        confidence = "MEDIUM"

    if gaps:
        gap_domains = ", ".join(g["domain"] for g in gaps)
        primary_path += f" Note: no active Division found for {gap_domains} — these areas need manual follow-up."

    return {
        "primary_path": primary_path,
        "confidence": confidence,
        "next_actions": all_actions[:5],
        "domain_summaries": domain_summaries,
        "if_blocked": ["Contact your local Veterans Service Organization (VSO)", "Call 1-800-827-1000 (VA main line)"],
        "quorum_met": quorum_met,
    }


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

def write_receipt(result: dict[str, Any]) -> Path:
    receipts_dir = REPO_ROOT / "artifacts" / "receipts" / "coordinator"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"COORD_{result['case_id']}_{result['timestamp'].replace(':', '-')}.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return receipt_path


# ---------------------------------------------------------------------------
# Main coordinator entry
# ---------------------------------------------------------------------------

def run_coordinator(intake: dict[str, Any]) -> dict[str, Any]:
    assert_founding_law()

    if intake.get("schema") != _INTAKE_SCHEMA:
        _fail_closed(f"Unknown intake schema: {intake.get('schema')}")
    if intake.get("founding_law_sha256") != _FOUNDING_LAW_SHA256:
        _fail_closed("Intake founding_law_sha256 mismatch — intake rejected.")

    registry = load_division_registry()
    divisions_cfg = load_divisions_config()

    domains = intake.get("domains", [])
    matched_divisions, gaps = resolve_divisions_for_domains(domains, registry, divisions_cfg)

    # Crisis gate — foundational, cannot be bypassed
    crisis_gate_result, crisis_results = run_crisis_gate(intake, matched_divisions)

    if crisis_gate_result["flagged"] and not crisis_gate_result["resolved"]:
        coordinator_status = "FAILED_CLOSED"
        all_results = crisis_results
    else:
        non_crisis_divisions = [
            d for d in matched_divisions if d["domain"] not in _CRISIS_DOMAINS
        ]

        # Fan out to non-crisis Divisions in parallel
        non_crisis_results: list[dict[str, Any]] = []
        if non_crisis_divisions:
            with ThreadPoolExecutor(max_workers=len(non_crisis_divisions)) as pool:
                futures = {
                    pool.submit(invoke_division, div, intake): div
                    for div in non_crisis_divisions
                }
                for future in as_completed(futures):
                    non_crisis_results.append(future.result())

        all_results = crisis_results + non_crisis_results
        completed_count = sum(1 for r in all_results if r["status"] == "COMPLETED")
        failed_count = sum(1 for r in all_results if r["status"] == "FAILED")

        if completed_count == 0:
            coordinator_status = "CONTROLLED"
        elif failed_count > 0:
            coordinator_status = "CONTROLLED"
        else:
            coordinator_status = "WITHIN_TOLERANCE"

    synthesis = synthesize(all_results, gaps)

    result: dict[str, Any] = {
        "schema": _RESULT_SCHEMA,
        "case_id": intake["case_id"],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "founding_law_sha256": _FOUNDING_LAW_SHA256,
        "coordinator_status": coordinator_status,
        "crisis_gate_result": crisis_gate_result,
        "division_results": all_results,
        "synthesis": synthesis,
        "gaps": gaps,
        "receipt_ref": "",
    }

    receipt_path = write_receipt(result)
    result["receipt_ref"] = str(receipt_path.relative_to(REPO_ROOT))

    return result


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pathfinder Coordinator v1 — routes a veteran case through the Division swarm."
    )
    parser.add_argument("--input", required=True, help="Path to coordinator intake JSON file.")
    parser.add_argument("--out", help="Path to write result JSON. Defaults to stdout.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    with open(input_path, encoding="utf-8") as f:
        intake = json.load(f)

    result = run_coordinator(intake)

    output = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Result written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()

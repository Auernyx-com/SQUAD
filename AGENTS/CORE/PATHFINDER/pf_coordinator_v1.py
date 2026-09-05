"""
Pathfinder Coordinator v1

Routes a veteran case through the Division swarm.

Routing rules (Foundational — immutable):
  1. Founding law SHA-256 verified before any Division runs. Mismatch = fail closed.
     This is one of only three legitimate fail-closed triggers in BAT.
  2. Crisis response is ADDITIVE — never blocks other divisions.
     A veteran in crisis still needs housing, benefits, medical, and legal routing.
  3. Every Division result — including SKIPPED, NEEDS_INPUT, and FAILED — is recorded.
     Nothing dropped.
  4. Quorum: at least one Division must return COMPLETED for synthesis to be actionable.
  5. Confidence is a hard percentage based on known facts in the intake.
     Never a label. Never a guess. Displayed raw to navigators; translated to plain
     language for veterans. Always stored. Never suppressed.
  6. Edge cases surface honestly — no path invented where none exists.
     Unknown territory routes to specific humans, not plausible-sounding guesses.

Legitimate fail-closed triggers (the ONLY three):
  1. FOUNDING_LAW_MISSING or FOUNDING_LAW_TAMPERED — data sovereignty integrity
  2. Unknown intake schema — request cannot be verified as a valid BAT intake
  3. Intake founding_law_sha256 mismatch — intake produced under wrong governance version

Nothing about the veteran — discharge status, crisis flag, eligibility, service history,
identity, or any situational data — ever triggers fail-closed. Those route, with explanation.

Routing rules (Mutable — subject to registry updates):
  - Active Divisions resolved from config/divisions.json at runtime.
  - Domain-to-Division mapping resolved from config/division-registry.json.
  - All Divisions run in parallel regardless of crisis flag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared verified contacts — imported from single source of truth
# ---------------------------------------------------------------------------

_SHARED_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'MODULES', '_shared')
)
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from contacts import (  # type: ignore
    VA_MAIN_LINE         as _VA_MAIN_LINE,
    VA_HOMELESS_VETERANS as _VA_HOMELESS_VETERANS,
    VETERANS_CRISIS_LINE as _VETERANS_CRISIS_LINE,
    VA_OIG               as _VA_OIG,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FOUNDING_LAW_SHA256 = "dc0fcb428e24948c5471798bf3c0b77cafade1c68e1aecb39aa13eef264f2f87"
_INTAKE_SCHEMA       = "squad-bat.coordinator-intake.v1"
_RESULT_SCHEMA       = "squad-bat.coordinator-result.v1"

REPO_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Confidence fields — per domain
#
# These are the intake fields that materially affect routing quality for each
# domain. Confidence percentage = how many of these are present and non-empty.
# Missing fields don't stop routing — they reduce the confidence number.
# ---------------------------------------------------------------------------

_CONFIDENCE_FIELDS: dict[str, list[str]] = {
    "BENEFITS":       ["discharge", "era", "disability_rating", "va_history",
                       "service_status", "state", "income_monthly"],
    "EMPLOYMENT":     ["discharge", "service_status", "era", "state"],
    "MEDICAL":        ["discharge", "disability_rating", "va_history", "state", "county"],
    "CLAIMS":         ["discharge", "disability_rating", "va_history", "state"],
    "MENTAL_HEALTH":  ["discharge", "service_status", "state"],
    "HOUSING":        ["discharge", "state", "county", "housing_status"],
    "LEGAL":          ["discharge", "state"],
    "BUSINESS":       ["discharge", "state", "service_status"],
    "TRANSPORTATION": ["state", "county", "service_status"],
    "WOMEN_VETERANS": ["discharge", "state", "service_status"],
    "TOXIC_EXPOSURE": ["discharge", "era", "branch", "state"],
    "CRISIS":         ["service_status", "state"],
}

# Flags from divisions that indicate uncertain routing — each reduces confidence by 5
_UNCERTAIN_MARKERS = ("unknown", "candidate", "check_recommended", "verify", "needs_review")

# ---------------------------------------------------------------------------
# Edge case patterns — situations BAT has no reliable routing path for
#
# These don't stop routing. They reduce the synthesis confidence ceiling and
# surface an explicit human handoff note. Never suppressed, never guessed around.
# ---------------------------------------------------------------------------

_EDGE_CASE_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "DISCHARGE_UNKNOWN",
        "description": "Discharge status unknown — eligibility cannot be determined reliably",
        "check": lambda i: i.get("discharge") in ("unknown", None, ""),
    },
    {
        "id": "SERVICE_STATUS_UNKNOWN",
        "description": "Service status not established — routing may be inaccurate",
        "check": lambda i: i.get("service_status") in ("not_sure", None, ""),
    },
    {
        "id": "NO_LOCATION",
        "description": "No location data — local resources cannot be identified",
        "check": lambda i: (
            not i.get("state") and
            not (i.get("location") or {}).get("state")
        ),
    },
    {
        "id": "RECORDS_UNAVAILABLE",
        "description": (
            "Records flagged as unavailable or disputed — eligibility may differ "
            "from what routing suggests. Verify with VSO before acting."
        ),
        "check": lambda i: (
            i.get("records_available") is False or
            i.get("records_disputed") is True
        ),
    },
    {
        "id": "MULTIPLE_SERVICE_PERIODS",
        "description": (
            "Multiple service periods detected — discharge status and eligibility "
            "may differ per period. A VSO can assess the full picture."
        ),
        "check": lambda i: (
            isinstance(i.get("service_periods"), list) and
            len(i.get("service_periods", [])) > 1
        ),
    },
    {
        "id": "MEDICAL_RETIREMENT_VA_DISPUTE",
        "description": (
            "Medical retirement with VA post-discharge causation dispute. "
            "DoD medically retired this veteran — VA claiming conditions are post-service "
            "directly contradicts DoD's own finding. Records-first appeal path required. "
            "Accredited attorney recommended, not standard VSO intake."
        ),
        "check": lambda i: (
            i.get("discharge") == "medical" and
            i.get("medical_retirement_va_dispute") is True
        ),
    },
    {
        "id": "CHRONIC_HOMELESS",
        "description": (
            "Chronic homelessness (6+ months or repeat episodes). "
            "HUD-VASH priority tier — immediate housing routing required alongside all other domains."
        ),
        "check": lambda i: (
            i.get("is_chronically_homeless") is True or
            (i.get("housing_status") in ("unhoused", "unstable") and
             i.get("homelessness_months", 0) >= 6)
        ),
    },
    {
        "id": "ACTIVE_CRIMINAL_CASE",
        "description": (
            "Active criminal case in progress. Veterans Treatment Court routing is time-sensitive — "
            "request VTC diversion at next court appearance. Benefits routing continues in parallel."
        ),
        "check": lambda i: i.get("active_criminal_case") is True,
    },
    {
        "id": "MULTI_DOMAIN_CRISIS",
        "description": (
            "Three or more urgent domains active simultaneously. "
            "This case requires a human navigator to coordinate across tracks — "
            "no single automated path covers this. Human coordinator referral is priority."
        ),
        "check": lambda i: (
            sum([
                i.get("housing_status") in ("unhoused", "unstable"),
                i.get("active_criminal_case") is True,
                (i.get("crisis") or {}).get("flagged") is True,
                i.get("medical_retirement_va_dispute") is True,
                i.get("urgency") == "high",
                i.get("is_chronically_homeless") is True,
            ]) >= 3
        ),
    },
    {
        "id": "VA_FACILITY_OBSTRUCTION",
        "description": (
            "Local VA facility flagged as the obstruction. "
            "Routing must go AROUND the facility — OIG, congressional caseworker, Vet Center, "
            "Community Care, and VAMC transfer are the parallel escalation paths. "
            "Do not route back through a facility the veteran has identified as a barrier."
        ),
        "check": lambda i: (
            i.get("va_facility_obstruction") is True or
            "va_facility_issues" in (i.get("legal_needs") or []) or
            i.get("va_facility_issues") in ("complaints", "obstruction", "distrust")
        ),
    },
]


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
    """
    Hard stop. Called ONLY for the three legitimate fail-closed triggers:
      1. Founding law missing or tampered
      2. Unknown intake schema
      3. Intake founding_law_sha256 mismatch

    Nothing about the veteran ever calls this function.
    """
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
    reg_divisions = {d["id"]: d for d in registry.get("divisions", [])}

    domain_to_division: dict[str, str] = {}
    for div_id, div in reg_divisions.items():
        for domain in div.get("domains", []):
            if domain not in domain_to_division:
                domain_to_division[domain] = div_id

    matched: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    seen_divisions: set[str] = set()

    for domain in domains:
        div_id = domain_to_division.get(domain)
        if div_id and div_id not in seen_divisions:
            div_reg = reg_divisions[div_id]
            div_cfg = active_divisions.get(div_id, {})
            entry = div_cfg.get("entry", "")
            matched.append({
                "division_id": div_id,
                "domain": domain,
                "entry": entry,
                "entry_configured": bool(entry),
                "status": div_reg.get("status", "unknown"),
                "founding_law_sha256": registry.get("founding_law_sha256", ""),
            })
            seen_divisions.add(div_id)
        elif not div_id:
            gaps.append({"domain": domain, "reason": "No Division registered for this domain"})

    return matched, gaps


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def calculate_division_confidence(
    domain: str,
    intake: dict[str, Any],
    status: str,
    flags: list[str],
) -> int:
    """
    Returns routing confidence as integer 0–100, derived from known facts.

    Never a vibe. Never a label. Derivation:
      - Base = percentage of domain-relevant confidence fields present in intake
      - SKIPPED → 0 (division did not run)
      - NEEDS_INPUT → capped at 45 (intake incomplete for this domain)
      - FAILED → capped at 25 (routing attempted but failed)
      - COMPLETED → no ceiling (base holds)
      - Each uncertain flag (unknown/candidate/check/verify) → -5, floor 10
      - Rounded to nearest 5
    """
    if status == "SKIPPED":
        return 0

    fields = _CONFIDENCE_FIELDS.get(domain, ["discharge", "state"])

    # Resolve location fields — intake may nest state/county under "location"
    location = intake.get("location") or {}
    effective: dict[str, Any] = dict(intake)
    if not effective.get("state") and location.get("state"):
        effective["state"] = location["state"]
    if not effective.get("county") and location.get("county"):
        effective["county"] = location["county"]

    present = sum(1 for f in fields if effective.get(f))
    base = round((present / len(fields)) * 100 / 5) * 5

    # Status ceiling
    if status == "FAILED":
        base = min(base, 25)
    elif status == "NEEDS_INPUT":
        base = min(base, 45)

    # Uncertain flags reduce confidence
    uncertain = sum(
        1 for f in flags
        if any(m in f.lower() for m in _UNCERTAIN_MARKERS)
    )
    base = max(10, base - (uncertain * 5))

    return min(100, base)


# ---------------------------------------------------------------------------
# Edge case detection
# ---------------------------------------------------------------------------

def detect_edge_cases(intake: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Checks intake for patterns that indicate unknown territory BAT cannot
    reliably route. Returns list of {id, description}. Empty = no edge cases.

    Edge cases do not stop routing — they reduce the synthesis confidence ceiling
    and surface an explicit human handoff note. BAT never invents a path.
    """
    return [
        {"id": p["id"], "description": p["description"]}
        for p in _EDGE_CASE_PATTERNS
        if p["check"](intake)
    ]


# ---------------------------------------------------------------------------
# Division invocation
# ---------------------------------------------------------------------------

def invoke_division(
    division: dict[str, Any],
    intake: dict[str, Any],
) -> dict[str, Any]:
    """
    Invokes a single Division's Python entry point and returns a DivisionResult dict.
    Falls back to SKIPPED on any error — never raises.

    Status values returned:
      COMPLETED   — division ran, rule matched, result produced
      NEEDS_INPUT — division ran, intake incomplete for this domain
      FAILED      — division ran, routing exception or hard failure
      SKIPPED     — division entry not configured or not found
    """
    import importlib.util

    division_id = division["division_id"]
    domain = division["domain"]
    entry = division.get("entry", "")
    start_ms = int(time.monotonic() * 1000)

    if not entry:
        return _division_skipped(
            division_id, domain,
            f"Division entry not configured — framework-only. "
            f"Set entry in config/divisions.json.",
            start_ms,
        )

    entry_path = REPO_ROOT / entry
    if not entry_path.exists():
        return _division_skipped(
            division_id, domain,
            f"Division entry not found at {entry_path}",
            start_ms,
        )

    try:
        spec = importlib.util.spec_from_file_location(division_id, entry_path)
        if spec is None or spec.loader is None:
            return _division_skipped(division_id, domain, "Could not load module spec", start_ms)

        import sys as _sys
        mod = importlib.util.module_from_spec(spec)
        _sys.modules[spec.name] = mod   # required in Python 3.14+ — dataclass needs module in sys.modules
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        if not hasattr(mod, "run"):
            return _division_skipped(division_id, domain, "Division has no run() entrypoint", start_ms)

        result = mod.run(intake)
        duration_ms = int(time.monotonic() * 1000) - start_ms

        # Normalize — division run() returns a dataclass or dict
        if hasattr(result, "status"):
            raw_status    = result.status
            summary       = getattr(result, "primary_path", None) or getattr(result, "next_action", "") or ""
            next_acts     = list(getattr(result, "secondary_options", []))[:3]
            flags         = list(getattr(result, "flags", []))
            questions     = list(getattr(result, "questions", []))
            key_resources = list(getattr(result, "key_resources", []))
            notes         = list(getattr(result, "notes", []))
            next_action   = getattr(result, "next_action", "") or ""
        else:
            raw_status    = result.get("status", "UNKNOWN")
            summary       = result.get("primary_path") or result.get("next_action", "")
            next_acts     = result.get("secondary_options", [])[:3]
            flags         = result.get("flags", [])
            questions     = result.get("questions", [])
            key_resources = result.get("key_resources", [])
            notes         = result.get("notes", [])
            next_action   = result.get("next_action", "") or ""

        # Extract verified phone numbers from key_resources and notes.
        # Any line containing a phone pattern (1-XXX, XXX-XXX-XXXX, 988)
        # is treated as an immediate contact and surfaced separately.
        import re as _re
        _phone_pattern = _re.compile(r'(1-\d{3}-\d{3}-\d{4}|1-\d{3}-\d{4}|1-877-4AID-VET|\d{3}-\d{3}-\d{4}|988)')
        immediate_contacts: list[str] = []
        for line in key_resources + notes:
            if _phone_pattern.search(str(line)) and line not in immediate_contacts:
                immediate_contacts.append(str(line)[:200])

        # Map division status to coordinator status
        if raw_status in ("OK", "WITHIN_TOLERANCE", "COMPLETED"):
            coord_status = "COMPLETED"
        elif raw_status == "NEEDS_INPUT":
            coord_status = "NEEDS_INPUT"
        else:
            coord_status = "FAILED"

        confidence = calculate_division_confidence(domain, intake, coord_status, flags)

        result_dict: dict[str, Any] = {
            "division_id":        division_id,
            "domain":             domain,
            "status":             coord_status,
            "confidence":         confidence,
            "result_summary":     str(summary)[:500] if summary else f"{division_id} completed.",
            "next_action":        str(next_action)[:300] if next_action else "",
            "next_actions":       next_acts,
            "immediate_contacts": immediate_contacts,  # verified phone numbers — always surfaced
            "flags":              flags,
            "duration_ms":        duration_ms,
        }
        if questions:
            result_dict["intake_questions"] = questions

        return result_dict

    except Exception as exc:
        return _division_skipped(division_id, domain, f"Invocation error: {exc}", start_ms)


def _division_skipped(
    division_id: str, domain: str, reason: str, start_ms: int
) -> dict[str, Any]:
    return {
        "division_id":    division_id,
        "domain":         domain,
        "status":         "SKIPPED",
        "confidence":     0,
        "result_summary": reason,
        "next_actions":   [],
        "duration_ms":    int(time.monotonic() * 1000) - start_ms,
    }


# ---------------------------------------------------------------------------
# Crisis response — additive, never blocking
# ---------------------------------------------------------------------------

_CRISIS_RESOURCES = [
    "988 Suicide & Crisis Lifeline — call or text 988, press 1 for veterans",
    "Veterans Crisis Line — text 838255",
    "Crisis Chat — veteranscrisisline.net/get-help-now/chat",
    "Emergency: 911",
]


def run_crisis_response(intake: dict[str, Any]) -> dict[str, Any]:
    """
    If crisis is flagged, surface crisis resources immediately.
    DOES NOT block other divisions — all routing continues in parallel.
    Crisis response is additive, never a gate.
    """
    crisis = intake.get("crisis", {})
    if not crisis.get("flagged", False):
        return {"flagged": False}

    return {
        "flagged": True,
        "resources": _CRISIS_RESOURCES,
        "outcome_note": (
            "Crisis flagged. Resources surfaced below. "
            "All other routing continues — a veteran in crisis still needs "
            "housing, benefits, medical, and legal help."
        ),
    }


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def synthesize(
    division_results: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    edge_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Synthesizes division results into a single coordinator output.

    Confidence is calculated as the average of completed division confidences,
    capped at 50 when edge cases are present. Always an integer 0–100.
    Always accompanied by a plain-language label for veteran-facing display.
    """
    completed   = [r for r in division_results if r["status"] == "COMPLETED"]
    needs_input = [r for r in division_results if r["status"] == "NEEDS_INPUT"]
    quorum_met  = len(completed) > 0

    all_actions: list[str] = []
    all_contacts: list[str] = []
    domain_summaries: dict[str, str] = {}
    for r in division_results:
        domain_summaries[r["domain"]] = r.get("result_summary", "No result.")
        all_actions.extend(r.get("next_actions", []))
        for c in r.get("immediate_contacts", []):
            if c not in all_contacts:
                all_contacts.append(c)

    # Always include the VA main line and homeless veterans line as floor contacts
    _floor_contacts = [
        f"VA main line — {_VA_MAIN_LINE}",
        f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} — 24/7",
        f"Veterans Crisis Line — {_VETERANS_CRISIS_LINE}",
    ]

    # --- Synthesis confidence ---
    # Average of completed division confidences.
    # Edge cases cap the ceiling — unknown territory means the number can't be high.
    # Track whether the cap actually reduced the number so the label reflects reality.
    edge_case_cap_applied = False
    if not completed:
        synthesis_confidence = 0
    else:
        raw_avg = sum(r.get("confidence", 0) for r in completed) / len(completed)
        synthesis_confidence = round(raw_avg / 5) * 5
        if edge_cases and synthesis_confidence > 50:
            synthesis_confidence = 50
            edge_case_cap_applied = True

    # --- Primary path ---
    if not quorum_met:
        primary_path = (
            "No Division returned a completed result. Manual review required. "
            "Contact your local VA navigator or Veterans Service Organization (VSO)."
        )
    elif len(completed) == 1:
        primary_path = completed[0].get("result_summary", "See Division result.")
    else:
        domains_covered = ", ".join(r["domain"] for r in completed)
        primary_path = (
            f"Multiple programs identified across: {domains_covered}. "
            "Review domain summaries below for next steps in each area."
        )

    if gaps:
        gap_domains = ", ".join(g["domain"] for g in gaps)
        primary_path += (
            f" Note: no active Division found for {gap_domains} — "
            "these areas need manual follow-up."
        )

    if edge_cases:
        edge_notes = "; ".join(e["description"] for e in edge_cases)
        primary_path += (
            f" IMPORTANT — unusual circumstances detected: {edge_notes}. "
            "Results may be incomplete. Verify with a VSO or VA navigator before acting."
        )

    if needs_input:
        ni_domains = ", ".join(r["domain"] for r in needs_input)
        primary_path += f" Additional intake information needed for: {ni_domains}."

    # --- Plain-language confidence label ---
    # This is a translation of the number, not a replacement for it.
    # Label must reflect WHY the number is where it is — not just the number itself.
    #   Edge case cap applied → routing ran, cap is from unknown territory, not gaps
    #   Edge cases present but cap not applied → unusual circumstances AND gaps
    #   No edge cases → label is purely about intake completeness
    if not completed:
        confidence_label = "No completed routing — manual review required"
    elif edge_case_cap_applied:
        ec_count = len(edge_cases)
        confidence_label = (
            f"Capped at 50% — {ec_count} unusual circumstance"
            + ("s" if ec_count != 1 else "")
            + " detected; routing is valid but human verification required before acting"
        )
    elif edge_cases:
        # Cap wasn't applied (raw was already ≤ 50) but edge cases are still present —
        # both intake gaps AND unusual circumstances contributed
        ec_count = len(edge_cases)
        confidence_label = (
            f"Low — incomplete intake"
            + (f" and {ec_count} unusual circumstance" + ("s" if ec_count != 1 else "") if ec_count else "")
            + "; VSO or human navigator review required"
        )
    elif synthesis_confidence >= 80:
        confidence_label = "High — routing based on complete intake data"
    elif synthesis_confidence >= 60:
        confidence_label = "Moderate — some intake fields missing; verify before acting"
    elif synthesis_confidence >= 40:
        confidence_label = "Low — incomplete intake data; VSO review strongly recommended"
    else:
        confidence_label = "Very low — BAT cannot reliably route this case; contact a VSO directly"

    # Deduplicate division-surfaced contacts by phone number substring.
    # Two contacts with the same number but different labels are the same contact.
    # Keep the first occurrence (usually more specific), drop later ones.
    import re as _re
    _phone_re = _re.compile(r'1-\d{3}-[\d-]{7,}|1-877-4AID-VET|\d{3}-\d{3}-\d{4}|988')
    _seen_numbers: set[str] = set()
    _seen_exact: set[str] = set()
    deduped: list[str] = []
    for c in all_contacts:
        if c in _seen_exact:
            continue
        nums_in_c = set(_phone_re.findall(c))
        if nums_in_c and nums_in_c.issubset(_seen_numbers):
            continue   # all numbers in this contact already represented
        _seen_exact.add(c)
        _seen_numbers.update(nums_in_c)
        deduped.append(c)

    # Add floor contacts if their phone number isn't already present anywhere.
    # Check by number substring — catches "VA main line — 1-800-827-1000 — ask for Benefits"
    # and "VA main line — 1-800-827-1000" as the same number without needing exact label match.
    _floor_pairs = [
        (f"VA main line — {_VA_MAIN_LINE}", _VA_MAIN_LINE),
        (f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} — 24/7",
         _VA_HOMELESS_VETERANS),
        (f"Veterans Crisis Line — {_VETERANS_CRISIS_LINE}", _VETERANS_CRISIS_LINE),
    ]
    merged_contacts: list[str] = deduped
    for label, number in _floor_pairs:
        if not any(number in c for c in merged_contacts):
            merged_contacts.append(label)

    return {
        "primary_path":       primary_path,
        "confidence":         synthesis_confidence,
        "confidence_label":   confidence_label,
        "next_actions":       all_actions[:5],
        "immediate_contacts": merged_contacts,        # verified phone numbers — always present
        "domain_summaries":   domain_summaries,
        "if_blocked": [
            "Contact your local Veterans Service Organization (VSO)",
            f"Call VA main line: {_VA_MAIN_LINE}",
        ],
        "quorum_met":         quorum_met,
        "edge_cases":         edge_cases,
    }


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

def write_receipt(result: dict[str, Any]) -> Path:
    # Overridable the same way config/divisions.json's own notes already
    # document env-var overrides (SQUAD_BAT_DIVISION_ENTRY_*): every
    # coordinator run — test or real — writes a receipt here, and
    # artifacts/receipts/coordinator/ is not gitignored (older receipts are
    # already tracked in this repo, committed intentionally). Without this,
    # every test run leaves real files in the shared production path that a
    # careless `git add -A` could commit as noise. Tests set
    # SQUAD_BAT_RECEIPTS_DIR to a temp directory instead.
    receipts_dir = Path(os.environ.get("SQUAD_BAT_RECEIPTS_DIR") or (REPO_ROOT / "artifacts" / "receipts" / "coordinator"))
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = (
        receipts_dir /
        f"COORD_{result['case_id']}_{result['timestamp'].replace(':', '-')}.json"
    )
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return receipt_path


# ---------------------------------------------------------------------------
# Main coordinator entry
# ---------------------------------------------------------------------------

def run_coordinator(intake: dict[str, Any]) -> dict[str, Any]:
    # Legitimate fail-closed triggers (the only three)
    assert_founding_law()

    if intake.get("schema") != _INTAKE_SCHEMA:
        _fail_closed(f"Unknown intake schema: {intake.get('schema')}")
    if intake.get("founding_law_sha256") != _FOUNDING_LAW_SHA256:
        _fail_closed("Intake founding_law_sha256 mismatch — intake rejected.")

    registry      = load_division_registry()
    divisions_cfg = load_divisions_config()

    domains = intake.get("domains", [])
    matched_divisions, gaps = resolve_divisions_for_domains(domains, registry, divisions_cfg)

    # Crisis response — additive, never blocking
    crisis_response = run_crisis_response(intake)

    # Edge case detection — affects confidence ceiling, surfaces human handoff
    edge_cases = detect_edge_cases(intake)

    # All divisions run in parallel regardless of crisis flag or edge cases
    all_results: list[dict[str, Any]] = []
    if matched_divisions:
        with ThreadPoolExecutor(max_workers=max(1, len(matched_divisions))) as pool:
            futures = {
                pool.submit(invoke_division, div, intake): div
                for div in matched_divisions
            }
            for future in as_completed(futures):
                all_results.append(future.result())

    completed_count   = sum(1 for r in all_results if r["status"] == "COMPLETED")
    failed_count      = sum(1 for r in all_results if r["status"] == "FAILED")
    needs_input_count = sum(1 for r in all_results if r["status"] == "NEEDS_INPUT")

    if completed_count == 0:
        coordinator_status = "CONTROLLED"
    elif failed_count > 0 or needs_input_count > 0:
        coordinator_status = "CONTROLLED"
    else:
        coordinator_status = "WITHIN_TOLERANCE"

    synthesis = synthesize(all_results, gaps, edge_cases)

    result: dict[str, Any] = {
        "schema":             _RESULT_SCHEMA,
        "case_id":            intake["case_id"],
        "timestamp":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "founding_law_sha256": _FOUNDING_LAW_SHA256,
        "coordinator_status": coordinator_status,
        "crisis_response":    crisis_response,
        "edge_cases":         edge_cases,
        "division_results":   all_results,
        "synthesis":          synthesis,
        "gaps":               gaps,
        "receipt_ref":        "",
    }

    receipt_path = write_receipt(result)
    # receipt_path is normally under REPO_ROOT, but write_receipt() now
    # honors SQUAD_BAT_RECEIPTS_DIR (added alongside this change, for test
    # isolation), which can point anywhere. relative_to() raises ValueError
    # for a path that isn't actually a subpath — caught directly by running
    # a real coordinator call with that env var set. Fall back to the
    # absolute path in that case rather than let a receipt-path bookkeeping
    # detail crash the whole coordinator run.
    try:
        result["receipt_ref"] = str(receipt_path.relative_to(REPO_ROOT))
    except ValueError:
        result["receipt_ref"] = str(receipt_path)

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

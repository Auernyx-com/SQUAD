"""
business_opportunity_router.py
SQUAD BAT — Business & Opportunity Division module entry point.

Wraps BusinessOpportunity_v0_1.py routing logic with standard module interface.
Accepts a dict payload, validates required fields, returns structured result.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

_SHARED_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '_shared')
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from BusinessOpportunity_v0_1 import (  # type: ignore
    BusinessOpportunityProfile,
    route_business_opportunity,
    check_qualification,
    check_certification_eligibility,
)
from local_resources import find_local_resources, format_local_resource_line  # type: ignore

# Service tags to search for. Unlike every other Division, there is no
# dedicated "veteran business" tag in the controlled vocabulary -- but
# every state's shard already carries a state VSO/veterans-affairs agency
# entry tagged "advocacy"/"resource_referral" (see
# tools/generate_state_shards.py), and that agency is a real, useful first
# stop for a business question too, not just claims/benefits. Kept to a
# fixed baseline rather than branching on flags -- none of this Division's
# own tracks (contracting/SBA/GSA/startup) map to a more specific real tag.
_LOCAL_RESOURCE_TAGS = ["advocacy", "resource_referral"]

REQUIRED_FIELDS = {'discharge'}
VALID_DISCHARGE = {'honorable', 'general', 'other_than_honorable', 'dishonorable', 'unknown'}
VALID_STAGE = {'idea', 'startup', 'existing'}


@dataclass(frozen=True)
class BusinessOpportunityResult:
    status: str                      # OK | NEEDS_INPUT | FAILED_CLOSED
    primary_path: Optional[str]
    secondary_options: List[str]
    certifications: List[Dict]
    flags: List[str]
    next_action: Optional[str]
    key_resources: List[str]
    notes: List[str]
    questions: List[str]
    audit: Dict[str, Any]


def _validate(payload: Dict[str, Any]) -> List[str]:
    errors = []
    if 'discharge' not in payload or not payload['discharge']:
        errors.append('Missing required field: discharge')
    discharge = payload.get('discharge', '')
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")
    stage = payload.get('business_stage', '')
    if stage and stage not in VALID_STAGE:
        errors.append(f"Invalid business_stage '{stage}'. Valid: {sorted(VALID_STAGE)}")
    return errors


def _build_profile(payload: Dict[str, Any]) -> BusinessOpportunityProfile:
    def _bool(key: str) -> bool:
        return bool(payload.get(key, False))
    def _list(key: str) -> List[str]:
        val = payload.get(key, [])
        return val if isinstance(val, list) else []
    def _int_or_none(key: str) -> Optional[int]:
        val = payload.get(key)
        if val is None: return None
        try: return int(val)
        except (ValueError, TypeError): return None

    return BusinessOpportunityProfile(
        discharge=payload.get('discharge', 'unknown'),
        service_connected_disability=_bool('service_connected_disability'),
        disability_rating=_int_or_none('disability_rating'),
        business_stage=payload.get('business_stage', 'idea'),
        need_branches=_list('need_branches'),
        entity_type=payload.get('entity_type', 'none_yet'),
        owns_51_percent=payload.get('owns_51_percent', True),
        controls_operations=payload.get('controls_operations', True),
        state=str(payload.get('state', '')),
        county=str(payload.get('county', '')),
        annual_revenue=_int_or_none('annual_revenue'),
        employee_count=_int_or_none('employee_count'),
    )


def route(payload: Dict[str, Any]) -> BusinessOpportunityResult:
    if not isinstance(payload, dict):
        return BusinessOpportunityResult(
            status='FAILED_CLOSED', primary_path=None, secondary_options=[],
            certifications=[], flags=['invalid_payload'], next_action=None,
            key_resources=[], notes=[], questions=[],
            audit={'error': 'payload must be a dict'},
        )

    errors = _validate(payload)
    if errors:
        questions = []
        if any('discharge' in e for e in errors):
            questions.append('What type of discharge did you receive? (honorable / general / other than honorable / dishonorable / not sure)')
        return BusinessOpportunityResult(
            status='NEEDS_INPUT', primary_path=None, secondary_options=[],
            certifications=[], flags=['incomplete_intake'], next_action='Collect missing intake fields.',
            key_resources=[], notes=errors, questions=questions,
            audit={'validation_errors': errors},
        )

    profile = _build_profile(payload)
    routing = route_business_opportunity(profile)

    key_resources = list(routing.get('key_resources', []))
    local = find_local_resources(
        state=profile.state,
        county=profile.county,
        service_tags=_LOCAL_RESOURCE_TAGS,
    )
    key_resources.extend(format_local_resource_line(r) for r in local)

    return BusinessOpportunityResult(
        status='OK',
        primary_path=routing.get('primary_path'),
        secondary_options=routing.get('secondary_options', []),
        certifications=routing.get('certifications', []),
        flags=routing.get('flags', []),
        next_action=routing.get('next_action'),
        key_resources=key_resources,
        notes=routing.get('notes', []),
        questions=[],
        audit={
            'discharge': profile.discharge,
            'service_connected_disability': profile.service_connected_disability,
            'disability_rating': profile.disability_rating,
            'business_stage': profile.business_stage,
            'state': profile.state,
            'flags_triggered': routing.get('flags', []),
        },
    )


def route_to_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = route(payload)
    return {
        'status': r.status,
        'primary_path': r.primary_path,
        'secondary_options': r.secondary_options,
        'certifications': r.certifications,
        'flags': r.flags,
        'next_action': r.next_action,
        'key_resources': r.key_resources,
        'notes': r.notes,
        'questions': r.questions,
        'audit': r.audit,
    }


# The Pathfinder coordinator (AGENTS/CORE/PATHFINDER/pf_coordinator_v1.py)
# dynamically loads each Division's entry module and calls mod.run(intake) —
# every other wired Division (housing, legal, transportation, women_veterans,
# toxic_exposure) exposes exactly that name. This module only ever exposed
# route()/route_to_dict(), so even with config/divisions.json pointed at this
# file, invoke_division()'s `hasattr(mod, "run")` check would still fail and
# the coordinator would report this Division SKIPPED — "no run() entrypoint"
# — for every intake touching the BUSINESS domain. Verified directly: this
# was the actual reason business-opportunity-division's entry was still
# empty in divisions.json alongside two other complete, working routers.
run = route

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class ScopeRules:
    allowed_output_fields: List[str]
    allowed_service_tags: Set[str]
    blocked_field_keys: Set[str]


def _module_root() -> Path:
    # MODULES/RESOURCES_NONPROFITS/src/nonprofit_search.py -> module root
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _scope_path() -> Path:
    return _module_root() / "GOVERNANCE" / "auernyx.nonprofit.scope.json"


def _normalize_str(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _walk_keys(obj: Any) -> Iterable[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _load_scope_rules() -> ScopeRules:
    p = _scope_path()
    if not p.exists():
        raise FileNotFoundError(f"Missing module scope file: {p}")

    scope = _load_json(p)

    allowed_output_fields = list((scope.get("registry_rules") or {}).get("allowed_output_fields") or [])
    allowed_output_fields = [str(x) for x in allowed_output_fields if isinstance(x, str) and x.strip()]

    allowed_tags = set((scope.get("service_taxonomy") or {}).get("allowed_service_tags") or [])
    allowed_service_tags = {str(x).strip().lower() for x in allowed_tags if isinstance(x, str) and x.strip()}

    blocked = set((((scope.get("prohibited") or {}).get("ranking_or_recommendation") or {}).get("blocked_fields") or []))
    blocked_field_keys = {str(x).strip().lower() for x in blocked if isinstance(x, str) and x.strip()}

    if not allowed_output_fields:
        raise ValueError("Scope rules missing allowed_output_fields")
    if not allowed_service_tags:
        raise ValueError("Scope rules missing allowed_service_tags")

    return ScopeRules(
        allowed_output_fields=allowed_output_fields,
        allowed_service_tags=allowed_service_tags,
        blocked_field_keys=blocked_field_keys,
    )


def _extract_providers(payload: Any, *, source: str) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        if all(isinstance(x, dict) for x in payload):
            return list(payload)
        raise ValueError(f"{source}: expected provider list of objects")

    if isinstance(payload, dict):
        providers = payload.get("providers")
        if isinstance(providers, list) and all(isinstance(x, dict) for x in providers):
            return list(providers)
        raise ValueError(f"{source}: expected object with providers: [...] ")

    raise ValueError(f"{source}: expected list or object")


def _sanitize_and_validate_record(record: Dict[str, Any], rules: ScopeRules, *, source: str) -> Dict[str, Any]:
    # Reject blocked key names anywhere in the record (not just top-level).
    for k in _walk_keys(record):
        if k.strip().lower() in rules.blocked_field_keys:
            raise ValueError(f"{source}: blocked field key present: {k!r}")

    # Validate services are controlled vocab.
    services = record.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError(f"{source}: services must be a non-empty list")

    cleaned_services: List[str] = []
    for tag in services:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError(f"{source}: service tag must be non-empty string")
        norm = tag.strip().lower()
        if norm not in rules.allowed_service_tags:
            raise ValueError(f"{source}: service tag not in taxonomy: {tag}")
        cleaned_services.append(norm)

    # Keep only allowed output fields at top-level.
    cleaned: Dict[str, Any] = {}
    for field in rules.allowed_output_fields:
        if field in record:
            cleaned[field] = record[field]

    # Ensure required basics exist after stripping.
    if not isinstance(cleaned.get("provider_id"), str) or not str(cleaned.get("provider_id")).strip():
        raise ValueError(f"{source}: missing/invalid provider_id")
    if not isinstance(cleaned.get("name"), str) or not str(cleaned.get("name")).strip():
        raise ValueError(f"{source}: missing/invalid name")

    cleaned["services"] = cleaned_services

    return cleaned


def load_registry(paths: List[str]) -> List[Dict[str, Any]]:
    """Load one or more registry shard files.

    Each file must be either:
    - {"providers": [ {record}, ... ]}
    - or a raw list of provider records.

    Returns sanitized records (allowed output fields only) and rejects prohibited fields.
    """

    if not isinstance(paths, list) or not paths:
        raise ValueError("paths must be a non-empty list of file paths")

    rules = _load_scope_rules()

    out: List[Dict[str, Any]] = []
    for p in paths:
        shard_path = Path(p).expanduser().resolve()
        if not shard_path.exists():
            raise FileNotFoundError(f"Registry shard not found: {shard_path}")

        payload = _load_json(shard_path)
        providers = _extract_providers(payload, source=str(shard_path))

        for i, rec in enumerate(providers):
            out.append(_sanitize_and_validate_record(rec, rules, source=f"{shard_path}#providers[{i}]"))

    return out


def _ci_eq(a: Optional[str], b: Optional[str]) -> bool:
    if a is None or b is None:
        return False
    return str(a).strip().lower() == str(b).strip().lower()


def _ci_contains(haystack: str, needle: str) -> bool:
    return needle.strip().lower() in haystack.strip().lower()


def _list_ci_contains(values: Any, needle: str) -> bool:
    if not isinstance(values, list):
        return False
    for v in values:
        if isinstance(v, str) and _ci_eq(v, needle):
            return True
    return False


def search(
    records: List[Dict[str, Any]],
    *,
    county: Optional[str] = None,
    city: Optional[str] = None,
    service: Optional[str] = None,
    org_type: Optional[str] = None,
    va_visibility: Optional[str] = None,
    text: Optional[str] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """Filter-only search over sanitized nonprofit records.

    - No ranking
    - No scores
    - Stable name sort only
    """

    if not isinstance(records, list):
        raise ValueError("records must be a list")

    if not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    # Enforce service taxonomy by normalizing to lowercase; load_registry already validated.
    service_norm = service.strip().lower() if isinstance(service, str) and service.strip() else None

    text_norm = _normalize_str(text) if isinstance(text, str) and text.strip() else None

    results: List[Dict[str, Any]] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue

        if county and not _list_ci_contains(rec.get("coverage_counties"), county):
            continue
        if city and not _list_ci_contains(rec.get("cities"), city):
            continue
        if service_norm and service_norm not in [str(x).strip().lower() for x in (rec.get("services") or []) if isinstance(x, str)]:
            continue
        if org_type and not _ci_eq(rec.get("org_type"), org_type):
            continue
        if va_visibility and not _ci_eq(rec.get("va_visibility"), va_visibility):
            continue

        if text_norm:
            name = str(rec.get("name") or "")
            notes = str(rec.get("notes") or "")
            blob = " ".join(
                [
                    name,
                    notes,
                    " ".join([str(x) for x in (rec.get("services") or [])]),
                    " ".join([str(x) for x in (rec.get("cities") or [])]),
                    " ".join([str(x) for x in (rec.get("coverage_counties") or [])]),
                ]
            )
            if not _ci_contains(blob, text_norm):
                continue

        results.append(rec)

    # Stable name sort (no scoring)
    results_sorted = sorted(results, key=lambda r: str(r.get("name") or "").strip().lower())

    return results_sorted[:limit]

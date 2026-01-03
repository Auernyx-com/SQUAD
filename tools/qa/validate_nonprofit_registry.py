from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class Finding:
    path: str
    detail: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _module_root(root: Path) -> Path:
    return root / "MODULES" / "RESOURCES_NONPROFITS"


def _iter_registry_files(root: Path) -> List[Path]:
    module_root = _module_root(root)
    data_root = module_root / "DATA"
    if not data_root.is_dir():
        return []
    return sorted(data_root.rglob("*.json"))


def _scope_path(root: Path) -> Path:
    module_scope = _module_root(root) / "GOVERNANCE" / "auernyx.nonprofit.scope.json"
    if module_scope.exists():
        return module_scope
    return root / "GOVERNANCE" / "SCOPE" / "auernyx.nonprofit.scope.json"


def _as_lower_set(values: Any) -> Set[str]:
    if not isinstance(values, list):
        return set()
    out: Set[str] = set()
    for v in values:
        if isinstance(v, str) and v.strip():
            out.add(v.strip().lower())
    return out


def _get_scope_rules(scope: Dict[str, Any]) -> Tuple[Set[str], Set[str], List[str], List[str]]:
    allowed_fields = set(
        str(x).strip() for x in (scope.get("registry_rules") or {}).get("allowed_output_fields") or []
    )
    allowed_fields = {f for f in allowed_fields if f}

    allowed_service_tags = set(
        str(x).strip() for x in (scope.get("service_taxonomy") or {}).get("allowed_service_tags") or []
    )
    allowed_service_tags = {t for t in allowed_service_tags if t}

    blocked_fields = _as_lower_set(
        ((scope.get("prohibited") or {}).get("ranking_or_recommendation") or {}).get("blocked_fields")
    )

    blocked_phrases: List[str] = []
    rr = (scope.get("prohibited") or {}).get("ranking_or_recommendation") or {}
    eo = (scope.get("prohibited") or {}).get("eligibility_or_outcome") or {}
    blocked_phrases.extend([str(x) for x in (rr.get("blocked_phrases") or [])])
    blocked_phrases.extend([str(x) for x in (eo.get("blocked_phrases") or [])])

    # Normalize phrases: lowercase, collapse whitespace
    norm_phrases: List[str] = []
    for p in blocked_phrases:
        p2 = " ".join(p.strip().lower().split())
        if p2:
            norm_phrases.append(p2)

    return allowed_fields, allowed_service_tags, sorted(blocked_fields), norm_phrases


def _walk(obj: Any, path: str = "$") -> Iterable[Tuple[str, Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_str = str(k)
            yield from _walk(v, f"{path}.{k_str}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _walk_keys(obj: Any, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_str = str(k)
            yield f"{path}.{k_str}", k_str
            yield from _walk_keys(v, f"{path}.{k_str}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def _string_values(obj: Any) -> Iterable[Tuple[str, str]]:
    for p, v in _walk(obj):
        if isinstance(v, str):
            yield p, v


def _extract_providers(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        providers = payload.get("providers")
        if isinstance(providers, list):
            return [x for x in providers if isinstance(x, dict)]

    return []


def _validate_payload(
    *,
    payload: Any,
    source_path: Path,
    allowed_fields: Set[str],
    allowed_service_tags: Set[str],
    blocked_fields: Sequence[str],
    blocked_phrases: Sequence[str],
) -> List[Finding]:
    findings: List[Finding] = []

    providers = _extract_providers(payload)
    if not providers:
        # Some module JSON files (like index manifests) are not shards.
        # Only validate files that actually contain provider records.
        return findings

    blocked_fields_set = {b.lower() for b in blocked_fields}

    # 1) Blocked keys anywhere in provider entries
    for idx, provider in enumerate(providers):
        for key_path, key in _walk_keys(provider, path=f"$providers[{idx}]"):
            if key.strip().lower() in blocked_fields_set:
                findings.append(
                    Finding(
                        path=f"{source_path}:{key_path}",
                        detail=f"Blocked field key present: {key!r}",
                    )
                )

    # 2) Enforce allowed top-level provider keys (soft, but mechanical)
    #    Only applies to provider *top-level* keys so we don't forbid nested contact/address structure.
    for idx, provider in enumerate(providers):
        for k in provider.keys():
            if not isinstance(k, str):
                continue
            if k not in allowed_fields:
                findings.append(
                    Finding(
                        path=f"{source_path}:$providers[{idx}].{k}",
                        detail=f"Unexpected top-level field (not in allowed_output_fields): {k}",
                    )
                )

    # 3) Enforce controlled vocabulary for services, if present
    if allowed_service_tags:
        allowed_tags_lower = {t.lower() for t in allowed_service_tags}
        for idx, provider in enumerate(providers):
            services = provider.get("services")
            if services is None:
                continue
            if not isinstance(services, list):
                findings.append(
                    Finding(
                        path=f"{source_path}:$providers[{idx}].services",
                        detail="services must be a list of service_tag strings.",
                    )
                )
                continue

            for j, tag in enumerate(services):
                if not isinstance(tag, str) or not tag.strip():
                    findings.append(
                        Finding(
                            path=f"{source_path}:$providers[{idx}].services[{j}]",
                            detail="service_tag must be a non-empty string.",
                        )
                    )
                    continue
                if tag.strip().lower() not in allowed_tags_lower:
                    findings.append(
                        Finding(
                            path=f"{source_path}:$providers[{idx}].services[{j}]",
                            detail=f"service_tag not in controlled vocabulary: {tag}",
                        )
                    )

    # 4) Blocked phrases inside string values (keeps registry factual/neutral)
    if blocked_phrases:
        # Precompile regexes for phrase containment (whitespace-normalized)
        phrase_res = [re.compile(re.escape(p), re.IGNORECASE) for p in blocked_phrases]

        for idx, provider in enumerate(providers):
            for pth, s in _string_values(provider):
                normalized = " ".join(s.strip().lower().split())
                if not normalized:
                    continue
                for rx, phrase in zip(phrase_res, blocked_phrases):
                    if rx.search(normalized):
                        findings.append(
                            Finding(
                                path=f"{source_path}:{pth}",
                                detail=f"Blocked phrase found in string value: {phrase!r}",
                            )
                        )
                        break

    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Nonprofit Registry files against Auernyx nonprofit scope.")
    parser.add_argument("--root", help="Repo root (defaults to auto-detect)")
    parser.add_argument("--max-failures", type=int, default=50)

    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root).resolve() if args.root else _repo_root()
    scope_file = _scope_path(root)

    if not scope_file.exists():
        print("nonprofit registry validation: SKIP (missing scope json)")
        return 0

    try:
        scope = _load_json(scope_file)
    except Exception as exc:  # noqa: BLE001
        print(f"nonprofit registry validation: FAIL (scope json invalid) {scope_file} ({exc})")
        return 2

    allowed_fields, allowed_service_tags, blocked_fields, blocked_phrases = _get_scope_rules(scope)
    registry_files = _iter_registry_files(root)

    if not registry_files:
        print("nonprofit registry files scanned: 0")
        print("nonprofit registry validation: OK (no module shard files present)")
        return 0

    findings: List[Finding] = []

    for f in registry_files:
        try:
            payload = _load_json(f)
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding(path=str(f), detail=f"invalid json: {exc}"))
            continue

        findings.extend(
            _validate_payload(
                payload=payload,
                source_path=f,
                allowed_fields=allowed_fields,
                allowed_service_tags=allowed_service_tags,
                blocked_fields=blocked_fields,
                blocked_phrases=blocked_phrases,
            )
        )

        if len(findings) >= args.max_failures:
            break

    print(f"nonprofit registry files scanned: {len(registry_files)}")
    if findings:
        print("nonprofit registry validation findings:")
        for finding in findings[: args.max_failures]:
            print(f"- {finding.path} :: {finding.detail}")
        return 1

    print("nonprofit registry validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

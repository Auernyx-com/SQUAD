from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ProvenanceFailureCode = str


@dataclass(frozen=True)
class ProvenanceStatus:
    ok: bool
    code: Optional[ProvenanceFailureCode] = None
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def _env_truthy(name: str) -> bool:
    val = (os.environ.get(name) or "").strip().lower()
    return val in {"1", "true", "yes", "on"}


_PROVENANCE_DEBUG = _env_truthy("SQUAD_PROVENANCE_DEBUG")


def _log_exception(context: str, exc: BaseException, *, include_traceback: bool = False) -> None:
    try:
        msg = f"[obsidian_judgment] WARN {context}: {type(exc).__name__}: {exc}"
        print(msg, file=sys.stderr)
        if include_traceback:
            print(traceback.format_exc().rstrip(), file=sys.stderr)
    except Exception:
        return


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _stable_sort_keys_deep(value: Any) -> Any:
    if isinstance(value, list):
        return [_stable_sort_keys_deep(v) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k in sorted(value.keys()):
            v = value[k]
            if v is None and k == "record_hash":
                # Preserve behavior parity with mk2: undefined/None record_hash is excluded
                # from the hash payload.
                continue
            out[str(k)] = _stable_sort_keys_deep(v)
        return out
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_stable_sort_keys_deep(value), ensure_ascii=False, separators=(",", ":"))


def repo_root_from_env_or_cwd() -> Path:
    root = os.environ.get("SQUAD_REPO_ROOT") or os.environ.get("SQUAD_ROOT")
    if root and root.strip():
        return Path(root).resolve()
    return Path.cwd().resolve()


def provenance_dir(repo_root: Path) -> Path:
    return repo_root / "SYSTEM" / "META" / "PROVENANCE"


def genesis_path(repo_root: Path) -> Path:
    return provenance_dir(repo_root) / "genesis.v1.json"


def judgment_path(repo_root: Path) -> Path:
    return provenance_dir(repo_root) / "judgment.v1.json"


def audit_path(repo_root: Path) -> Path:
    return provenance_dir(repo_root) / "audit.ndjson"


def _read_text_if_exists(path: Path) -> str:
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _governance_inputs(repo_root: Path) -> Dict[str, str]:
    allowlist = [
        "Invoke-SquadAdminClerk.ps1",
        "SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1",
        "SYSTEM/CONFIG/squad.config.json",
        ".github/copilot-instructions.md",
        "DOCS/GOVERNANCE.md",
        "PIPELINE_README.md",
        "AGENTS/SCHEMAS/BattleBuddy_Contract_v1.schema.json",
    ]

    out: Dict[str, str] = {}
    for rel in allowlist:
        out[rel] = _read_text_if_exists(repo_root / rel)
    return out


def compute_governance_hash(repo_root: Path) -> str:
    payload = {"files": _governance_inputs(repo_root)}
    return _sha256_hex(_stable_json(payload))


def _compute_genesis_record_hash(payload: Dict[str, Any]) -> str:
    # Hash includes all fields except record_hash itself.
    base = dict(payload)
    base.pop("record_hash", None)
    return _sha256_hex(_stable_json(base))


def ensure_genesis_record(repo_root: Path, *, write_enabled: bool = False) -> Dict[str, Any]:
    """Create a genesis record if missing and write_enabled is True.

    Returns a dict with: {created: bool, path: str}
    """

    p = genesis_path(repo_root)
    if p.exists():
        return {"created": False, "path": str(p)}

    if not write_enabled:
        return {"created": False, "path": str(p)}

    provenance_dir(repo_root).mkdir(parents=True, exist_ok=True)

    author = (os.environ.get("SQUAD_AUTHOR_IDENTITY") or os.environ.get("AUERNYX_AUTHOR_IDENTITY") or getpass.getuser() or "unknown").strip() or "unknown"
    project_id = "SQUAD"
    created_at = _now_iso()
    gov_hash = compute_governance_hash(repo_root)

    record: Dict[str, Any] = {
        "version": 1,
        "author_identity": author,
        "project_id": project_id,
        "created_at": created_at,
        "initial_governance_hash": gov_hash,
    }
    record["record_hash"] = _compute_genesis_record_hash(record)

    # Exclusive create: if exists, raise.
    p.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    append_audit(repo_root, {"kind": "genesis.created", "data": {"project_id": project_id}})
    return {"created": True, "path": str(p)}


def rotate_genesis_record(repo_root: Path, *, confirm: bool = False) -> Dict[str, Any]:
    """Explicitly rewrite the genesis record to match current governance inputs.

    This is a deliberate, audited operation intended for intentional governance updates.
    """

    if not confirm:
        raise ValueError("rotate_genesis_record requires confirm=True")

    p = genesis_path(repo_root)
    old = read_genesis_record(repo_root) or {}

    provenance_dir(repo_root).mkdir(parents=True, exist_ok=True)

    author = (
        os.environ.get("SQUAD_AUTHOR_IDENTITY")
        or os.environ.get("AUERNYX_AUTHOR_IDENTITY")
        or getpass.getuser()
        or "unknown"
    ).strip() or "unknown"
    project_id = "SQUAD"
    created_at = _now_iso()
    gov_hash = compute_governance_hash(repo_root)

    record: Dict[str, Any] = {
        "version": 1,
        "author_identity": author,
        "project_id": project_id,
        "created_at": created_at,
        "initial_governance_hash": gov_hash,
    }
    record["record_hash"] = _compute_genesis_record_hash(record)

    p.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    append_audit(
        repo_root,
        {
            "kind": "genesis.rotated",
            "data": {
                "old_governance_hash": old.get("initial_governance_hash"),
                "new_governance_hash": gov_hash,
            },
        },
    )

    return {"rotated": True, "path": str(p), "governance_hash": gov_hash}


def read_genesis_record(repo_root: Path) -> Optional[Dict[str, Any]]:
    p = genesis_path(repo_root)
    try:
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        _log_exception(f"read_genesis_record failed (path={p})", e, include_traceback=_PROVENANCE_DEBUG)
        return None


def verify_provenance(repo_root: Path) -> ProvenanceStatus:
    genesis = read_genesis_record(repo_root)
    if not genesis:
        return ProvenanceStatus(
            ok=False,
            code="genesis_missing",
            reason="Genesis record missing",
            details={"expected_path": str(genesis_path(repo_root))},
        )

    try:
        base = {
            "version": genesis.get("version"),
            "author_identity": genesis.get("author_identity"),
            "project_id": genesis.get("project_id"),
            "created_at": genesis.get("created_at"),
            "initial_governance_hash": genesis.get("initial_governance_hash"),
        }

        computed = _compute_genesis_record_hash({**base, "record_hash": None})
        recorded = str(genesis.get("record_hash") or "")
        if not recorded or recorded != computed:
            return ProvenanceStatus(
                ok=False,
                code="genesis_hash_mismatch",
                reason="Genesis record hash mismatch",
                details={"recorded": recorded, "computed": computed},
            )

        if str(genesis.get("project_id") or "") != "SQUAD":
            return ProvenanceStatus(
                ok=False,
                code="project_id_mismatch",
                reason="Project identifier mismatch",
                details={"declared": genesis.get("project_id"), "expected": "SQUAD"},
            )

        observed_gov = compute_governance_hash(repo_root)
        declared_gov = str(genesis.get("initial_governance_hash") or "")
        if declared_gov != observed_gov:
            return ProvenanceStatus(
                ok=False,
                code="governance_hash_mismatch",
                reason="Governance hash mismatch",
                details={"declared": declared_gov, "observed": observed_gov},
            )

        return ProvenanceStatus(ok=True)

    except Exception as e:
        return ProvenanceStatus(
            ok=False,
            code="genesis_parse_error",
            reason="Genesis record invalid",
            details={"error": str(e)},
        )


def append_audit(repo_root: Path, event: Dict[str, Any]) -> None:
    try:
        provenance_dir(repo_root).mkdir(parents=True, exist_ok=True)
        entry = {"ts": _now_iso(), **event}
        with audit_path(repo_root).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        if _PROVENANCE_DEBUG:
            _log_exception("append_audit failed", e, include_traceback=True)
        # audit is best-effort
        return


def read_judgment(repo_root: Path) -> Optional[Dict[str, Any]]:
    p = judgment_path(repo_root)
    try:
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        _log_exception(f"read_judgment failed (path={p})", e, include_traceback=_PROVENANCE_DEBUG)
        return None


def is_judgment_active(repo_root: Path) -> bool:
    j = read_judgment(repo_root)
    return bool(j and j.get("active") is True)


def activate_judgment(repo_root: Path, failure: ProvenanceStatus) -> Dict[str, Any]:
    provenance_dir(repo_root).mkdir(parents=True, exist_ok=True)

    record = {
        "active": True,
        "activated_at": _now_iso(),
        "failure": {
            "code": failure.code,
            "reason": failure.reason,
            "details": failure.details,
        },
    }

    judgment_path(repo_root).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    append_audit(repo_root, {"kind": "judgment.activated", "data": record.get("failure")})
    return record


def clear_judgment(repo_root: Path) -> bool:
    try:
        p = judgment_path(repo_root)
        if p.is_file():
            p.unlink()
        append_audit(repo_root, {"kind": "judgment.cleared"})
        return True
    except Exception as e:
        if _PROVENANCE_DEBUG:
            _log_exception("clear_judgment failed", e, include_traceback=True)
        return False


def status_report(repo_root: Path) -> Dict[str, Any]:
    prov = verify_provenance(repo_root)
    j = read_judgment(repo_root)

    return {
        "repo_root": str(repo_root),
        "provenance": {
            "ok": prov.ok,
            "code": prov.code,
            "reason": prov.reason,
            "details": prov.details,
        },
        "judgment": {
            "active": bool(j and j.get("active") is True),
            "record": j,
            "path": str(judgment_path(repo_root)),
        },
        "paths": {
            "dir": str(provenance_dir(repo_root)),
            "genesis": str(genesis_path(repo_root)),
            "judgment": str(judgment_path(repo_root)),
            "audit": str(audit_path(repo_root)),
        },
    }

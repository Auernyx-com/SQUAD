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
    except Exception as e:
        _log_exception(f"_read_text_if_exists failed (path={path})", e, include_traceback=_PROVENANCE_DEBUG)
        return ""


def _governance_inputs(repo_root: Path) -> Dict[str, str]:
    allowlist = [
        "Invoke-SquadAdminClerk.ps1",
        "SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1",
        "SYSTEM/CONFIG/squad.config.json",
        ".github/copilot-instructions.md",
        "DOCS/GOVERNANCE.md",
        "PIPELINE_README.md",
        "AGENTS/SCHEMAS/Pathfinder_Contract_v1.schema.json",
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

    Refuses while an active tamper-classified judgment exists (see
    _restoration_required) — rotation recomputes the trusted baseline from
    whatever governance files exist RIGHT NOW, so calling it while a
    governance_hash_mismatch judgment is unresolved would silently accept
    the still-unverified (possibly still-tampered) state as the new genesis
    truth, with nothing but a --confirm flag standing in for actual proof.
    That's the exact bypass clear_judgment() was hardened against: this
    closes the same hole reachable through a different function. Resolve the
    judgment via clear_judgment() with a verified restoration_proof first.
    """

    if not confirm:
        raise ValueError("rotate_genesis_record requires confirm=True")

    existing_judgment = read_judgment(repo_root)
    if existing_judgment and existing_judgment.get("active") is True and _restoration_required(existing_judgment):
        append_audit(
            repo_root,
            {"kind": "genesis.rotate_refused", "data": {"reason": "active_tamper_judgment_unresolved"}},
        )
        raise RuntimeError(
            "rotate_genesis_record refused: an active tamper-classified judgment "
            "(e.g. governance_hash_mismatch) is unresolved. Resolve it via "
            "clear_judgment() with a verified restoration_proof before rotating genesis."
        )

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
        return json.loads(p.read_text(encoding="utf-8-sig"))
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
        return json.loads(p.read_text(encoding="utf-8-sig"))
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
        if not p.is_file():
            return True

        judgment = read_judgment(repo_root) or {}

        if _restoration_required(judgment):
            proof = _restoration_proof(judgment)
            if not proof:
                append_audit(repo_root, {"kind": "judgment.clear_refused", "data": {"reason": "restoration_proof_missing"}})
                raise RuntimeError("restoration_proof_missing")

            ref = str(proof.get("ref") or "").strip()
            sha = str(proof.get("sha256") or "").strip()
            if not ref or not sha:
                append_audit(repo_root, {"kind": "judgment.clear_refused", "data": {"reason": "restoration_proof_missing"}})
                raise RuntimeError("restoration_proof_missing")

            # Best-effort verification: if ref points to a local file, ensure it exists and matches sha256.
            ref_candidate = Path(ref)
            ref_path = (ref_candidate if ref_candidate.is_absolute() else (repo_root / ref_candidate)).resolve()
            if not ref_path.is_file():
                append_audit(
                    repo_root,
                    {
                        "kind": "judgment.clear_refused",
                        "data": {"reason": "restoration_proof_ref_missing", "ref": ref},
                    },
                )
                raise RuntimeError("restoration_proof_ref_missing")

            data = ref_path.read_bytes()
            computed = hashlib.sha256(data).hexdigest()
            if computed.lower() != sha.lower():
                append_audit(
                    repo_root,
                    {
                        "kind": "judgment.clear_refused",
                        "data": {"reason": "restoration_proof_hash_mismatch", "ref": ref},
                    },
                )
                raise RuntimeError("restoration_proof_hash_mismatch")

            # CRITICAL: everything above only proves `ref` is a real file
            # whose bytes match `sha` -- a tautology, satisfiable by ANY
            # real file paired with its own real hash. It proves nothing
            # about whether the actual tampered governance file was
            # restored. Confirmed directly with a probe before this fix:
            # tampering with a governance file, activating judgment, then
            # calling clear_judgment() with an unrelated file (never
            # touched by the tamper) as "restoration_proof" succeeded --
            # is_judgment_active() went False while
            # verify_provenance(repo_root) still reported
            # governance_hash_mismatch against the SAME tampered content.
            # The tamper alarm was silenced with the tamper still in place,
            # and rotate_genesis_record()'s own docstring says it trusts
            # clear_judgment() having required "a verified restoration_proof"
            # before it will rotate -- so this bypass could go on to launder
            # tampered content into a new trusted baseline.
            #
            # The only proof that actually proves anything is re-running the
            # real check: does the governance state match genesis again,
            # right now? ref/sha are kept as a required audit trail of what
            # restoration evidence was cited, but they no longer stand in
            # for verification -- this does.
            post_restore = verify_provenance(repo_root)
            if not post_restore.ok:
                append_audit(
                    repo_root,
                    {
                        "kind": "judgment.clear_refused",
                        "data": {
                            "reason": "governance_still_mismatched",
                            "ref": ref,
                            "verify_code": post_restore.code,
                            "verify_details": post_restore.details,
                        },
                    },
                )
                raise RuntimeError("governance_still_mismatched")

        p.unlink()
        append_audit(repo_root, {"kind": "judgment.cleared"})
        return True
    except Exception as e:
        if _PROVENANCE_DEBUG:
            _log_exception("clear_judgment failed", e, include_traceback=True)
        return False


def _restoration_required(judgment: Dict[str, Any]) -> bool:
    """Return True when judgment represents author/core governance tamper.

    Supports current v1 record shape (failure.code) and future v1 schema shape (decision.restoration_required).
    """

    try:
        failure = judgment.get("failure") or {}
        code = str(failure.get("code") or "")
        if code == "governance_hash_mismatch":
            return True

        decision = judgment.get("decision") or {}
        if isinstance(decision, dict) and decision.get("restoration_required") is True:
            return True

        return False
    except Exception:
        return False


def _restoration_proof(judgment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        decision = judgment.get("decision") or {}
        if isinstance(decision, dict):
            proof = decision.get("restoration_proof")
            if isinstance(proof, dict):
                return proof
        proof2 = judgment.get("restoration_proof")
        if isinstance(proof2, dict):
            return proof2
        return None
    except Exception:
        return None


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

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ledger_v1 import append_receipt


@dataclass(frozen=True)
class DecisionResult:
    branch_id: str
    canonical_event_id: str
    decision: str  # allow | deny | advisory | insufficient_context
    reason_codes: List[str]
    evidence_refs: List[str]


REQUIRED_TOP_LEVEL = {
    "canonical_event_id",
    "canonical_payload_digest",
    "parser_version",
}

AGENT_VERSION = "auernyx-branch-cli@0.1.0"


def _read_envelope_from_stdin() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("Empty stdin; expected envelope JSON")
    return json.loads(raw)


def _read_envelope_from_file(path: str) -> Dict[str, Any]:
    # Accept UTF-8 with or without BOM.
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _canonicalize_payload(payload_obj: Any) -> str:
    # Level-1 canonicalization: minified JSON, UTF-8, stable insertion-order keys.
    # Python 3.7+ preserves dict insertion order; we do NOT sort keys.
    return json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _missing_required_fields(envelope: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for key in sorted(REQUIRED_TOP_LEVEL):
        if envelope.get(key) is None or (isinstance(envelope.get(key), str) and not str(envelope.get(key)).strip()):
            missing.append(key)
    return missing


def evaluate(envelope: Dict[str, Any], *, explain: bool = False, input_source: str = "unknown") -> Dict[str, Any]:
    branch_id = str(envelope.get("branch_id") or "auernyx-agent")
    canonical_event_id = str(envelope.get("canonical_event_id") or "MISSING")

    missing = _missing_required_fields(envelope)
    if missing:
        return {
            "branch_id": branch_id,
            "canonical_event_id": canonical_event_id,
            "decision": "insufficient_context",
            "reason_codes": [
                *(f"INPUT_MISSING_{k.upper()}" for k in missing),
            ],
            "evidence_refs": [],
        }

    # Digest integrity check (Level 1)
    payload_obj = envelope.get("canonical_payload")
    if payload_obj is None:
        return {
            "branch_id": branch_id,
            "canonical_event_id": canonical_event_id,
            "decision": "insufficient_context",
            "reason_codes": ["INPUT_MISSING_CANONICAL_PAYLOAD"],
            "evidence_refs": [],
        }

    claimed = str(envelope.get("canonical_payload_digest") or "").strip()

    # Prefer the emitter-provided canonical bytes string when present.
    raw_payload_json = envelope.get("canonical_payload_json")
    if isinstance(raw_payload_json, str) and raw_payload_json.strip():
        # If both representations exist, they must agree.
        try:
            raw_obj = json.loads(raw_payload_json)
        except Exception:
            raw_obj = None

        if raw_obj is None:
            return {
                "branch_id": branch_id,
                "canonical_event_id": canonical_event_id,
                "decision": "deny",
                "reason_codes": ["CANONICAL_PAYLOAD_JSON_PARSE_FAIL"],
                "evidence_refs": [
                    "tools/ygg/auernyx_branch_cli.py",
                    "tools/ygg/emit-event.ps1",
                    claimed,
                ],
                "receipt": {
                    "agent_version": AGENT_VERSION,
                    "input_source": input_source,
                    "received_payload_digest": claimed,
                    "recomputed_payload_digest": "(not computed)",
                    "match": False,
                    "parser_version": str(envelope.get("parser_version") or ""),
                },
            }

        if raw_obj != payload_obj:
            # Digest may still match raw_payload_json, but the object was altered.
            return {
                "branch_id": branch_id,
                "canonical_event_id": canonical_event_id,
                "decision": "deny",
                "reason_codes": [
                    "CANONICAL_PAYLOAD_OBJECT_MISMATCH",
                    "POSSIBLE_TAMPERING",
                ],
                "evidence_refs": [
                    "tools/ygg/auernyx_branch_cli.py",
                    "tools/ygg/emit-event.ps1",
                    claimed,
                ],
                "receipt": {
                    "agent_version": AGENT_VERSION,
                    "input_source": input_source,
                    "received_payload_digest": claimed,
                    "recomputed_payload_digest": "(not computed)",
                    "match": False,
                    "parser_version": str(envelope.get("parser_version") or ""),
                },
            }

        payload_json = raw_payload_json
        computed = f"sha256:{_sha256_hex_utf8(payload_json)}"
    else:
        payload_json = _canonicalize_payload(payload_obj)
        computed = f"sha256:{_sha256_hex_utf8(payload_json)}"

    receipt = {
        "agent_version": AGENT_VERSION,
        "input_source": input_source,
        "received_payload_digest": claimed,
        "recomputed_payload_digest": computed,
        "match": computed == claimed,
        "parser_version": str(envelope.get("parser_version") or ""),
    }

    evidence_refs = [
        "tools/ygg/auernyx_branch_cli.py",
        "tools/ygg/emit-event.ps1",
        claimed,
    ]

    if computed != claimed:
        out = {
            "branch_id": branch_id,
            "canonical_event_id": canonical_event_id,
            "decision": "deny",
            "reason_codes": [
                "DIGEST_MISMATCH",
                "CANONICALIZATION_LEVEL1_INTEGRITY_FAIL",
            ],
            "evidence_refs": evidence_refs + [f"computed:{computed}"],
            "receipt": receipt,
        }
        if explain:
            out["explain_decision"] = {
                "claimed": claimed,
                "computed": computed,
                "payload_json": payload_json,
            }
        return out

    intent = None
    try:
        intent = str((payload_obj or {}).get("intent") or "")
    except Exception:
        intent = ""

    reason_codes = [
        "CANONICAL_FIELDS_PRESENT",
        "DIGEST_VERIFIED",
    ]

    # Conservative default: advisory unless explicitly requesting a mutating action.
    decision = "advisory"

    # If someone tries to smuggle side effects, deny.
    if intent.strip().lower() in {"write", "mutate", "push", "network"}:
        decision = "deny"
        reason_codes.append("INTENT_SIDE_EFFECT_NOT_ALLOWED")

    return {
        "branch_id": branch_id,
        "canonical_event_id": canonical_event_id,
        "decision": decision,
        "reason_codes": reason_codes,
        "evidence_refs": evidence_refs,
        "receipt": receipt,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Auernyx Branch CLI (Level-1 envelope evaluator)")
    parser.add_argument("--input", default=None, help="Use '-' to read envelope JSON from stdin")
    parser.add_argument("--input-file", default=None, help="Read envelope JSON from this file")
    parser.add_argument("--explain-decision", action="store_true")
    parser.add_argument("--write-receipt", action="store_true", help="Append a Level-2 receipt + hash-chain into canon/")
    parser.add_argument("--canon-root", default="./canon", help="Canon root directory for receipts/ledger")

    args = parser.parse_args()

    input_source = "unknown"

    if args.input_file:
        env = _read_envelope_from_file(args.input_file)
        input_source = "file"
    elif args.input == "-":
        env = _read_envelope_from_stdin()
        input_source = "stdin"
    else:
        raise SystemExit("Provide --input - OR --input-file <path>")

    out = evaluate(env, explain=bool(args.explain_decision), input_source=input_source)

    # Level 2: persist receipts + enforce replay protection (agent-owned side effects).
    if args.write_receipt:
        canon_root = Path(args.canon_root).expanduser().resolve()
        try:
            receipt_meta = append_receipt(
                canon_root=canon_root,
                envelope=env,
                decision_obj=out,
                input_source=input_source,
                agent_version=AGENT_VERSION,
            )
            out.setdefault("reason_codes", []).append("RECEIPT_HASH_CHAIN_ADVANCED")
            out.setdefault("reason_codes", []).append("RECEIPT_CANONICAL_BYTES_VERIFIED")
            out.setdefault("evidence_refs", []).extend(
                [
                    receipt_meta["receipt_path"],
                    receipt_meta["receipt_hash"],
                    receipt_meta["head_path"],
                    receipt_meta["index_path"],
                    receipt_meta["digest_index_path"],
                ]
            )
            out["receipt_ledger"] = receipt_meta
        except ValueError as e:
            code = str(e)
            if code.startswith("LEDGER_TAMPER_DETECTED"):
                out["decision"] = "deny"
                out.setdefault("reason_codes", []).append("LEDGER_TAMPER_DETECTED")
            elif code == "REPLAY_EVENT_ID":
                out["decision"] = "deny"
                out.setdefault("reason_codes", []).append("REPLAY_EVENT_ID")
            elif code == "REPLAY_PAYLOAD_DIGEST":
                out["decision"] = "deny"
                out.setdefault("reason_codes", []).append("REPLAY_PAYLOAD_DIGEST")
            else:
                out["decision"] = "deny"
                out.setdefault("reason_codes", []).append("RECEIPT_APPEND_FAILED")

            out.setdefault("evidence_refs", []).append(f"canon_root:{str(canon_root.as_posix())}")
            out["receipt_ledger_error"] = code
    sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

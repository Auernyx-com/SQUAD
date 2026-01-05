from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


GENESIS = "GENESIS"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_hex_utf8(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonicalize_json(obj: Any) -> str:
    # Level-2 law: stable minified JSON bytes from insertion-order keys.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8-sig").strip()


def write_text_no_bom(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    # UTF-8 without BOM
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    line = canonicalize_json(obj)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.write("\n")


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _iter() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                yield json.loads(line)

    return _iter()


@dataclass(frozen=True)
class ReceiptPaths:
    canon_root: Path

    @property
    def receipts_dir(self) -> Path:
        return self.canon_root / "receipts"

    @property
    def ledger_dir(self) -> Path:
        return self.canon_root / "ledger"

    @property
    def head_file(self) -> Path:
        return self.ledger_dir / "HEAD"

    @property
    def index_file(self) -> Path:
        return self.ledger_dir / "INDEX.jsonl"

    @property
    def digest_index_file(self) -> Path:
        return self.ledger_dir / "digest_index.jsonl"


def compute_agent_receipt_id(
    *,
    canonical_event_id: str,
    canonical_payload_digest: str,
    agent_version: str,
    parser_version: str,
) -> str:
    raw = f"receipt:v1|{canonical_event_id}|{canonical_payload_digest}|{agent_version}|{parser_version}"
    return _sha256_hex_utf8(raw)


def _latest_index_hash(index_path: Path) -> Optional[str]:
    last: Optional[str] = None
    for row in iter_jsonl(index_path):
        rh = row.get("receipt_hash")
        if isinstance(rh, str) and rh.strip():
            last = rh.strip()
    return last


def assert_ledger_head_consistent(paths: ReceiptPaths) -> Optional[str]:
    head = read_text(paths.head_file)
    if head is None:
        return None

    head = head.strip()
    if not head:
        return None

    last_index = _latest_index_hash(paths.index_file)
    if last_index is None:
        # HEAD exists but index is empty/missing -> tamper or partial state.
        raise ValueError("LEDGER_TAMPER_DETECTED: HEAD exists but INDEX has no entries")

    if last_index != head:
        raise ValueError(
            f"LEDGER_TAMPER_DETECTED: HEAD mismatch. head={head} index_last={last_index}"
        )

    return head


def is_replay_event_id(paths: ReceiptPaths, canonical_event_id: str) -> bool:
    for row in iter_jsonl(paths.index_file):
        if row.get("canonical_event_id") == canonical_event_id:
            return True
    return False


def is_replay_payload_digest(paths: ReceiptPaths, canonical_payload_digest: str) -> bool:
    for row in iter_jsonl(paths.digest_index_file):
        if row.get("canonical_payload_digest") == canonical_payload_digest:
            return True
    return False


def build_receipt_body(
    *,
    agent_receipt_id: str,
    decision_timestamp_utc: str,
    prev_receipt_hash: str,
    branch_id: str,
    canonical_event_id: str,
    canonical_payload_digest: str,
    parser_version: str,
    agent_version: str,
    input_source: str,
    received_payload_digest: str,
    recomputed_payload_digest: str,
    match: bool,
    decision: str,
    reason_codes: list[str],
    evidence_refs: list[str],
) -> Dict[str, Any]:
    # Insertion order defines canonical bytes.
    return {
        "receipt_version": 1,
        "agent_receipt_id": agent_receipt_id,
        "decision_timestamp_utc": decision_timestamp_utc,
        "prev_receipt_hash": prev_receipt_hash,
        "branch_id": branch_id,
        "canonical_event_id": canonical_event_id,
        "canonical_payload_digest": canonical_payload_digest,
        "parser_version": parser_version,
        "agent_version": agent_version,
        "input_source": input_source,
        "received_payload_digest": received_payload_digest,
        "recomputed_payload_digest": recomputed_payload_digest,
        "match": match,
        "decision": decision,
        "reason_codes": reason_codes,
        "evidence_refs": evidence_refs,
    }


def receipt_filename(*, canonical_event_id: str, agent_receipt_id: str) -> str:
    # Windows-safe: keep underscores; receipt id is hex.
    return f"RCT_{canonical_event_id}_{agent_receipt_id}.json"


def append_receipt(
    *,
    canon_root: Path,
    envelope: Dict[str, Any],
    decision_obj: Dict[str, Any],
    input_source: str,
    agent_version: str,
) -> Dict[str, Any]:
    paths = ReceiptPaths(canon_root=canon_root)

    canonical_event_id = str(envelope.get("canonical_event_id") or "")
    canonical_payload_digest = str(envelope.get("canonical_payload_digest") or "")
    parser_version = str(envelope.get("parser_version") or "")
    branch_id = str(envelope.get("branch_id") or "")

    if not canonical_event_id or not canonical_payload_digest or not parser_version:
        raise ValueError("Receipt append requires canonical_event_id, canonical_payload_digest, parser_version")

    # Ledger consistency check before any replay checks.
    head = assert_ledger_head_consistent(paths)

    if is_replay_event_id(paths, canonical_event_id):
        raise ValueError("REPLAY_EVENT_ID")

    if is_replay_payload_digest(paths, canonical_payload_digest):
        raise ValueError("REPLAY_PAYLOAD_DIGEST")

    prev_hash = head if head else GENESIS

    receipt_id = compute_agent_receipt_id(
        canonical_event_id=canonical_event_id,
        canonical_payload_digest=canonical_payload_digest,
        agent_version=agent_version,
        parser_version=parser_version,
    )

    ts = _utc_now_iso()

    # Expect decision_obj to contain a receipt block (Level 2 contract)
    receipt_block = decision_obj.get("receipt") or {}
    received = str(receipt_block.get("received_payload_digest") or "")
    recomputed = str(receipt_block.get("recomputed_payload_digest") or "")
    match = bool(receipt_block.get("match"))

    body = build_receipt_body(
        agent_receipt_id=receipt_id,
        decision_timestamp_utc=ts,
        prev_receipt_hash=prev_hash,
        branch_id=branch_id,
        canonical_event_id=canonical_event_id,
        canonical_payload_digest=canonical_payload_digest,
        parser_version=parser_version,
        agent_version=agent_version,
        input_source=input_source,
        received_payload_digest=received,
        recomputed_payload_digest=recomputed,
        match=match,
        decision=str(decision_obj.get("decision") or ""),
        reason_codes=list(decision_obj.get("reason_codes") or []),
        evidence_refs=list(decision_obj.get("evidence_refs") or []),
    )

    receipt_json = canonicalize_json(body)
    receipt_hash = f"sha256:{_sha256_hex_utf8(receipt_json)}"

    receipt_file = paths.receipts_dir / receipt_filename(canonical_event_id=canonical_event_id, agent_receipt_id=receipt_id)
    if receipt_file.exists():
        raise ValueError("RECEIPT_ALREADY_EXISTS")

    # Persist receipt file.
    receipt_file_obj = {
        "receipt_json": receipt_json,
        "receipt_hash": receipt_hash,
        "receipt": body,
    }
    write_text_no_bom(receipt_file, json.dumps(receipt_file_obj, indent=2, ensure_ascii=False) + "\n")

    # Advance ledger HEAD and append indexes.
    write_text_no_bom(paths.head_file, receipt_hash + "\n")

    append_jsonl(
        paths.index_file,
        {
            "agent_receipt_id": receipt_id,
            "receipt_hash": receipt_hash,
            "canonical_event_id": canonical_event_id,
            "canonical_payload_digest": canonical_payload_digest,
            "ts": ts,
            "agent_version": agent_version,
            "parser_version": parser_version,
        },
    )

    append_jsonl(
        paths.digest_index_file,
        {
            "canonical_payload_digest": canonical_payload_digest,
            "canonical_event_id": canonical_event_id,
            "agent_receipt_id": receipt_id,
            "ts": ts,
        },
    )

    return {
        "agent_receipt_id": receipt_id,
        "receipt_hash": receipt_hash,
        "receipt_path": str(receipt_file.as_posix()),
        "prev_receipt_hash": prev_hash,
        "head_path": str(paths.head_file.as_posix()),
        "index_path": str(paths.index_file.as_posix()),
        "digest_index_path": str(paths.digest_index_file.as_posix()),
    }

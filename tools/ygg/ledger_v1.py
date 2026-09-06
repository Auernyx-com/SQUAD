from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


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


def _index_receipt_hashes(index_rows: List[Dict[str, Any]]) -> List[str]:
    return [
        row.get("receipt_hash").strip()
        for row in index_rows
        if isinstance(row.get("receipt_hash"), str) and row.get("receipt_hash").strip()
    ]


def _latest_index_hash(index_path: Path) -> Optional[str]:
    hashes = _index_receipt_hashes(list(iter_jsonl(index_path)))
    return hashes[-1] if hashes else None


def assert_ledger_head_consistent(
    paths: ReceiptPaths, *, index_rows: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """Verify (and where safe, self-heal) that HEAD matches the tail of INDEX.

    HEAD and INDEX.jsonl are written as two separate operations (see
    append_receipt) — a process crash, kill, or power loss between them
    leaves one advanced without the other. Historically this raised
    LEDGER_TAMPER_DETECTED for that case indistinguishably from real
    tampering, permanently wedging the ledger after any ordinary interrupted
    write (confirmed with a direct probe: writing HEAD forward with no
    matching INDEX entry, then calling this on the next legitimate append,
    raised LEDGER_TAMPER_DETECTED even though nothing had been tampered
    with).

    Self-healing is safe in exactly one case: HEAD points to a hash that
    appears SOMEWHERE in this ledger's own recorded history (INDEX is the
    append-only source of truth here). That can only mean HEAD is stale --
    the ledger already durably recorded a receipt at or past that point, so
    advancing HEAD to the true tail materializes no new information and
    can't be exploited to accept anything not already committed to INDEX.

    HEAD pointing to a value that never appears in INDEX at all is NOT
    self-healed -- that's not explainable by an interrupted write and still
    raises LEDGER_TAMPER_DETECTED.
    """
    head = read_text(paths.head_file)
    if head is None:
        return None

    head = head.strip()
    if not head:
        return None

    rows = index_rows if index_rows is not None else list(iter_jsonl(paths.index_file))
    hashes = _index_receipt_hashes(rows)

    if not hashes:
        # HEAD exists but index is empty/missing -> tamper or partial state.
        raise ValueError("LEDGER_TAMPER_DETECTED: HEAD exists but INDEX has no entries")

    last_index = hashes[-1]
    if last_index == head:
        return head

    if head in hashes:
        # Stale, not tampered -- fast-forward HEAD to the true tail.
        write_text_no_bom(paths.head_file, last_index + "\n")
        return last_index

    raise ValueError(
        f"LEDGER_TAMPER_DETECTED: HEAD mismatch. head={head} index_last={last_index}"
    )


def _conflicting_event_id(index_rows: List[Dict[str, Any]], canonical_event_id: str, receipt_id: str) -> bool:
    # A genuine replay: this event_id is already recorded under a DIFFERENT
    # receipt_id. Same event_id + same receipt_id means this is a resumed
    # retry of the identical receipt (same event, digest, and versions),
    # not a conflict -- callers check that case separately.
    return any(
        row.get("canonical_event_id") == canonical_event_id and row.get("agent_receipt_id") != receipt_id
        for row in index_rows
    )


def _conflicting_payload_digest(digest_rows: List[Dict[str, Any]], canonical_payload_digest: str, receipt_id: str) -> bool:
    return any(
        row.get("canonical_payload_digest") == canonical_payload_digest and row.get("agent_receipt_id") != receipt_id
        for row in digest_rows
    )


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
    """Append one receipt to the ledger, or safely finish an interrupted one.

    append_receipt performs three separate writes -- the receipt file, then
    INDEX.jsonl, then digest_index.jsonl, then HEAD -- and a process
    crash/kill/power-loss can land between any two of them. Every step below
    is therefore idempotent, keyed on the deterministic agent_receipt_id
    (a pure hash of event_id + payload_digest + agent/parser versions, with
    no timestamp or randomness): re-running append_receipt for the exact
    same logical event after a partial write completes whatever didn't
    finish last time, instead of raising RECEIPT_ALREADY_EXISTS /
    REPLAY_EVENT_ID / REPLAY_PAYLOAD_DIGEST / LEDGER_TAMPER_DETECTED for
    what is actually the same request retried. A genuinely different event
    reusing the same canonical_event_id or payload digest (a real replay,
    not a resume) still raises exactly as before.
    """
    paths = ReceiptPaths(canon_root=canon_root)

    canonical_event_id = str(envelope.get("canonical_event_id") or "")
    canonical_payload_digest = str(envelope.get("canonical_payload_digest") or "")
    parser_version = str(envelope.get("parser_version") or "")
    branch_id = str(envelope.get("branch_id") or "")

    if not canonical_event_id or not canonical_payload_digest or not parser_version:
        raise ValueError("Receipt append requires canonical_event_id, canonical_payload_digest, parser_version")

    receipt_id = compute_agent_receipt_id(
        canonical_event_id=canonical_event_id,
        canonical_payload_digest=canonical_payload_digest,
        agent_version=agent_version,
        parser_version=parser_version,
    )
    receipt_file = paths.receipts_dir / receipt_filename(canonical_event_id=canonical_event_id, agent_receipt_id=receipt_id)

    index_rows = list(iter_jsonl(paths.index_file))
    digest_rows = list(iter_jsonl(paths.digest_index_file))

    if receipt_file.exists():
        # Resume: this exact receipt was already durably written. Verify
        # it's genuinely the same content (not a hash collision or a
        # corrupted file) before treating it as safe to resume from.
        try:
            existing = json.loads(read_text(receipt_file) or "")
        except Exception as exc:
            raise ValueError(f"RECEIPT_FILE_CORRUPT: {receipt_file} ({exc})") from exc

        receipt_hash = existing.get("receipt_hash")
        body = existing.get("receipt")
        if not isinstance(receipt_hash, str) or not receipt_hash or not isinstance(body, dict):
            raise ValueError(f"RECEIPT_FILE_CORRUPT: {receipt_file} (missing receipt_hash/receipt)")
        if body.get("canonical_event_id") != canonical_event_id or body.get("canonical_payload_digest") != canonical_payload_digest:
            raise ValueError(f"RECEIPT_FILE_CORRUPT: {receipt_file} (content does not match request)")

        prev_hash = str(body.get("prev_receipt_hash") or GENESIS)
    else:
        # Not a resume -- a conflicting record under a DIFFERENT receipt_id
        # for the same event or digest is a genuine replay, not a retry.
        if _conflicting_event_id(index_rows, canonical_event_id, receipt_id):
            raise ValueError("REPLAY_EVENT_ID")
        if _conflicting_payload_digest(digest_rows, canonical_payload_digest, receipt_id):
            raise ValueError("REPLAY_PAYLOAD_DIGEST")

        head = assert_ledger_head_consistent(paths, index_rows=index_rows)
        prev_hash = head if head else GENESIS

        ts = _utc_now_iso()
        receipt_block = decision_obj.get("receipt") or {}
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
            received_payload_digest=str(receipt_block.get("received_payload_digest") or ""),
            recomputed_payload_digest=str(receipt_block.get("recomputed_payload_digest") or ""),
            match=bool(receipt_block.get("match")),
            decision=str(decision_obj.get("decision") or ""),
            reason_codes=list(decision_obj.get("reason_codes") or []),
            evidence_refs=list(decision_obj.get("evidence_refs") or []),
        )
        receipt_json = canonicalize_json(body)
        receipt_hash = f"sha256:{_sha256_hex_utf8(receipt_json)}"

        write_text_no_bom(
            receipt_file,
            json.dumps({"receipt_json": receipt_json, "receipt_hash": receipt_hash, "receipt": body}, indent=2, ensure_ascii=False) + "\n",
        )

    # From here on, whether just-written or resumed, finish whatever
    # bookkeeping is still missing. Each step checks first so a resume
    # never double-appends.
    if not any(row.get("agent_receipt_id") == receipt_id for row in index_rows):
        append_jsonl(
            paths.index_file,
            {
                "agent_receipt_id": receipt_id,
                "receipt_hash": receipt_hash,
                "canonical_event_id": canonical_event_id,
                "canonical_payload_digest": canonical_payload_digest,
                "ts": _utc_now_iso(),
                "agent_version": agent_version,
                "parser_version": parser_version,
            },
        )
        index_rows = list(iter_jsonl(paths.index_file))

    if not any(row.get("agent_receipt_id") == receipt_id for row in digest_rows):
        append_jsonl(
            paths.digest_index_file,
            {
                "canonical_payload_digest": canonical_payload_digest,
                "canonical_event_id": canonical_event_id,
                "agent_receipt_id": receipt_id,
                "ts": _utc_now_iso(),
            },
        )

    # HEAD is written LAST, only after INDEX already has this receipt --
    # the only possible partial-write state from an interruption at this
    # point is "INDEX has it, HEAD hasn't caught up yet," which
    # assert_ledger_head_consistent's self-heal already covers on the next
    # call. Write it directly; this receipt is the tail either way (freshly
    # created, or a resumed completion of the last thing this call started).
    write_text_no_bom(paths.head_file, receipt_hash + "\n")

    return {
        "agent_receipt_id": receipt_id,
        "receipt_hash": receipt_hash,
        "receipt_path": str(receipt_file.as_posix()),
        "prev_receipt_hash": prev_hash,
        "head_path": str(paths.head_file.as_posix()),
        "index_path": str(paths.index_file.as_posix()),
        "digest_index_path": str(paths.digest_index_file.as_posix()),
    }


@dataclass(frozen=True)
class ChainVerificationResult:
    ok: bool
    entries_checked: int
    error: Optional[str] = None
    error_index: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


def verify_chain(canon_root: Path) -> ChainVerificationResult:
    """Walk the ENTIRE ledger end to end, verifying every link.

    assert_ledger_head_consistent only ever compares the tail of INDEX
    against HEAD -- it says nothing about entries in the middle of the
    ledger's history. Confirmed directly: prev_receipt_hash is written into
    every receipt body but was never read back or checked anywhere in this
    module before this function existed, so editing or deleting a receipt
    that isn't the very last one, or hand-editing an INDEX.jsonl row's
    cached receipt_hash, went completely undetected.

    For every entry in INDEX.jsonl, in order, this checks:
      1. The receipt file exists and its own content actually hashes to its
         own stored receipt_hash (catches a receipt file edited after the
         fact).
      2. INDEX.jsonl's cached receipt_hash for that entry matches the
         receipt file's real hash (catches an INDEX row edited to point
         somewhere else).
      3. The receipt body's own canonical_event_id / canonical_payload_digest
         match what INDEX recorded for it (catches an INDEX row rewritten to
         reference a different receipt's file).
      4. The receipt's prev_receipt_hash equals the PREVIOUS entry's hash
         (or GENESIS for the first entry) -- this is the actual chain link;
         breaking it anywhere is what a deleted, reordered, or inserted
         historical entry can't avoid doing.
    Finally, HEAD must equal the tail.

    Returns as soon as the first broken link is found, with enough detail
    (error, error_index, details) to say exactly where and how.
    """
    paths = ReceiptPaths(canon_root=canon_root)
    index_rows = list(iter_jsonl(paths.index_file))

    prev_hash_expected = GENESIS
    for i, row in enumerate(index_rows):
        receipt_id = row.get("agent_receipt_id")
        canonical_event_id = row.get("canonical_event_id")
        index_payload_digest = row.get("canonical_payload_digest")
        recorded_hash = row.get("receipt_hash")

        if not isinstance(receipt_id, str) or not receipt_id:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="INDEX_ENTRY_MISSING_RECEIPT_ID", error_index=i
            )

        receipt_file = paths.receipts_dir / receipt_filename(
            canonical_event_id=str(canonical_event_id or ""), agent_receipt_id=receipt_id
        )
        if not receipt_file.is_file():
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="RECEIPT_FILE_MISSING", error_index=i,
                details={"receipt_path": str(receipt_file)},
            )

        try:
            stored = json.loads(read_text(receipt_file) or "")
        except Exception as exc:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="RECEIPT_FILE_UNREADABLE", error_index=i,
                details={"receipt_path": str(receipt_file), "exception": str(exc)},
            )

        stored_json = stored.get("receipt_json")
        stored_hash = stored.get("receipt_hash")
        body = stored.get("receipt")
        if not isinstance(stored_json, str) or not isinstance(stored_hash, str) or not isinstance(body, dict):
            return ChainVerificationResult(ok=False, entries_checked=i, error="RECEIPT_FILE_MALFORMED", error_index=i)

        # Re-derive the canonical JSON from `receipt` (the parsed body) --
        # NOT from the stored `receipt_json` string field. The file stores
        # both side by side; trusting the stored string as ground truth
        # would miss exactly the tamper this function exists to catch
        # (confirmed with a direct probe: editing `receipt.decision` in
        # place while leaving `receipt_json`/`receipt_hash` untouched slid
        # straight past a hash check that only re-hashed the untouched
        # string). Re-canonicalizing `body` itself closes that gap.
        recomputed_json = canonicalize_json(body)
        recomputed_hash = f"sha256:{_sha256_hex_utf8(recomputed_json)}"
        if recomputed_hash != stored_hash:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="RECEIPT_CONTENT_HASH_MISMATCH", error_index=i,
                details={"stored_hash": stored_hash, "recomputed_hash": recomputed_hash},
            )
        if recomputed_json != stored_json:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="RECEIPT_JSON_BODY_DIVERGED", error_index=i,
                details={"stored_json": stored_json, "recomputed_json": recomputed_json},
            )

        if isinstance(recorded_hash, str) and recorded_hash and recorded_hash != stored_hash:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="INDEX_RECEIPT_HASH_MISMATCH", error_index=i,
                details={"index_hash": recorded_hash, "receipt_file_hash": stored_hash},
            )

        if body.get("canonical_event_id") != canonical_event_id or body.get("canonical_payload_digest") != index_payload_digest:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="INDEX_RECEIPT_IDENTITY_MISMATCH", error_index=i,
                details={
                    "index_event_id": canonical_event_id, "receipt_event_id": body.get("canonical_event_id"),
                    "index_payload_digest": index_payload_digest, "receipt_payload_digest": body.get("canonical_payload_digest"),
                },
            )

        actual_prev = str(body.get("prev_receipt_hash") or "")
        if actual_prev != prev_hash_expected:
            return ChainVerificationResult(
                ok=False, entries_checked=i, error="CHAIN_LINK_BROKEN", error_index=i,
                details={"expected_prev_hash": prev_hash_expected, "actual_prev_hash": actual_prev},
            )

        prev_hash_expected = stored_hash

    head = read_text(paths.head_file)
    if head is not None:
        head = head.strip()
        tail_hashes = _index_receipt_hashes(index_rows)
        tail = tail_hashes[-1] if tail_hashes else None
        if head and head != tail:
            return ChainVerificationResult(
                ok=False, entries_checked=len(index_rows), error="HEAD_TAIL_MISMATCH",
                details={"head": head, "tail": tail},
            )

    return ChainVerificationResult(ok=True, entries_checked=len(index_rows))

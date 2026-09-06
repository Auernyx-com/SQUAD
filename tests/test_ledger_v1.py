"""
tests/test_ledger_v1.py

tools/ygg/ledger_v1.py is a hash-chained receipt ledger. It had zero test
coverage before this file. Two real defects found by reading it end to end:

1. A PROCESS CRASH FALSELY AND PERMANENTLY TRIGGERED LEDGER_TAMPER_DETECTED.
   append_receipt() performed three separate, non-atomic writes: the
   receipt file, then HEAD, then INDEX.jsonl, then digest_index.jsonl.
   Confirmed with a direct probe against the pre-fix code: writing HEAD
   forward to a real value with no matching INDEX entry (simulating a
   kill between the HEAD write and the INDEX append), then calling
   append_receipt() again for a completely unrelated, legitimate next
   event, raised LEDGER_TAMPER_DETECTED -- with no way to recover other
   than manual intervention, indistinguishable from real tampering.

   Fixed by: (a) reordering writes so HEAD is written LAST, only after
   INDEX/digest_index already have the entry, and (b) making
   assert_ledger_head_consistent() self-heal the one safe case: HEAD is
   stale (points to an EARLIER entry in the ledger's own recorded
   history) rather than fabricated (points to something INDEX never
   recorded at all, which still raises). And (c) making the entire
   append_receipt() flow idempotent/resumable keyed on the deterministic
   agent_receipt_id, so retrying an interrupted append at ANY of its three
   write points completes the missing steps instead of raising
   RECEIPT_ALREADY_EXISTS / REPLAY_EVENT_ID / REPLAY_PAYLOAD_DIGEST for
   what is actually the same request retried.

2. THE "HASH CHAIN" ONLY EVER CHECKED THE TAIL, NEVER THE FULL CHAIN.
   Every receipt records prev_receipt_hash, but nothing in this module
   ever read it back or verified it before this fix -- confirmed via
   direct grep before writing any code. assert_ledger_head_consistent()
   only compares the LAST INDEX entry against HEAD; a receipt tampered
   with, deleted, or reordered anywhere else in history went completely
   undetected.

   Fixed by adding verify_chain(), which walks every entry in order and
   checks: the receipt file's content still hashes to its own stored hash
   (re-deriving the canonical JSON from the parsed `receipt` body itself,
   not trusting the stored `receipt_json` string side by side with it --
   an early version of this fix had exactly that gap, caught by testing:
   editing `receipt.decision` in place while leaving the stored
   `receipt_json`/`receipt_hash` untouched slid past a hash check that
   only re-hashed the untouched string); INDEX's cached hash for that
   entry matches; the receipt's own recorded event_id/payload_digest match
   what INDEX has for it; and prev_receipt_hash actually equals the
   previous entry's hash (GENESIS for the first). Wired into
   auernyx_branch_cli.py as --verify-chain.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "ygg"))

import ledger_v1 as lg  # noqa: E402


def _env(event_id: str, digest: str) -> dict:
    return {
        "canonical_event_id": event_id,
        "canonical_payload_digest": digest,
        "parser_version": "p1",
        "branch_id": "b1",
    }


def _decision() -> dict:
    return {
        "decision": "advisory",
        "reason_codes": [],
        "evidence_refs": [],
        "receipt": {
            "received_payload_digest": "x",
            "recomputed_payload_digest": "x",
            "match": True,
        },
    }


def _tmp_canon() -> Path:
    return Path(tempfile.mkdtemp(prefix="ygg-ledger-test-"))


class CrashRecoveryRegressionTest(unittest.TestCase):
    def test_normal_sequential_appends_build_a_valid_chain(self):
        canon = _tmp_canon()
        for i in range(3):
            lg.append_receipt(
                canon_root=canon, envelope=_env(f"e{i}", f"d{i}"),
                decision_obj=_decision(), input_source="t", agent_version="a@1",
            )
        result = lg.verify_chain(canon)
        self.assertTrue(result.ok)
        self.assertEqual(result.entries_checked, 3)

    def test_head_stale_from_an_interrupted_write_self_heals_instead_of_false_alarming(self):
        canon = _tmp_canon()
        lg.append_receipt(canon_root=canon, envelope=_env("e1", "d1"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        r2 = lg.append_receipt(canon_root=canon, envelope=_env("e2", "d2"), decision_obj=_decision(), input_source="t", agent_version="a@1")

        # Simulate the crash point: roll HEAD back to what it was BEFORE r2
        # (as if the process died after the INDEX append but before the
        # HEAD write for r2).
        paths = lg.ReceiptPaths(canon_root=canon)
        lg.write_text_no_bom(paths.head_file, r2["prev_receipt_hash"] + "\n")

        # A completely unrelated, legitimate next event must not be
        # rejected -- this is the exact bug: it used to raise
        # LEDGER_TAMPER_DETECTED here.
        r3 = lg.append_receipt(canon_root=canon, envelope=_env("e3", "d3"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        self.assertEqual(r3["prev_receipt_hash"], r2["receipt_hash"])

    def test_fabricated_head_with_no_history_backing_it_still_raises(self):
        # The self-heal must NOT cover a HEAD value that never appears
        # anywhere in the ledger's own recorded history -- that's not
        # explainable by an interrupted write.
        canon = _tmp_canon()
        lg.append_receipt(canon_root=canon, envelope=_env("h1", "hd1"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        paths = lg.ReceiptPaths(canon_root=canon)
        lg.write_text_no_bom(paths.head_file, "sha256:totally_made_up_never_existed\n")

        with self.assertRaises(ValueError) as ctx:
            lg.assert_ledger_head_consistent(paths)
        self.assertIn("LEDGER_TAMPER_DETECTED", str(ctx.exception))

    def test_resuming_after_a_crash_before_any_bookkeeping_completed(self):
        # Simulates the crash point right after the receipt file itself was
        # durably written, before INDEX/digest_index/HEAD were touched.
        canon = _tmp_canon()
        env = _env("r1", "rd1")
        decision = _decision()
        first = lg.append_receipt(canon_root=canon, envelope=env, decision_obj=decision, input_source="t", agent_version="a@1")

        paths = lg.ReceiptPaths(canon_root=canon)
        paths.index_file.unlink()
        paths.digest_index_file.unlink()
        paths.head_file.unlink()

        resumed = lg.append_receipt(canon_root=canon, envelope=env, decision_obj=decision, input_source="t", agent_version="a@1")
        self.assertEqual(resumed["receipt_hash"], first["receipt_hash"])
        result = lg.verify_chain(canon)
        self.assertTrue(result.ok)

    def test_genuine_replay_with_a_different_digest_is_still_rejected(self):
        # A resume must never be confused with an actual conflicting reuse
        # of the same event_id.
        canon = _tmp_canon()
        lg.append_receipt(canon_root=canon, envelope=_env("e1", "d1"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        with self.assertRaises(ValueError) as ctx:
            lg.append_receipt(canon_root=canon, envelope=_env("e1", "DIFFERENT_DIGEST"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        self.assertEqual(str(ctx.exception), "REPLAY_EVENT_ID")

    def test_genuine_replay_of_the_same_digest_under_a_different_event_is_still_rejected(self):
        canon = _tmp_canon()
        lg.append_receipt(canon_root=canon, envelope=_env("e1", "shared-digest"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        with self.assertRaises(ValueError) as ctx:
            lg.append_receipt(canon_root=canon, envelope=_env("DIFFERENT_EVENT", "shared-digest"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        self.assertEqual(str(ctx.exception), "REPLAY_PAYLOAD_DIGEST")


class FullChainVerificationTest(unittest.TestCase):
    def test_mid_chain_content_tampering_is_detected(self):
        canon = _tmp_canon()
        for i in range(3):
            lg.append_receipt(canon_root=canon, envelope=_env(f"t{i}", f"td{i}"), decision_obj=_decision(), input_source="t", agent_version="a@1")

        paths = lg.ReceiptPaths(canon_root=canon)
        receipt_files = sorted(paths.receipts_dir.glob("*.json"))
        first = json.loads(receipt_files[0].read_text())
        first["receipt"]["decision"] = "TAMPERED_DECISION"
        receipt_files[0].write_text(json.dumps(first))

        result = lg.verify_chain(canon)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "RECEIPT_CONTENT_HASH_MISMATCH")
        self.assertEqual(result.error_index, 0)

    def test_tampering_the_stored_json_string_alone_is_also_detected(self):
        # Regression for a gap found while building this fix: an earlier
        # version only re-hashed the stored `receipt_json` string field
        # rather than re-deriving it from the parsed `receipt` body, so
        # editing the body in place without touching the string slipped
        # through. This tests editing the OTHER representation -- both must
        # be checked against each other.
        canon = _tmp_canon()
        lg.append_receipt(canon_root=canon, envelope=_env("s1", "sd1"), decision_obj=_decision(), input_source="t", agent_version="a@1")
        paths = lg.ReceiptPaths(canon_root=canon)
        receipt_files = sorted(paths.receipts_dir.glob("*.json"))
        stored = json.loads(receipt_files[0].read_text())
        stored["receipt_json"] = stored["receipt_json"].replace("advisory", "TAMPERED")
        receipt_files[0].write_text(json.dumps(stored))

        result = lg.verify_chain(canon)
        self.assertFalse(result.ok)

    def test_deleting_a_middle_entry_breaks_the_chain_link(self):
        canon = _tmp_canon()
        for i in range(3):
            lg.append_receipt(canon_root=canon, envelope=_env(f"x{i}", f"xd{i}"), decision_obj=_decision(), input_source="t", agent_version="a@1")

        paths = lg.ReceiptPaths(canon_root=canon)
        rows = list(lg.iter_jsonl(paths.index_file))
        remaining = [rows[0], rows[2]]  # drop the middle entry
        paths.index_file.write_text("\n".join(lg.canonicalize_json(r) for r in remaining) + "\n")

        result = lg.verify_chain(canon)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "CHAIN_LINK_BROKEN")
        self.assertEqual(result.error_index, 1)

    def test_empty_ledger_verifies_as_ok(self):
        canon = _tmp_canon()
        result = lg.verify_chain(canon)
        self.assertTrue(result.ok)
        self.assertEqual(result.entries_checked, 0)


if __name__ == "__main__":
    unittest.main()

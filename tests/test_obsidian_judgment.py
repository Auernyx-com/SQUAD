"""
tests/test_obsidian_judgment.py

Regression coverage for a severe, previously-unmerged fix to
MODULES/OBSIDIAN_JUDGMENT/src/obsidian_judgment.py's clear_judgment().

Found by reviewing a stale, unmerged branch (governance/wip-provenance-mismatch,
written January 2026, never merged) that turned out to contain a real fix for
a live vulnerability still present in main as of 2026-09-05. Verified
directly before applying: clear_judgment() unconditionally deleted the
judgment file with zero verification, for EVERY failure type — including
"governance_hash_mismatch", the most severe failure code this module has,
representing tampered core/author governance files. Anyone (or any bug)
calling clear_judgment() could silently dismiss a "your core governance
files were tampered with" alarm with no proof the tampering was ever
addressed. Confirmed with a real probe against the pre-fix code: activate a
governance_hash_mismatch judgment, call clear_judgment() with nothing else,
and the judgment was gone.

Fixed by requiring a verified "restoration proof" (a file reference + SHA-256
digest that must actually match) before a tamper-classified judgment can be
cleared. Every other judgment type (e.g. genesis_missing) clears exactly as
before — this only gates the specific failure class that represents
governance/author-identity tampering.

Round 2 (2026-09-06): that fix closed the "zero verification at all" hole,
but the verification it added was itself a tautology — ref+sha256 only prove
that SOME real file matches ITS OWN real hash, which is trivially true of
any file paired with its own digest. It never checked whether the actual
tampered governance file had been restored. Confirmed directly with a
probe: tamper a real governance file, activate judgment, then call
clear_judgment() with an unrelated file (never touched by the tamper) as
"restoration_proof" — it succeeded, and verify_provenance() still reported
governance_hash_mismatch against the same tampered content immediately
after. The tamper alarm was silenced with the tamper still in place, and
rotate_genesis_record()'s own docstring says it trusts clear_judgment()
having required "a verified restoration_proof" before it will rotate — so
this could go on to launder tampered content into a new trusted baseline.
Fixed by re-running verify_provenance() after the ref/sha check and
refusing to clear unless governance state actually matches genesis again,
right now. ref/sha are kept as a required audit trail of what restoration
evidence was cited, but no longer stand in for verification.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "OBSIDIAN_JUDGMENT" / "src"))

import obsidian_judgment as oj  # noqa: E402


def _tmp_repo() -> Path:
    return Path(tempfile.mkdtemp(prefix="squad-bat-obsidian-test-"))


class ClearJudgmentRequiresRestorationProofTest(unittest.TestCase):
    def test_governance_hash_mismatch_cannot_be_cleared_without_any_proof(self):
        repo_root = _tmp_repo()
        failure = oj.ProvenanceStatus(ok=False, code="governance_hash_mismatch", reason="tampered")
        oj.activate_judgment(repo_root, failure)

        cleared = oj.clear_judgment(repo_root)

        self.assertFalse(cleared)
        self.assertTrue(oj.is_judgment_active(repo_root))

    def test_governance_hash_mismatch_clears_with_a_valid_matching_proof(self):
        # (round 2 of this fix) The original version of this test used an
        # arbitrary "restored.txt" file, unrelated to any real governance
        # file, as restoration_proof -- proving only that the file matched
        # its own claimed hash, a tautology satisfiable by ANY real file.
        # Confirmed directly with a probe before this second fix: tamper a
        # real governance file, activate judgment, then call clear_judgment()
        # with an unrelated file (never touched by the tamper) as proof --
        # it succeeded, and verify_provenance() still reported
        # governance_hash_mismatch against the SAME tampered content
        # immediately after. The tamper alarm was silenced with the tamper
        # still in place. This test now actually tampers a real governance
        # file and actually restores it byte-for-byte before expecting
        # clear_judgment() to succeed -- the only thing that should be
        # sufficient proof.
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)

        clerk = repo_root / "Invoke-SquadAdminClerk.ps1"
        original = "original clerk content\n"
        clerk.write_text(original)
        # Re-baseline genesis now that a real governance file exists with
        # known content (ensure_genesis_record above ran before this file
        # existed).
        oj.rotate_genesis_record(repo_root, confirm=True)

        clerk.write_text("TAMPERED CONTENT")
        status = oj.verify_provenance(repo_root)
        self.assertEqual(status.code, "governance_hash_mismatch")
        oj.activate_judgment(repo_root, status)

        # Actually restore the tampered file to its exact original bytes.
        clerk.write_text(original)
        sha = hashlib.sha256(clerk.read_bytes()).hexdigest()

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "Invoke-SquadAdminClerk.ps1", "sha256": sha},
        }
        jp.write_text(json.dumps(record))

        cleared = oj.clear_judgment(repo_root)

        self.assertTrue(cleared)
        self.assertFalse(oj.is_judgment_active(repo_root))

    def test_governance_hash_mismatch_refused_when_proof_is_unrelated_to_the_actual_tamper(self):
        # The exact bypass this second hardening pass closes: ref+sha256
        # that are internally consistent (a real file matching its own real
        # hash) but have nothing to do with the file that was actually
        # tampered. Must be refused even though the old check alone would
        # have accepted it.
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)

        clerk = repo_root / "Invoke-SquadAdminClerk.ps1"
        clerk.write_text("original clerk content\n")
        oj.rotate_genesis_record(repo_root, confirm=True)

        clerk.write_text("TAMPERED CONTENT")
        status = oj.verify_provenance(repo_root)
        oj.activate_judgment(repo_root, status)

        unrelated = repo_root / "unrelated_file.txt"
        unrelated.write_text("nothing to do with the tampered file")
        unrelated_sha = hashlib.sha256(unrelated.read_bytes()).hexdigest()

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "unrelated_file.txt", "sha256": unrelated_sha},
        }
        jp.write_text(json.dumps(record))

        cleared = oj.clear_judgment(repo_root)

        self.assertFalse(cleared)
        self.assertTrue(oj.is_judgment_active(repo_root))
        # The tamper must still be reported -- nothing was actually fixed.
        self.assertEqual(oj.verify_provenance(repo_root).code, "governance_hash_mismatch")

    def test_proof_with_a_hash_that_does_not_match_the_referenced_file_is_refused(self):
        repo_root = _tmp_repo()
        failure = oj.ProvenanceStatus(ok=False, code="governance_hash_mismatch", reason="tampered")
        oj.activate_judgment(repo_root, failure)

        proof_file = repo_root / "restored.txt"
        proof_file.write_text("proof of restoration")

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "restored.txt", "sha256": "0" * 64},
        }
        jp.write_text(json.dumps(record))

        cleared = oj.clear_judgment(repo_root)

        self.assertFalse(cleared)
        self.assertTrue(oj.is_judgment_active(repo_root))

    def test_proof_referencing_a_file_that_does_not_exist_is_refused(self):
        repo_root = _tmp_repo()
        failure = oj.ProvenanceStatus(ok=False, code="governance_hash_mismatch", reason="tampered")
        oj.activate_judgment(repo_root, failure)

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "does-not-exist.txt", "sha256": "0" * 64},
        }
        jp.write_text(json.dumps(record))

        cleared = oj.clear_judgment(repo_root)

        self.assertFalse(cleared)
        self.assertTrue(oj.is_judgment_active(repo_root))

    def test_non_tamper_judgment_types_still_clear_normally_no_regression(self):
        repo_root = _tmp_repo()
        failure = oj.ProvenanceStatus(ok=False, code="genesis_missing", reason="no genesis record")
        oj.activate_judgment(repo_root, failure)

        cleared = oj.clear_judgment(repo_root)

        self.assertTrue(cleared)
        self.assertFalse(oj.is_judgment_active(repo_root))

    def test_clearing_when_no_judgment_is_active_is_a_safe_no_op(self):
        repo_root = _tmp_repo()
        self.assertFalse(oj.is_judgment_active(repo_root))
        cleared = oj.clear_judgment(repo_root)
        self.assertTrue(cleared)


class RotateGenesisRecordCannotBypassClearJudgmentTest(unittest.TestCase):
    """
    Follow-on finding: rotate_genesis_record() rewrites the trusted genesis
    baseline to match whatever governance files exist RIGHT NOW. With no
    gate, it let a tamper-classified judgment be silently laundered away --
    an attacker could tamper a governance file, then call
    rotate_genesis_record(confirm=True) instead of clear_judgment(), and the
    system would accept the still-tampered state as the new legitimate
    baseline with zero proof. verify_provenance() would then report ok=True
    while judgment.v1.json sat orphaned with active=True.

    Confirmed against the pre-fix code with a direct probe: after activating
    a governance_hash_mismatch judgment, clear_judgment() correctly refused
    with no proof, but rotate_genesis_record(confirm=True) succeeded anyway
    and verify_provenance() came back ok=True immediately after.
    """

    def test_rotate_refuses_while_a_tamper_judgment_is_active(self):
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)

        gov_dir = repo_root / "SYSTEM" / "CONFIG"
        gov_dir.mkdir(parents=True, exist_ok=True)
        (gov_dir / "squad.config.json").write_text('{"tampered": true}')

        status = oj.verify_provenance(repo_root)
        self.assertEqual(status.code, "governance_hash_mismatch")
        oj.activate_judgment(repo_root, failure=status)

        with self.assertRaises(RuntimeError):
            oj.rotate_genesis_record(repo_root, confirm=True)

        # The tamper must still be reported -- rotation must not have
        # silently accepted it as the new baseline.
        self.assertEqual(oj.verify_provenance(repo_root).code, "governance_hash_mismatch")
        self.assertTrue(oj.is_judgment_active(repo_root))

    def test_rotate_still_works_with_no_active_judgment(self):
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)

        result = oj.rotate_genesis_record(repo_root, confirm=True)

        self.assertTrue(result["rotated"])

    def test_rotate_works_again_after_a_properly_proven_clear(self):
        # (round 2 of this fix) The original version of this test "restored"
        # with an unrelated restored.txt file, never actually reverting
        # squad.config.json -- see the ClearJudgment test class above for
        # the full story on why that no longer counts as proof. Genesis was
        # established before squad.config.json existed, so restoring to
        # that baseline means the file goes back to not existing.
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)

        gov_dir = repo_root / "SYSTEM" / "CONFIG"
        gov_dir.mkdir(parents=True, exist_ok=True)
        config_file = gov_dir / "squad.config.json"
        config_file.write_text('{"legit_change": true}')

        status = oj.verify_provenance(repo_root)
        oj.activate_judgment(repo_root, failure=status)

        # Actually restore to the genesis baseline: the file didn't exist
        # when genesis was established, so remove it.
        config_file.unlink()
        proof_file = repo_root / "restoration_record.txt"
        proof_file.write_text("squad.config.json removed, restoring pre-tamper state")
        sha = hashlib.sha256(proof_file.read_bytes()).hexdigest()

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "restoration_record.txt", "sha256": sha},
        }
        jp.write_text(json.dumps(record))

        self.assertTrue(oj.clear_judgment(repo_root))

        result = oj.rotate_genesis_record(repo_root, confirm=True)
        self.assertTrue(result["rotated"])

    def test_rotate_is_unaffected_by_a_non_tamper_judgment(self):
        # A judgment that isn't tamper-classified (e.g. genesis_missing)
        # must not block rotation -- only governance_hash_mismatch /
        # restoration_required judgments do.
        repo_root = _tmp_repo()
        oj.ensure_genesis_record(repo_root, write_enabled=True)
        failure = oj.ProvenanceStatus(ok=False, code="genesis_missing", reason="no genesis record")
        oj.activate_judgment(repo_root, failure)

        result = oj.rotate_genesis_record(repo_root, confirm=True)

        self.assertTrue(result["rotated"])


if __name__ == "__main__":
    unittest.main()

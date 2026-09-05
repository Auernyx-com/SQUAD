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
        repo_root = _tmp_repo()
        failure = oj.ProvenanceStatus(ok=False, code="governance_hash_mismatch", reason="tampered")
        oj.activate_judgment(repo_root, failure)

        proof_file = repo_root / "restored.txt"
        proof_file.write_text("proof of restoration")
        sha = hashlib.sha256(proof_file.read_bytes()).hexdigest()

        jp = oj.judgment_path(repo_root)
        record = json.loads(jp.read_text())
        record["decision"] = {
            "restoration_required": True,
            "restoration_proof": {"ref": "restored.txt", "sha256": sha},
        }
        jp.write_text(json.dumps(record))

        cleared = oj.clear_judgment(repo_root)

        self.assertTrue(cleared)
        self.assertFalse(oj.is_judgment_active(repo_root))

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


if __name__ == "__main__":
    unittest.main()

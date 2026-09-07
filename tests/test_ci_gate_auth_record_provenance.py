"""
tests/test_ci_gate_auth_record_provenance.py

Independent-audit finding (2026-09-07, round 8, critical):
tools/ci_gate.py's validate_auth_record() only ever checked that an
authorization record's OWN fields were well-formed (authorizedBy is an
allowlisted login, authorizedAt is a valid non-future date, reason is
non-empty) -- it never verified the record was actually produced by the
real auto-authorize job rather than hand-written by whoever opened the
PR. Reproduced directly before this fix: a record with every field
individually valid, committed as part of an attacker's own PR (no real
review, no real approval, zero involvement from the allowlisted person),
passed every check with no exception -- a complete bypass of the entire
allowlist-authorization model this gate exists to enforce. The same gap
was independently confirmed in auernyx-agent-mk2's copy of this same
script (SQUAD's was explicitly adapted from it).

Fixed by requiring the commit that introduced the record file to match a
SHA the workflow's auto-authorize job vouches for via the
SQUAD_RECORD_COMMIT_SHA environment variable -- populated only when that
job's own live, this-run GitHub API-based is_allowed check was true (see
.github/workflows/squad-alteration-gate.yml's "Determine trusted record
commit" step). An attacker's own PR-branch commit can claim any git
author/committer identity it wants (that metadata is trivially spoofable
locally) but cannot inject a value into another job's GitHub Actions
output.

This test builds an isolated temp git repository (never the real SQUAD
checkout) and monkeypatches ci_gate's module-level GIT_ROOT/ALLOWLIST_PATH
to point at it, so it can commit both legitimate and forged records
without ever touching real repo history.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import ci_gate  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return result.stdout


class _IsolatedGateRepo:
    """A throwaway git repo with just enough structure for
    validate_auth_record()/record_introducing_commit() to run against,
    with ci_gate's module globals patched to point here instead of the
    real SQUAD checkout for the duration of the `with` block."""

    def __enter__(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="ci-gate-test-")
        self.root = Path(self.tmpdir.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.name", "Test Author")
        _git(self.root, "config", "user.email", "test@example.com")

        records_dir = self.root / "governance/alteration-program/authorization/records"
        records_dir.mkdir(parents=True)
        (records_dir / ".gitkeep").write_text("")

        allowlist_path = self.root / "governance/alteration-program/authorization/allowlist.json"
        allowlist_path.write_text(json.dumps({"authorizedLogins": ["Ghostwolf101"]}))

        (self.root / "README.md").write_text("fixture repo\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "initial")

        self._patches = [
            patch.object(ci_gate, "GIT_ROOT", self.root),
            patch.object(ci_gate, "ALLOWLIST_PATH", allowlist_path),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        self.tmpdir.cleanup()

    def commit_record(self, filename: str, record: dict, *, as_bot: bool) -> str:
        """Writes and commits a record file, as either the real bot identity
        (simulating a genuine auto-authorize commit) or an arbitrary
        identity (simulating an attacker's own commit -- still just as
        capable of claiming to BE the bot's name/email, since that's the
        whole point: this identity is not what the fix trusts)."""
        path = self.root / "governance/alteration-program/authorization/records" / filename
        path.write_text(json.dumps(record))
        _git(self.root, "add", str(path))
        author = (
            "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
            if as_bot else "Test Author <test@example.com>"
        )
        _git(self.root, "-c", f"user.name={author.split(' <')[0]}",
             "-c", f"user.email={author.split('<')[1].rstrip('>')}",
             "commit", "-q", "-m", f"chore: add {filename}", f"--author={author}")
        return _git(self.root, "log", "-1", "--format=%H", "--", str(path)).strip()

    def relpath(self, filename: str) -> str:
        return f"governance/alteration-program/authorization/records/{filename}"


VALID_RECORD = {
    "authorizedBy": "Ghostwolf101",
    "authorizedAt": "2026-09-07",
    "reason": "PR #1: a real, legitimate change",
}


class ForgedRecordIsRejectedTest(unittest.TestCase):
    def test_no_trusted_sha_env_var_is_rejected(self):
        with _IsolatedGateRepo() as repo:
            repo.commit_record("2026-09-07-pr-1.json", VALID_RECORD, as_bot=False)
            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("SQUAD_RECORD_COMMIT_SHA", None)
                with self.assertRaises(SystemExit):
                    ci_gate.validate_auth_record(repo.relpath("2026-09-07-pr-1.json"))

    def test_forged_record_even_with_bot_authored_git_identity_is_rejected(self):
        # Confirms the fix does not accidentally rely on git author/committer
        # identity as its trust signal -- an attacker who ALSO fakes the git
        # author to look like the bot must still be rejected, because no
        # SQUAD_RECORD_COMMIT_SHA vouches for it.
        with _IsolatedGateRepo() as repo:
            repo.commit_record("2026-09-07-pr-1.json", VALID_RECORD, as_bot=True)
            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("SQUAD_RECORD_COMMIT_SHA", None)
                with self.assertRaises(SystemExit):
                    ci_gate.validate_auth_record(repo.relpath("2026-09-07-pr-1.json"))

    def test_fabricated_mismatched_sha_is_rejected(self):
        with _IsolatedGateRepo() as repo:
            repo.commit_record("2026-09-07-pr-1.json", VALID_RECORD, as_bot=False)
            with patch.dict("os.environ", {"SQUAD_RECORD_COMMIT_SHA": "f" * 40}):
                with self.assertRaises(SystemExit):
                    ci_gate.validate_auth_record(repo.relpath("2026-09-07-pr-1.json"))


class LegitimateRecordStillAcceptedTest(unittest.TestCase):
    def test_matching_trusted_sha_is_accepted(self):
        with _IsolatedGateRepo() as repo:
            real_sha = repo.commit_record("2026-09-07-pr-1.json", VALID_RECORD, as_bot=True)
            with patch.dict("os.environ", {"SQUAD_RECORD_COMMIT_SHA": real_sha}):
                try:
                    ci_gate.validate_auth_record(repo.relpath("2026-09-07-pr-1.json"))
                except SystemExit as e:
                    self.fail(f"legitimate record was rejected: {e}")

    def test_still_rejects_a_record_with_a_non_allowlisted_login_even_with_matching_sha(self):
        # The commit-SHA check is additive, not a replacement for the
        # existing allowlist check.
        with _IsolatedGateRepo() as repo:
            bad_record = {**VALID_RECORD, "authorizedBy": "not-on-the-allowlist"}
            real_sha = repo.commit_record("2026-09-07-pr-1.json", bad_record, as_bot=True)
            with patch.dict("os.environ", {"SQUAD_RECORD_COMMIT_SHA": real_sha}):
                with self.assertRaises(SystemExit):
                    ci_gate.validate_auth_record(repo.relpath("2026-09-07-pr-1.json"))


if __name__ == "__main__":
    unittest.main()

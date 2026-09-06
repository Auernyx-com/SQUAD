"""
tests/test_cra_case_id_path_traversal.py

A real bug found in pathfinder_cra/run_cra_v1.py: --input, --out, and
--handshake-file all go through a "path sanitizer" (_require_json_path /
_require_text_path) specifically so a user-controlled string can't flow
into a file operation unvalidated -- the module's own header comment on
that section says so explicitly. --case-id was the one argparse argument
that fed a file-operation path (_case_dir_from_case_id -> read the input
report, mkdir + write the output report) without going through any such
gate.

Confirmed directly before fixing: _case_dir_from_case_id(repo_root,
"../../../../TMP/EVIL") resolves to a path completely outside the repo
(e.g. "/home/TMP/EVIL" for a repo at "/home/justin/SQUAD"). Nothing about
--case-id being upper-cased and .strip()'d stops that -- Path.resolve()
still walks the ".." segments.

Fix: added _require_safe_case_id(), restricting a case id to the same
kind of safe charset (letters, digits, hyphens, underscores) any real
case id was already expected to use, applied before the id is ever
joined into a path.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pathfinder_cra"))

from run_cra_v1 import _case_dir_from_case_id, _require_safe_case_id  # noqa: E402


class CaseIdSanitizerTest(unittest.TestCase):
    def test_traversal_attempts_are_rejected(self):
        cases = [
            "../../../../tmp/evil",
            "..",
            "CO/../../etc",
            "foo/bar",
            "foo\\bar",
            "",
            "   ",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(SystemExit):
                    _require_safe_case_id(raw)

    def test_ordinary_case_ids_are_accepted_and_normalized(self):
        self.assertEqual(_require_safe_case_id("CO-2026-001"), "CO-2026-001")
        self.assertEqual(_require_safe_case_id("case_42"), "CASE_42")
        self.assertEqual(_require_safe_case_id("  abc123  "), "ABC123")

    def test_sanitized_case_id_cannot_escape_the_repo(self):
        # The sanitizer raises before a traversal string ever reaches
        # _case_dir_from_case_id (see test_traversal_attempts_are_rejected).
        # This documents the other half: a value that DID pass the
        # sanitizer always resolves under CASES/ACTIVE, never outside it.
        repo_root = REPO_ROOT
        case_dir = _case_dir_from_case_id(repo_root, _require_safe_case_id("CO-2026-001")).resolve()
        self.assertTrue(str(case_dir).startswith(str((repo_root / "CASES" / "ACTIVE").resolve())))


if __name__ == "__main__":
    unittest.main()

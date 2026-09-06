"""
tests/test_qa_sweeps.py

Two real gaps found in tools/qa/ sweep scripts (neither had test coverage
before this file), both surfaced by checking DOCS/GOVERNANCE.md's claims
against the actual code.

1. python_compile_sweep.py's default --skip-regex only ever matched a
   literal double-backslash path separator (r"\\\\(\\.venv|...)\\\\") --
   confirmed directly with a probe: re.compile(that pattern).search()
   returned no match against any forward-slash (Unix-style) path at all.
   This repo's own CI runs on ubuntu-latest, so the "skip .venv/.git/
   node_modules/OUTPUTS" default did nothing there. Currently latent (no
   stray .py files happen to sit in OUTPUTS/ today), but a default that
   only works on a platform this repo doesn't test on isn't a real
   default. Fixed with a regex matching either separator style.

2. Neither sweep script excluded SYSTEM/META/QUARANTINE/, despite
   DOCS/GOVERNANCE.md's explicit "quarantine invariant": that directory is
   append-only evidence storage and "must never be treated as valid
   runtime output; validators and runners must exclude it from normal
   processing." Confirmed only one QA script (validate_pathfinder_
   contracts.py) actually implemented that exclusion; json_sweep.py and
   python_compile_sweep.py did not. A quarantined (possibly deliberately
   malformed, tamper-evidence) file would have been swept and parsed/
   compiled as if it were ordinary repo content -- and since both scripts
   are now required checks in ci-tests.yml, a real quarantine event could
   have broken CI for an unrelated reason.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QA_DIR = REPO_ROOT / "tools" / "qa"


class PythonCompileSweepSkipRegexTest(unittest.TestCase):
    """Tests the actual default --skip-regex value the script ships with."""

    def _default_regex(self) -> re.Pattern:
        src = (QA_DIR / "python_compile_sweep.py").read_text()
        match = re.search(r'default=r"([^"]+)"', src)
        self.assertIsNotNone(match, "could not find the default --skip-regex value in the script")
        return re.compile(match.group(1))

    def test_matches_unix_style_paths_for_every_skipped_dir(self):
        rx = self._default_regex()
        for name in (".venv", ".git", "node_modules", "OUTPUTS", "QUARANTINE"):
            with self.subTest(name=name):
                self.assertTrue(rx.search(f"/repo/{name}/file.py"), f"did not match Unix-style /{name}/ path")

    def test_matches_windows_style_paths_too(self):
        rx = self._default_regex()
        self.assertTrue(rx.search(r"C:\repo\.venv\lib\file.py"))
        self.assertTrue(rx.search(r"C:\repo\SYSTEM\META\QUARANTINE\evidence.py"))

    def test_does_not_match_an_ordinary_source_path(self):
        rx = self._default_regex()
        self.assertFalse(rx.search("/repo/tools/qa/real_script.py"))


class SweepQuarantineExclusionEndToEndTest(unittest.TestCase):
    """Runs the real scripts as subprocesses against a temp repo tree,
    matching exactly how ci-tests.yml invokes them."""

    def _make_quarantine_fixture(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="qa-sweep-test-"))
        quarantine = root / "SYSTEM" / "META" / "QUARANTINE"
        quarantine.mkdir(parents=True)
        (quarantine / "evidence.json").write_text("{ deliberately malformed tamper evidence, not valid json")
        (quarantine / "evidence.py").write_text("this is not valid python syntax !!! ((")
        # One real, valid file outside quarantine so the sweep has
        # something legitimate to actually scan.
        (root / "real.json").write_text('{"ok": true}')
        (root / "real.py").write_text("x = 1\n")
        return root

    def test_json_sweep_skips_quarantined_malformed_json(self):
        root = self._make_quarantine_fixture()
        result = subprocess.run(
            [sys.executable, str(QA_DIR / "json_sweep.py"), "--root", str(root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("json parse failures: 0", result.stdout)

    def test_python_compile_sweep_skips_quarantined_malformed_python(self):
        root = self._make_quarantine_fixture()
        result = subprocess.run(
            [sys.executable, str(QA_DIR / "python_compile_sweep.py"), "--root", str(root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("python-compile failures: 0", result.stdout)


if __name__ == "__main__":
    unittest.main()

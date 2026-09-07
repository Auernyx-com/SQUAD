"""
tests/test_division_cli_error_handling.py

Independent-audit finding (2026-09-07, round 7, low): 7 of 9 division CLI
tools (MODULES/*/cli/*_cli.py) crashed with a raw Python traceback on
malformed JSON or a missing --file path, because their payload-loading
code (open()/json.load()/json.loads()) wasn't wrapped in any exception
handling. Confirmed directly on 2 of the 7 during the audit. The other 2
division CLIs (RESOURCES_NONPROFITS's nonprofit_search_cli.py and
INTAKE_DO_NOT_GUESS's intake_gate_cli.py) already handled this correctly
-- this is that same fix pattern applied to the remaining 7, run here as
real subprocesses (exactly how a veteran/ops user would invoke them) so a
future regression on any one of them fails CI instead of surfacing as a
raw traceback in someone's terminal.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (module dir, cli filename) for every division CLI that had no error
# handling before this fix.
DIVISION_CLIS = [
    ("BUSINESS_OPPORTUNITY", "business_opportunity_cli.py"),
    ("LEGAL", "legal_cli.py"),
    ("MEDICAL_DISABILITY", "med_disability_cli.py"),
    ("TOXIC_EXPOSURE", "toxic_exposure_cli.py"),
    ("TRANSPORTATION", "transportation_cli.py"),
    ("VA_BENEFITS", "va_benefits_cli.py"),
    ("WOMEN_VETERANS", "women_veterans_cli.py"),
]


def _cli_path(module_dir: str, filename: str) -> Path:
    return REPO_ROOT / "MODULES" / module_dir / "cli" / filename


class DivisionCliMalformedJsonFileTest(unittest.TestCase):
    def test_malformed_json_file_exits_cleanly_no_traceback(self):
        bad_json = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        bad_json.write("{ this is not valid json")
        bad_json.close()

        for module_dir, filename in DIVISION_CLIS:
            with self.subTest(cli=filename):
                result = subprocess.run(
                    [sys.executable, str(_cli_path(module_dir, filename)), "--file", bad_json.name],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0, "should not exit 0 on malformed input")
                self.assertNotIn("Traceback (most recent call last)", result.stderr)


class DivisionCliMissingFileTest(unittest.TestCase):
    def test_missing_file_exits_cleanly_no_traceback(self):
        missing_path = str(Path(tempfile.mkdtemp()) / "does_not_exist.json")

        for module_dir, filename in DIVISION_CLIS:
            with self.subTest(cli=filename):
                result = subprocess.run(
                    [sys.executable, str(_cli_path(module_dir, filename)), "--file", missing_path],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0, "should not exit 0 when the file doesn't exist")
                self.assertNotIn("Traceback (most recent call last)", result.stderr)


class DivisionCliMalformedInlinePayloadTest(unittest.TestCase):
    def test_malformed_inline_payload_exits_cleanly_no_traceback(self):
        for module_dir, filename in DIVISION_CLIS:
            with self.subTest(cli=filename):
                result = subprocess.run(
                    [sys.executable, str(_cli_path(module_dir, filename)), "not valid json"],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0, "should not exit 0 on a non-JSON positional payload")
                self.assertNotIn("Traceback (most recent call last)", result.stderr)


if __name__ == "__main__":
    unittest.main()

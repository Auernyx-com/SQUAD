"""
tests/test_core_runner_schema_failure_graceful.py

Independent-audit finding (2026-09-08, round 6, low):
pf_core_runner_v1.py's run() called _validate_contract_schema(payload)
and the contract_id/schema_version mismatch check BEFORE the try/except
block that gracefully degrades every OTHER processing failure to the
module's own _closed_output() envelope ("Fail closed: any unexpected
processing error emits a safe VERIFY_REQUIRED output"). A schema-invalid
or unauthorized contract raised ValueError uncaught instead -- no output
file was written at all, not even the fail-closed one this module's
whole design is built around.

Confirmed directly against the unmodified code before this fix, using
the real example_input.contract.v1.json as a base: a schema-valid
payload with `input.case` set to a bare string (rejected by the schema's
own type constraint) crashed run() uncaught; a payload missing the
required top-level contract_id field also crashed uncaught. In both
cases no output file was produced.

Also confirmed via direct execution that the strict Draft202012 schema
already blocks structurally malformed input.case/input.stage shapes
before they could ever reach build_pathfinder_plan()/
build_case_review_plan() through this, the sole real entry point
(confirmed via repo-wide grep -- run() is the only caller reachable from
the PowerShell admin CLI) -- so this fix targets the actual reachable
gap (the authorization step bypassing the fail-closed envelope), not a
speculative defense of already-unreachable lower-level functions.

Fixed by computing input_env/stage defensively before validation and
widening the existing try/except to also cover the authorization step,
so any failure -- authorization or processing -- now produces the same
graceful _closed_output envelope.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))

from pf_core_runner_v1 import run  # noqa: E402

_EXAMPLE_PATH = REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER" / "example_input.contract.v1.json"


def _write_temp(payload) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(payload, f)
    f.close()
    return Path(f.name)


class SchemaFailureProducesGracefulOutputTest(unittest.TestCase):
    def setUp(self):
        self.base = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8-sig"))

    def test_malformed_case_type_produces_closed_output_not_a_crash(self):
        payload = json.loads(json.dumps(self.base))
        payload["input"]["case"] = "not an object"
        path = _write_temp(payload)

        out = run(path)  # must not raise

        self.assertEqual(out["output"]["confidence"], "VERIFY_REQUIRED")
        self.assertTrue(any(
            w["warning_id"] == "BB4.SYSTEM.FAIL_CLOSED" for w in out["output"]["warnings"]
        ))

    def test_missing_contract_id_produces_closed_output_not_a_crash(self):
        payload = json.loads(json.dumps(self.base))
        del payload["contract_id"]
        path = _write_temp(payload)

        out = run(path)  # must not raise

        self.assertEqual(out["output"]["confidence"], "VERIFY_REQUIRED")

    def test_output_file_is_actually_written_on_authorization_failure(self):
        payload = json.loads(json.dumps(self.base))
        payload["input"]["case"] = "not an object"
        in_path = _write_temp(payload)
        out_path = Path(tempfile.NamedTemporaryFile(suffix=".json", delete=False).name)

        run(in_path, output_path=out_path)

        self.assertTrue(out_path.exists())
        written = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(written["output"]["confidence"], "VERIFY_REQUIRED")

    def test_valid_payload_still_produces_a_real_plan_no_regression(self):
        path = _write_temp(self.base)
        out = run(path)
        self.assertIn("pathfinder_plan", out["output"])
        # A genuinely valid, well-formed case should not immediately be
        # fail-closed.
        self.assertNotEqual(
            out["output"].get("warnings", [{}])[0].get("warning_id"),
            "BB4.SYSTEM.FAIL_CLOSED",
        ) if out["output"].get("warnings") else None


if __name__ == "__main__":
    unittest.main()

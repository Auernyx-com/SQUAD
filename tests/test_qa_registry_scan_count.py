"""
tests/test_qa_registry_scan_count.py

Independent-audit finding (2026-09-07, round 7, low): tools/qa/
validate_nonprofit_registry.py stops *scanning files* as soon as it hits
--max-failures findings, but its final "nonprofit registry files scanned: N"
line always printed len(registry_files) -- the full candidate count --
regardless of how many files the loop actually got through before breaking
early. At the default cap (50) this could silently undercount the real
scanned total (and therefore the real backlog of unscanned files) by a wide
margin while claiming to report the full file count.

Confirmed directly: with --max-failures=1 and 3 shard files, the tool used
to print "files scanned: 3" after having examined only 1.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QA_SCRIPT = REPO_ROOT / "tools" / "qa" / "validate_nonprofit_registry.py"

_SCOPE = {
    "registry_rules": {"allowed_output_fields": ["provider_id", "name", "services"]},
    "service_taxonomy": {"allowed_service_tags": ["claims_assistance"]},
    "prohibited": {
        "ranking_or_recommendation": {"blocked_fields": [], "blocked_phrases": []},
        "eligibility_or_outcome": {"blocked_phrases": []},
    },
}


def _make_fixture(num_flagged_shards: int, num_clean_shards: int = 0) -> Path:
    root = Path(tempfile.mkdtemp(prefix="qa-registry-scan-count-"))
    module_root = root / "MODULES" / "RESOURCES_NONPROFITS"
    (module_root / "GOVERNANCE").mkdir(parents=True)
    (module_root / "GOVERNANCE" / "auernyx.nonprofit.scope.json").write_text(json.dumps(_SCOPE))

    data_root = module_root / "DATA"
    data_root.mkdir(parents=True)
    # Each flagged shard trips exactly one finding (an unexpected top-level
    # field not in allowed_output_fields) -- not a JSON-parse failure, which
    # takes a separate `continue` path that never reaches the max-failures
    # check at all (a second, already-known gap -- see KNOWN_GAPS.md).
    for i in range(num_flagged_shards):
        provider = {"provider_id": f"p{i}", "name": f"Org {i}", "services": [], "bogus_field": "not allowed"}
        (data_root / f"flagged_{i}.json").write_text(json.dumps({"providers": [provider]}))
    for i in range(num_clean_shards):
        (data_root / f"clean_{i}.json").write_text(json.dumps({"providers": []}))

    return root


class ScanCountReflectsActualWorkDoneTest(unittest.TestCase):
    def test_stops_early_reports_partial_count_not_full_candidate_count(self):
        # 3 flagged shards, cap of 1 finding -- the loop must break after
        # the first file, so the reported "scanned" count must be 1, not 3.
        root = _make_fixture(num_flagged_shards=3)
        result = subprocess.run(
            [sys.executable, str(QA_SCRIPT), "--root", str(root), "--max-failures", "1"],
            capture_output=True, text=True,
        )
        self.assertIn("nonprofit registry files scanned: 1 of 3", result.stdout, result.stdout)
        self.assertIn("stopped early", result.stdout)

    def test_full_scan_reports_no_early_stop(self):
        # 2 clean shards, cap well above any possible findings -- the loop
        # runs to completion and must not claim it stopped early.
        root = _make_fixture(num_flagged_shards=0, num_clean_shards=2)
        result = subprocess.run(
            [sys.executable, str(QA_SCRIPT), "--root", str(root), "--max-failures", "50"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("nonprofit registry files scanned: 2 of 2", result.stdout, result.stdout)
        self.assertNotIn("stopped early", result.stdout)


if __name__ == "__main__":
    unittest.main()

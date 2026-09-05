"""
tests/_test_receipts_isolation.py

Shared setup: point the coordinator's receipt writer at a throwaway temp
directory for the duration of the test process, instead of the shared
artifacts/receipts/coordinator/ path (not gitignored; older receipts are
already tracked in this repo, committed intentionally in a prior session).
Import this module first (before pf_coordinator_v1) in any test module that
runs the real coordinator, so test runs never leave files behind for a
careless `git add -A` to pick up.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

_TMP_RECEIPTS_DIR = tempfile.mkdtemp(prefix="squad-bat-test-receipts-")
os.environ["SQUAD_BAT_RECEIPTS_DIR"] = _TMP_RECEIPTS_DIR
atexit.register(shutil.rmtree, _TMP_RECEIPTS_DIR, True)

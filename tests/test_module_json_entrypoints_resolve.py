"""
tests/test_module_json_entrypoints_resolve.py

Independent-audit findings (2026-09-08, round 6, low):

1. MODULES/MEDICAL_DISABILITY/module.json's "logic" entrypoint pointed at
   "../../AGENTS/LOGIC/MedDisability_v0.1.py" (a dot) -- the real file on
   disk is "MedDisability_v0_1.py" (an underscore). Confirmed via
   repo-wide grep that nothing currently reads module.json's "logic"
   field programmatically (tools/qa/validate_module_registries.py only
   validates module_registry.v1.json's separate "entrypoint" field), so
   this was dead/inert metadata rather than a live crash -- but exactly
   the kind of stale reference that would break anything (tooling or a
   human) that trusts this file as documentation. Fixed the typo.

2. MODULES/HOUSING/ was the only one of the 8 divisions with no
   module.json at all (every sibling has one). No runtime effect
   confirmed (pf_coordinator_v1.py resolves entrypoints from
   config/divisions.json directly, never from module.json), but it's a
   real metadata/tooling-consistency gap. Added one, matching the
   established shape of the other 7.

This test locks in the fix and adds the missing validation the audit
itself noted doesn't exist anywhere: every module.json's declared
python_api/logic paths must actually resolve to a real file on disk.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = REPO_ROOT / "MODULES"


class ModuleJsonEntrypointsResolveTest(unittest.TestCase):
    def test_every_module_has_a_module_json(self):
        division_dirs = [
            "HOUSING", "LEGAL", "TRANSPORTATION", "TOXIC_EXPOSURE",
            "WOMEN_VETERANS", "MEDICAL_DISABILITY", "BUSINESS_OPPORTUNITY",
            "VA_BENEFITS",
        ]
        missing = [d for d in division_dirs if not (MODULES_DIR / d / "module.json").exists()]
        self.assertEqual(missing, [])

    def test_every_module_json_python_api_and_logic_path_resolves(self):
        unresolved = []
        for module_json_path in sorted(MODULES_DIR.glob("*/module.json")):
            data = json.loads(module_json_path.read_text(encoding="utf-8"))
            entrypoints = data.get("entrypoints", {})
            for key in ("python_api", "logic"):
                rel = entrypoints.get(key)
                if not rel:
                    continue
                resolved = (module_json_path.parent / rel).resolve()
                if not resolved.exists():
                    unresolved.append(f"{module_json_path}: {key} -> {rel} (resolved: {resolved})")
        self.assertEqual(unresolved, [])

    def test_medical_disability_logic_path_uses_the_real_underscore_filename(self):
        data = json.loads((MODULES_DIR / "MEDICAL_DISABILITY" / "module.json").read_text())
        self.assertEqual(data["entrypoints"]["logic"], "../../AGENTS/LOGIC/MedDisability_v0_1.py")


if __name__ == "__main__":
    unittest.main()

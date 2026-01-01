import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Change:
    status: str
    path: str


def _run_git(args: list[str], repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.stdout


def _parse_status_porcelain_v1_z(output: str) -> list[Change]:
    # Each record is NUL-separated, line format like:
    #  XY path\0 or "XY old\0new\0" for renames.
    records = output.split("\0")
    changes: list[Change] = []

    i = 0
    while i < len(records):
        rec = records[i]
        i += 1
        if not rec:
            continue
        status = rec[:2]
        rest = rec[3:] if len(rec) >= 4 else ""

        # Rename/copy: "R  old" and then next record is "new"
        if status and status[0] in {"R", "C"}:
            old_path = rest
            if i < len(records) and records[i]:
                new_path = records[i]
                i += 1
                changes.append(Change(status=status, path=new_path))
                # keep old path too for classification context
                changes.append(Change(status=status, path=old_path))
            else:
                changes.append(Change(status=status, path=old_path))
            continue

        changes.append(Change(status=status, path=rest))

    # Deduplicate identical paths
    seen: set[str] = set()
    unique: list[Change] = []
    for c in changes:
        if c.path and c.path not in seen:
            seen.add(c.path)
            unique.append(c)
    return unique


def _category_for_path(path: str) -> str:
    p = path.replace("\\", "/")

    if p.startswith("OUTPUTS/"):
        return "outputs"

    if p.startswith("CASES/ACTIVE/"):
        if "/ARTIFACTS/" in p:
            return "case_artifact"
        if p.endswith(".case.json") or p.endswith(".notes.md"):
            return "case_state"
        return "case_active"

    if p.startswith("AGENTS/SCHEMAS/"):
        return "schema"

    if p.startswith("AGENTS/CORE/"):
        return "agent_core"

    if p.startswith("AGENTS/"):
        return "agent"

    if p.startswith("SYSTEM/CONFIG/"):
        return "system_config"

    if p.startswith("SYSTEM/CLERK/") or p == "Invoke-SquadAdminClerk.ps1":
        return "clerk"

    if p.startswith("tools/qa/"):
        return "qa_tooling"

    if p.startswith("tools/"):
        return "tooling"

    if p.startswith("DOCS/"):
        return "docs"

    if p.startswith("DATA/"):
        return "data"

    if p.startswith(".vscode/"):
        return "editor_config"

    return "other"


def _risk_group(category: str) -> str:
    # Coarse boundary buckets used to detect "cross-category" edits.
    if category in {"schema", "system_config", "clerk", "editor_config"}:
        return "governed"
    if category.startswith("case_") or category == "case_active":
        return "case"
    if category == "outputs":
        return "outputs"
    if category in {"qa_tooling", "tooling"}:
        return "tooling"
    if category in {"agent_core", "agent"}:
        return "agents"
    if category in {"docs", "data", "other"}:
        return category
    return "other"


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]

    strict = "--strict" in argv

    out = _run_git(["status", "--porcelain=v1", "-z"], repo_root)
    changes = _parse_status_porcelain_v1_z(out)

    classified = []
    groups: set[str] = set()
    categories: set[str] = set()

    for c in changes:
        category = _category_for_path(c.path)
        group = _risk_group(category)
        categories.add(category)
        groups.add(group)
        classified.append(
            {
                "status": c.status,
                "path": c.path,
                "category": category,
                "group": group,
            }
        )

    warnings: list[str] = []
    errors: list[str] = []

    if "outputs" in groups:
        errors.append("Detected changes under OUTPUTS/. Treat OUTPUTS as write-protected.")

    # Boundary-crossing warning: mixing governed artifacts with case artifacts
    if "governed" in groups and "case" in groups:
        warnings.append("Boundary crossing: changes include both governed artifacts and case artifacts.")

    # Broad boundary crossing warning: many buckets in one change-set
    if len(groups) >= 3:
        warnings.append(f"Cross-category change-set: groups touched={sorted(groups)}")

    result = {
        "repo": "SQUAD",
        "changes_found": len(classified),
        "groups": sorted(groups),
        "categories": sorted(categories),
        "warnings": warnings,
        "errors": errors,
        "changes": sorted(classified, key=lambda x: x["path"]),
    }

    print(json.dumps(result, indent=2, sort_keys=True))

    if errors:
        return 3
    if strict and warnings:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

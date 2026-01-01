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


def _git_numstat(repo_root: Path) -> dict[str, tuple[int, int]]:
    """Return git diff numstat for tracked changes.

    Output is intentionally limited to line counts (no diff hunks) to reduce
    accidental exposure of sensitive content.
    """

    out = _run_git(["diff", "--numstat"], repo_root)
    stats: dict[str, tuple[int, int]] = {}

    for line in out.splitlines():
        # Format: added<TAB>deleted<TAB>path
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        a_raw, d_raw, path = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not path:
            continue

        # Binary files show '-' in numstat; treat as 0/0.
        try:
            added = int(a_raw) if a_raw != "-" else 0
            deleted = int(d_raw) if d_raw != "-" else 0
        except Exception:  # noqa: BLE001
            continue

        stats[path] = (added, deleted)

    return stats


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


def _plain_summary(result: dict) -> str:
    lines: list[str] = []
    changes_found = int(result.get("changes_found", 0) or 0)
    groups = result.get("groups") or []
    categories = result.get("categories") or []
    warnings = result.get("warnings") or []
    errors = result.get("errors") or []

    lines.append(f"Changes found: {changes_found}")
    if groups:
        lines.append(f"Groups touched: {', '.join([str(x) for x in groups])}")
    if categories:
        lines.append(f"Categories touched: {', '.join([str(x) for x in categories])}")

    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"- {w}")

    if errors:
        lines.append("Errors:")
        for e in errors:
            lines.append(f"- {e}")

    changes = result.get("changes") or []
    if changes:
        lines.append("Files:")
        for c in changes:
            status = str(c.get("status") or "").strip() or "??"
            path = str(c.get("path") or "").strip()
            category = str(c.get("category") or "")
            group = str(c.get("group") or "")
            lines.append(f"- {status} {path} ({category}/{group})")

    intent = result.get("intent")
    if isinstance(intent, dict):
        numstat = intent.get("numstat")
        if isinstance(numstat, list) and numstat:
            lines.append("Diff intent (line counts only):")
            for row in numstat:
                if not isinstance(row, dict):
                    continue
                p = str(row.get("path") or "").strip()
                a = row.get("added")
                d = row.get("deleted")
                if p:
                    lines.append(f"- +{a} -{d} {p}")

    # Privacy / HIPAA-aware reminder (no PHI/PII in outputs)
    lines.append("Privacy note: avoid putting PHI/PII (medical details, SSNs, full DOBs) in tracked text/code. Store medical/VA documents as case artifacts with redactions.")

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]

    strict = "--strict" in argv
    plain = "--plain" in argv
    intent = "--intent" in argv
    require_governed_confirm = "--require-governed-confirm" in argv
    confirm_governed = "--confirm-governed" in argv

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

    if intent:
        stats = _git_numstat(repo_root=repo_root)
        rows: list[dict[str, object]] = []
        for p, (a, d) in sorted(stats.items()):
            rows.append({"path": p, "added": a, "deleted": d})
        result["intent"] = {"numstat": rows}

    # Phase 5 (opt-in): require explicit confirmation for governed changes.
    if require_governed_confirm and ("governed" in groups) and (not confirm_governed):
        errors.append(
            "Governed changes detected without explicit confirmation. "
            "Re-run with --confirm-governed if this is intentional."
        )
        result["errors"] = errors

    if plain:
        sys.stdout.write(_plain_summary(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))

    if errors:
        return 3
    if strict and warnings:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

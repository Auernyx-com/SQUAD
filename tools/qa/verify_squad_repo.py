import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sentinel:
    path: str
    kind: str  # "file" | "dir"
    required: bool = True


def _exists(root: Path, sentinel: Sentinel) -> bool:
    candidate = root / sentinel.path
    if sentinel.kind == "file":
        return candidate.is_file()
    if sentinel.kind == "dir":
        return candidate.is_dir()
    raise ValueError(f"unknown sentinel kind: {sentinel.kind}")


def _repo_root_from_env_or_cwd() -> Path:
    # Prefer explicit root if provided.
    root = os.environ.get("SQUAD_REPO_ROOT")
    if root:
        return Path(root).resolve()
    return Path.cwd().resolve()


def main() -> int:
    root = _repo_root_from_env_or_cwd()

    sentinels = [
        Sentinel("Invoke-SquadAdminClerk.ps1", "file"),
        Sentinel("SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1", "file"),
        Sentinel("PIPELINE_README.md", "file"),
        Sentinel("AGENTS/SCHEMAS/BattleBuddy_Contract_v1.schema.json", "file"),
        Sentinel("tools/qa/Invoke-RepoCheck.ps1", "file"),
        Sentinel("SYSTEM/CONFIG/squad.config.json", "file"),
        Sentinel("CASES/ACTIVE", "dir"),
        Sentinel("DOCS/GOVERNANCE.md", "file"),
    ]

    missing_required: list[str] = []
    present: list[str] = []

    for s in sentinels:
        if _exists(root, s):
            present.append(s.path)
        elif s.required:
            missing_required.append(s.path)

    result = {
        "repo": "SQUAD" if not missing_required else "UNRECOGNIZED",
        "root": str(root),
        "present": present,
        "missing_required": missing_required,
    }

    # Deterministic, machine-friendly output.
    print(json.dumps(result, indent=2, sort_keys=True))

    if missing_required:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

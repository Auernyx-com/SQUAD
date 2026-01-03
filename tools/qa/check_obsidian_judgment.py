import argparse
import json
import os
from pathlib import Path


def repo_root_from_env_or_cwd() -> Path:
    root = os.environ.get("SQUAD_REPO_ROOT") or os.environ.get("SQUAD_ROOT")
    if root:
        return Path(root).resolve()
    return Path.cwd().resolve()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check SQUAD Obsidian Judgment / provenance state.")
    p.add_argument("--root", help="Repo root (defaults to env or cwd)")
    p.add_argument(
        "--require-genesis",
        action="store_true",
        help="Fail if genesis is missing (strict mode).",
    )
    return p.parse_args()


def main() -> int:
    # Optional by design:
    # - If genesis is missing => do not fail the repo check (not initialized).
    # - If judgment is active => fail.
    # - If genesis exists but provenance fails => fail.

    args = _parse_args()
    root = Path(args.root).resolve() if args.root else repo_root_from_env_or_cwd()

    # Import module core directly via file path, without packaging.
    src = root / "MODULES" / "OBSIDIAN_JUDGMENT" / "src"
    if not src.is_dir():
        print(json.dumps({"ok": True, "skipped": True, "reason": "module_missing"}, indent=2))
        return 0

    import sys

    sys.path.insert(0, str(src))
    from obsidian_judgment import (  # type: ignore
        compute_governance_hash,
        genesis_path,
        is_judgment_active,
        read_genesis_record,
        read_judgment,
        verify_provenance,
    )

    gpath = genesis_path(root)

    if is_judgment_active(root):
        j = read_judgment(root)
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": "judgment_active",
                    "reason": "Judgment is active",
                    "details": {"judgment": j},
                    "next_steps": "Clear judgment (authorized): python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py clear --confirm YES",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 2

    if not gpath.is_file():
        if args.require_genesis:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": "genesis_missing",
                        "reason": "Genesis record missing",
                        "details": {"expected_path": str(gpath)},
                        "next_steps": "Initialize genesis once: python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py genesis --write",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 2
        print(json.dumps({"ok": True, "skipped": True, "reason": "genesis_missing"}, indent=2))
        return 0

    status = verify_provenance(root)
    genesis = read_genesis_record(root) or {}
    declared = str(genesis.get("initial_governance_hash") or "")
    observed = compute_governance_hash(root)

    next_steps = ""
    if not status.ok:
        if status.code == "governance_hash_mismatch":
            next_steps = "Revert governance-critical files to the last known-good baseline, then re-run repo QA and Clerk."
        else:
            next_steps = "Fix provenance failure, then re-run repo QA and Clerk."

    out = {
        "ok": status.ok,
        "code": status.code,
        "reason": status.reason,
        "details": status.details,
        "expected_baseline_hash": declared,
        "detected_hash": observed,
        "next_steps": next_steps if next_steps else None,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    return 0 if status.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

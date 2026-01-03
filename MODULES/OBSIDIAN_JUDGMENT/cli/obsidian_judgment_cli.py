from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path


def _add_src_to_path() -> None:
    here = Path(__file__).resolve()
    module_root = here.parents[1]
    src_dir = module_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description="OBSIDIAN_JUDGMENT (v1) — SQUAD provenance + judgment state.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Print status report (JSON)")
    sub.add_parser("verify", help="Verify provenance (JSON)")

    g = sub.add_parser("genesis", help="Create genesis record (explicit)")
    g.add_argument("--write", action="store_true", help="Actually create genesis (required).")

    r = sub.add_parser("rotate-genesis", help="Rewrite genesis record to current governance hash (explicit)")
    r.add_argument("--confirm", choices=["YES"], required=True, help="Type YES to rotate genesis.")

    a = sub.add_parser("activate", help="Activate judgment based on current provenance failure.")
    a.add_argument("--confirm", choices=["YES"], required=True, help="Type YES to activate judgment.")

    c = sub.add_parser("clear", help="Clear judgment state.")
    c.add_argument("--confirm", choices=["YES"], required=True, help="Type YES to clear judgment.")

    args = parser.parse_args()

    _add_src_to_path()
    mod = importlib.import_module("obsidian_judgment")

    activate_judgment = getattr(mod, "activate_judgment")
    clear_judgment = getattr(mod, "clear_judgment")
    ensure_genesis_record = getattr(mod, "ensure_genesis_record")
    repo_root_from_env_or_cwd = getattr(mod, "repo_root_from_env_or_cwd")
    status_report = getattr(mod, "status_report")
    verify_provenance = getattr(mod, "verify_provenance")
    rotate_genesis_record = getattr(mod, "rotate_genesis_record")

    repo_root = repo_root_from_env_or_cwd()

    if args.cmd == "status":
        sys.stdout.write(json.dumps(status_report(repo_root), indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.cmd == "verify":
        prov = verify_provenance(repo_root)
        out = {
            "ok": prov.ok,
            "code": prov.code,
            "reason": prov.reason,
            "details": prov.details,
        }
        sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        return 0 if prov.ok else 2

    if args.cmd == "genesis":
        res = ensure_genesis_record(repo_root, write_enabled=bool(args.write))
        sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.cmd == "rotate-genesis":
        res = rotate_genesis_record(repo_root, confirm=True)
        sys.stdout.write(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.cmd == "activate":
        prov = verify_provenance(repo_root)
        if prov.ok:
            sys.stdout.write(json.dumps({"activated": False, "reason": "provenance_ok"}, indent=2) + "\n")
            return 0
        record = activate_judgment(repo_root, failure=prov)
        sys.stdout.write(json.dumps({"activated": True, "judgment": record}, indent=2, ensure_ascii=False) + "\n")
        return 0

    if args.cmd == "clear":
        ok = clear_judgment(repo_root)
        sys.stdout.write(json.dumps({"cleared": bool(ok)}, indent=2) + "\n")
        return 0 if ok else 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

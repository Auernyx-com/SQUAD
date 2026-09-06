"""Repo-wide Python syntax compile sweep.

Uses compileall to byte-compile all .py files under a root directory.

Exit codes:
  0 - compile succeeded
  1 - one or more files failed to compile
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Compile all Python files under a root folder.")
    parser.add_argument(
        "--root",
        default=str(Path.cwd()),
        help="Root folder to scan (default: current working directory)",
    )
    parser.add_argument(
        "--skip-regex",
        # Matches either path separator ([\\/]), not just Windows' backslash --
        # the original default (\\\\(...)\\\\) only ever matched a literal
        # double-backslash sequence, so on any Unix-style path (this repo's
        # own CI runs on ubuntu-latest) it silently matched nothing at all.
        # Confirmed directly: re.compile(r"\\\\(\\.venv|...)\\\\").search()
        # returned no match against any /.venv/ or /.git/ style path.
        # Currently latent (no stray .py files sit in OUTPUTS/ today), but a
        # default that only works on the platform it happens not to be
        # tested on isn't a real default. Also adds SYSTEM/META/QUARANTINE,
        # per DOCS/GOVERNANCE.md's quarantine invariant ("validators and
        # runners must exclude it from normal processing") -- this script
        # didn't, so quarantined evidence could have broken a compile sweep
        # meant to check real source, not preserved tamper evidence.
        default=r"[\\/](\.venv|\.git|node_modules|OUTPUTS|QUARANTINE)[\\/]",
        help="Regex for paths to skip (default skips .venv/.git/node_modules/OUTPUTS/QUARANTINE, either path separator style)",
    )

    args = parser.parse_args(argv)

    import compileall  # local import to keep startup minimal

    root = Path(args.root)
    rx = re.compile(args.skip_regex)
    ok = compileall.compile_dir(str(root), quiet=1, rx=rx)

    if ok:
        print("python-compile failures: 0")
        return 0

    print("python-compile failures: 1+")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

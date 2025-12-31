"""Repo JSON parse sweep.

Walks a directory tree and attempts to parse every *.json file using Python's
standard library json module.

Intended for repo-wide sanity checks (more strict than some parsers).

Exit codes:
  0 - all JSON files parsed successfully
  1 - one or more JSON files failed to parse
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class Failure:
    path: str
    error: str


DEFAULT_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
}


def _iter_json_files(root: Path, *, skip_dirs: set[str]) -> Iterable[Path]:
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        # prune directories in-place
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        for name in filenames:
            if name.lower().endswith(".json"):
                yield Path(dirpath) / name


def _load_json(path: Path) -> None:
    # Python's json parser rejects a leading UTF-8 BOM; decode with utf-8-sig to
    # transparently strip BOM while still strictly parsing JSON.
    with path.open("r", encoding="utf-8-sig") as f:
        json.load(f)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Parse all .json files under a root folder.")
    parser.add_argument(
        "--root",
        default=str(Path.cwd()),
        help="Root folder to scan (default: current working directory)",
    )
    parser.add_argument(
        "--skip-dir",
        action="append",
        default=[],
        help="Directory name to skip (can be repeated)",
    )
    parser.add_argument(
        "--include-outputs",
        action="store_true",
        help="Include OUTPUTS/ in scanning (default: skipped)",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=50,
        help="Max failures to print (default: 50)",
    )

    args = parser.parse_args(list(argv))

    root = Path(args.root)
    skip_dirs = set(DEFAULT_SKIP_DIRS)
    skip_dirs.update(args.skip_dir)

    if not args.include_outputs:
        skip_dirs.add("OUTPUTS")

    failures: List[Failure] = []
    total = 0

    for path in _iter_json_files(root, skip_dirs=skip_dirs):
        total += 1
        try:
            _load_json(path)
        except Exception as e:  # noqa: BLE001 - intended: capture any parse/IO error
            failures.append(Failure(path=str(path), error=str(e)))

    print(f"json files scanned: {total}")
    print(f"json parse failures: {len(failures)}")

    for f in failures[: max(args.max_failures, 0)]:
        print(f"FAIL {f.path}")
        print(f"  {f.error}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

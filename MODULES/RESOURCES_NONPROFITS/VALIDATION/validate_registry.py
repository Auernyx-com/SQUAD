from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _add_src_to_syspath(module_root: Path) -> None:
    src = (module_root / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate RESOURCES_NONPROFITS shard files using the shared core enforcement."
    )
    parser.add_argument("--module-root", help="Path to module root (defaults to auto-detect)")

    args = parser.parse_args(list(argv) if argv is not None else None)

    module_root = Path(args.module_root).resolve() if args.module_root else Path(__file__).resolve().parents[1]
    data_root = module_root / "DATA"
    if not data_root.is_dir():
        print("nonprofit module shard files scanned: 0")
        print("nonprofit module validation: OK (no DATA directory present)")
        return 0

    shard_files = sorted(data_root.rglob("*.json"))
    if not shard_files:
        print("nonprofit module shard files scanned: 0")
        print("nonprofit module validation: OK (no shard files present)")
        return 0

    _add_src_to_syspath(module_root)
    from nonprofit_search import load_registry  # noqa: E402

    # load_registry enforces:
    # - blocked fields (reject)
    # - service taxonomy (reject)
    # - strips to allowed_output_fields
    load_registry(paths=[str(p) for p in shard_files])

    print(f"nonprofit module shard files scanned: {len(shard_files)}")
    print("nonprofit module validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

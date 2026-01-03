from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def _add_src_to_syspath() -> None:
    # Allow running as a script without installation.
    # MODULES/RESOURCES_NONPROFITS/cli/nonprofit_search_cli.py -> ../src
    here = Path(__file__).resolve()
    src = (here.parents[1] / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_add_src_to_syspath()

from nonprofit_search import load_registry, search  # noqa: E402  # pyright: ignore[reportMissingImports]


def _parse_fields(fields: Optional[str]) -> Optional[List[str]]:
    if not fields:
        return None
    parts = [p.strip() for p in fields.split(",")]
    return [p for p in parts if p]


def main() -> int:
    parser = argparse.ArgumentParser(description="Search nonprofit registry shards (filter-only, no ranking).")
    parser.add_argument(
        "--data",
        action="append",
        required=True,
        help="Path to a shard JSON file. Repeatable.",
    )

    parser.add_argument("--county", help="County exact match (case-insensitive)")
    parser.add_argument("--city", help="City exact match (case-insensitive)")
    parser.add_argument("--service", help="Service tag (must be in controlled vocabulary)")
    parser.add_argument("--org-type", dest="org_type", help="Org type exact match (case-insensitive)")
    parser.add_argument("--va-visibility", dest="va_visibility", help="VA visibility exact match (case-insensitive)")
    parser.add_argument("--text", help="Substring match across name/notes/services/cities/counties")
    parser.add_argument("--limit", type=int, default=25)

    parser.add_argument(
        "--fields",
        help="Comma-separated subset of fields to emit (e.g., name,phones,emails,urls,address,services)",
    )

    args = parser.parse_args()

    try:
        records = load_registry(paths=list(args.data))
        results = search(
            records,
            county=args.county,
            city=args.city,
            service=args.service,
            org_type=args.org_type,
            va_visibility=args.va_visibility,
            text=args.text,
            limit=args.limit,
        )

        fields = _parse_fields(args.fields)
        if fields:
            trimmed = []
            for r in results:
                trimmed.append({k: r.get(k) for k in fields if k in r})
            results = trimmed

        sys.stdout.write(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        return 0

    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

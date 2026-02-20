"""CLI runner for Listing_Legitimacy_RedFlags_v1.

Stays modular: reads an input JSON file, runs the deterministic evaluator, prints JSON.

Usage:
    python .\run_listing_legitimacy_redflags_v1.py --input ./example_input.json
    python .\run_listing_legitimacy_redflags_v1.py --input ./in.json --output ./out.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from Listing_Legitimacy_RedFlags_v1 import evaluate_listing_legitimacy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Listing Legitimacy Red Flags (v1) on a JSON payload.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSON matching schema_Listing_Legitimacy_RedFlags_v1.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write output JSON (defaults to stdout)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if input_path.suffix.lower() != ".json":
        raise SystemExit(f"Expected a .json input file, got: {args.input!r}")
    payload: Dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))

    result = evaluate_listing_legitimacy(payload)
    out_obj = result.__dict__

    if args.pretty:
        out_text = json.dumps(out_obj, indent=2)
    else:
        out_text = json.dumps(out_obj)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        if out_path.suffix.lower() != ".json":
            raise SystemExit(f"Expected a .json output file, got: {args.output!r}")
        out_path.write_text(out_text + "\n", encoding="utf-8")
    else:
        print(out_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

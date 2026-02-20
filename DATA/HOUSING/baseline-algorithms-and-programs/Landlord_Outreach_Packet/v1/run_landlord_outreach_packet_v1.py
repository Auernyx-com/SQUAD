"""CLI runner for Landlord_Outreach_Packet_v1.

Reads an input JSON file, generates outreach packet templates, prints JSON.

Usage:
  python .\run_landlord_outreach_packet_v1.py --input ./example_input.json --pretty
  python .\run_landlord_outreach_packet_v1.py --input ./in.json --output ./out.json --pretty
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from Landlord_Outreach_Packet_v1 import build_landlord_outreach_packet


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate landlord outreach packet templates (v1).")
    parser.add_argument("--input", required=True, help="Path to input JSON")
    parser.add_argument("--output", default=None, help="Optional path to write output JSON")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if input_path.suffix.lower() != ".json":
        raise SystemExit(f"Expected a .json input file, got: {args.input!r}")
    payload: Dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    packet = build_landlord_outreach_packet(payload)
    out_obj = packet.__dict__

    out_text = json.dumps(out_obj, indent=2) if args.pretty else json.dumps(out_obj)

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

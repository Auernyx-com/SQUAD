from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _add_src_to_syspath() -> None:
    here = Path(__file__).resolve()
    src = (here.parents[1] / "src").resolve()
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_add_src_to_syspath()

from intake_gate import gate_intake  # noqa: E402


def _load_payload(path: str | None) -> Dict[str, Any]:
    if path:
        p = Path(path).expanduser().resolve()
        return json.loads(p.read_text(encoding="utf-8-sig"))

    # stdin
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Do Not Guess intake gate (JSON in, JSON out).")
    parser.add_argument("--in", dest="in_path", help="Path to intake JSON; if omitted, reads stdin")
    args = parser.parse_args()

    try:
        payload = _load_payload(args.in_path)
        res = gate_intake(payload)
        out = {"status": res.status, "questions": res.questions, "normalized": res.normalized}
        sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

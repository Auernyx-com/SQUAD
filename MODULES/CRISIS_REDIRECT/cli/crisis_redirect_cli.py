from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _load_json_from_stdin() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _load_json_from_file(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() != ".json":
        raise SystemExit(f"Expected a .json input file, got: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description="CRISIS_REDIRECT (v1) — minimal crisis-safe redirect.")
    parser.add_argument("--in", dest="in_path", help="Input JSON file path. If omitted, reads from stdin.")

    args = parser.parse_args()

    if args.in_path:
        payload = _load_json_from_file(Path(args.in_path).expanduser().resolve())
    else:
        payload = _load_json_from_stdin()

    # Local import to keep CLI thin and avoid path issues.
    # Add module src to sys.path when running as a script.
    here = Path(__file__).resolve()
    module_root = here.parents[1]
    src_dir = module_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from crisis_redirect import crisis_redirect_to_dict  # type: ignore

    out = crisis_redirect_to_dict(payload)
    sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

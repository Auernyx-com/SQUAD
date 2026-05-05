from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema


@dataclass(frozen=True)
class Expected:
    path: Path
    should_validate: bool
    schema: Path


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _validate(schema_path: Path, instance_path: Path) -> None:
    schema = _load_json(schema_path)
    instance = _load_json(instance_path)
    jsonschema.Draft202012Validator(schema).validate(instance)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]

    cra_in_schema = repo_root / "pathfinder_cra" / "schema" / "cra.schema.json"
    cra_out_schema = repo_root / "pathfinder_cra" / "schema" / "cra_output.schema.json"

    tests = [
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "example_input.cra.v1.json",
            should_validate=True,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.refusal_unsafe_content.cra.v1.json",
            should_validate=True,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.free_text_field_should_fail.cra.v1.json",
            should_validate=False,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.bad_enum_should_fail.cra.v1.json",
            should_validate=False,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.unsafe_reason_code_should_fail.cra.v1.json",
            should_validate=False,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.stealth_field_should_fail.cra.v1.json",
            should_validate=False,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_input.missing_required_field.cra.v1.json",
            should_validate=False,
            schema=cra_in_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_output.refusal_unsafe_content.cra.report.v1.json",
            should_validate=True,
            schema=cra_out_schema,
        ),
        Expected(
            path=repo_root / "pathfinder_cra" / "examples" / "test_output.ok_minimal.cra.report.v1.json",
            should_validate=True,
            schema=cra_out_schema,
        ),
    ]

    failures: list[str] = []
    for t in tests:
        try:
            _validate(t.schema, t.path)
            if not t.should_validate:
                failures.append(f"EXPECTED INVALID but validated: {t.path.relative_to(repo_root)}")
            else:
                print(f"[OK ] {t.path.relative_to(repo_root)}")
        except jsonschema.ValidationError as e:
            if t.should_validate:
                failures.append(f"EXPECTED VALID but failed: {t.path.relative_to(repo_root)} :: {e.message}")
            else:
                print(f"[OK ] Expected invalid: {t.path.relative_to(repo_root)} :: {e.message}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"- {f}")
        return 2

    print("\nCRA fixtures validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

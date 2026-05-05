import json
import os
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    # BOM-tolerant
    return json.loads(path.read_text(encoding="utf-8-sig"))


def is_relative_repo_path(text: str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if "://" in text:
        return False
    if text.startswith(("/", "\\")):
        return False
    # Disallow drive-rooted paths
    if len(text) >= 2 and text[1] == ":":
        return False
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    registries = [
        repo_root / "AGENTS" / "CORE" / "PATHFINDER" / "module_registry.v1.json",
    ]

    failures: list[str] = []

    for registry_path in registries:
        if not registry_path.exists():
            failures.append(f"missing registry file: {registry_path}")
            continue

        try:
            registry = load_json(registry_path)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"invalid json: {registry_path} ({exc})")
            continue

        modules = registry.get("modules")
        if not isinstance(modules, list):
            failures.append(f"bad registry shape (modules not list): {registry_path}")
            continue

        for module in modules:
            if not isinstance(module, dict):
                failures.append(f"bad module entry (not object): {registry_path}")
                continue

            module_id = module.get("module_id", "<unknown>")
            entrypoint = module.get("entrypoint")

            if not is_relative_repo_path(entrypoint):
                failures.append(
                    f"{registry_path}: module_id={module_id} has invalid entrypoint: {entrypoint!r}"
                )
                continue

            resolved = (repo_root / entrypoint).resolve()
            # Ensure it doesn't escape repo_root
            try:
                resolved.relative_to(repo_root)
            except Exception:  # noqa: BLE001
                failures.append(
                    f"{registry_path}: module_id={module_id} entrypoint escapes repo: {entrypoint}"
                )
                continue

            if not resolved.exists():
                failures.append(
                    f"{registry_path}: module_id={module_id} missing entrypoint: {entrypoint}"
                )

    if failures:
        print("module registry validation failures:")
        for f in failures:
            print(f"- {f}")
        return 1

    print("module registry validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

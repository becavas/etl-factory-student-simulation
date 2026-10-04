"""Select Bundle roots affected by repository-relative changed paths."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_EXACT = {
    "environment.yml",
    "pyproject.toml",
    ".github/CODEOWNERS",
    ".github/workflows/pull-request.yml",
    "scripts/affected_bundles.py",
    "scripts/inspect_wheel.py",
}
SHARED_PREFIXES = (
    "tools/bundle_generator/",
    "src/enterprise_fabric/shared/",
    "tests/shared/",
    "src/enterprise_fabric/capability_names.py",
    "tests/test_capability_names.py",
)


def discover_bundles() -> dict[tuple[str, str], str]:
    bundles = {}
    for bundle in sorted(REPO_ROOT.glob("domains/*/capabilities/*/databricks.yml")):
        capability_root = bundle.parent
        key = (capability_root.parents[1].name, capability_root.name)
        bundles[key] = capability_root.relative_to(REPO_ROOT).as_posix()
    return bundles


def affected_bundles(paths: list[str]) -> list[str]:
    known = discover_bundles()
    selected: set[str] = set()
    shared_changed = False
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip()).as_posix()
        if not path or path == ".":
            continue
        if path in SHARED_EXACT or path.startswith(SHARED_PREFIXES):
            shared_changed = True
            continue
        parts = PurePosixPath(path).parts
        if len(parts) >= 5 and parts[0] == "domains" and parts[2] == "capabilities":
            key = (parts[1], parts[3])
            if key in known:
                selected.add(known[key])
            else:
                raise ValueError(
                    f"Ruta de capability sin Bundle actual: {path}. "
                    "Revisa si se eliminó un Bundle; su retiro requiere un procedimiento explícito."
                )
        elif len(parts) >= 4 and parts[0] in {"src", "tests"}:
            offset = 2 if parts[0] == "src" and parts[1] == "enterprise_fabric" else 1
            if len(parts) > offset + 1:
                key = (parts[offset], parts[offset + 1])
                if key in known:
                    selected.add(known[key])
    if shared_changed:
        selected.update(known.values())
    return sorted(selected)


def main() -> int:
    paths = [line.rstrip("\n") for line in sys.stdin]
    for bundle_root in affected_bundles(paths):
        print(bundle_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

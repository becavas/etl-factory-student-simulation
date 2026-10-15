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
    ".github/workflows/deploy-dev.yml",
    ".github/workflows/promote-release.yml",
    ".github/workflows/publish-release.yml",
    "scripts/affected_bundles.py",
    "scripts/inspect_wheel.py",
    "scripts/prepare_bundle_artifact.py",
    "scripts/require_unique_job.py",
    "scripts/verify_ci_identity.py",
    "scripts/verify_release_candidate.py",
    "scripts/verify_release_publication.py",
    "scripts/write_deployment_record.py",
    "scripts/write_promotion_record.py",
}
SHARED_PREFIXES = (
    "tools/bundle_generator/",
    "src/enterprise_fabric/shared/",
    "src/enterprise_fabric/core/",
    "tests/shared/",
    "src/enterprise_fabric/capability_names.py",
    "tests/test_capability_names.py",
)


def discover_bundles() -> dict[tuple[str, str], str]:
    bundles = {}
    patterns = (
        "domains/*/capabilities/*/databricks.yml",
        "domains/*/orchestration/databricks.yml",
    )
    for pattern in patterns:
        for config in sorted(REPO_ROOT.glob(pattern)):
            root = config.parent
            relative = root.relative_to(REPO_ROOT).as_posix()
            if root.name == "orchestration":
                key = (root.parent.name, "orchestration")
            else:
                key = (root.parents[1].name, root.name)
            bundles[key] = relative
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
        elif len(parts) >= 4 and parts[0] == "domains" and parts[2] == "orchestration":
            key = (parts[1], "orchestration")
            if key in known:
                selected.add(known[key])
            else:
                raise ValueError(
                    f"Ruta de orquestación sin Bundle actual: {path}. "
                    "Revisa si se eliminó un Bundle; su retiro requiere un procedimiento explícito."
                )
        elif len(parts) >= 4 and parts[0] in {"src", "tests"}:
            if parts[0] == "src" and parts[1] == "enterprise_fabric":
                offset = 2
            elif parts[0] == "tests" and parts[1] == "domains":
                offset = 2
            else:
                offset = 1
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

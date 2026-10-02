#!/usr/bin/env python3
"""Inspect the wheel contract without installing the artifact."""

from __future__ import annotations

import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

EXPECTED_DISTRIBUTION = "enterprise-fabric"
EXPECTED_ENTRY_POINT = "engineering-baseline = enterprise_fabric.cli:main"
EXPECTED_PACKAGE_FILES = {
    "enterprise_fabric/__init__.py",
    "enterprise_fabric/capability_names.py",
    "enterprise_fabric/cli.py",
}


def inspect_wheel(wheel_path: Path) -> None:
    if wheel_path.suffix != ".whl" or not wheel_path.is_file():
        raise ValueError(f"Not a wheel file: {wheel_path}")

    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_point_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(metadata_names) != 1 or len(entry_point_names) != 1:
            raise ValueError("Wheel must contain one METADATA and one entry_points.txt")

        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        distribution = metadata.get("Name")
        version = metadata.get("Version")
        entry_points = archive.read(entry_point_names[0]).decode("utf-8")

    missing_files = sorted(EXPECTED_PACKAGE_FILES - names)
    if distribution != EXPECTED_DISTRIBUTION:
        raise ValueError(f"Unexpected distribution: {distribution}")
    if EXPECTED_ENTRY_POINT not in entry_points:
        raise ValueError("Required console entry point is missing")
    if missing_files:
        raise ValueError(f"Missing package files: {', '.join(missing_files)}")

    print(f"OK wheel={wheel_path.name} distribution={distribution} version={version}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: inspect_wheel.py <one-wheel-file>", file=sys.stderr)
        return 2
    try:
        inspect_wheel(Path(sys.argv[1]))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Inspect the wheel contract without installing the artifact."""

from __future__ import annotations

import argparse
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

EXPECTED_DISTRIBUTION = "enterprise-fabric"
EXPECTED_ENTRY_POINTS = {
    "engineering-baseline = enterprise_fabric.cli:main",
    "pedidos-bronze = enterprise_fabric.retail.pedidos.entrypoints:run_bronze",
    "pedidos-silver = enterprise_fabric.retail.pedidos.entrypoints:run_silver",
    "clientes-bronze = enterprise_fabric.retail.clientes.entrypoints:run_bronze",
    "clientes-silver = enterprise_fabric.retail.clientes.entrypoints:run_silver",
    "productos-bronze = enterprise_fabric.retail.productos.entrypoints:run_bronze",
    "productos-silver = enterprise_fabric.retail.productos.entrypoints:run_silver",
    "ventas-dimensions = enterprise_fabric.retail.ventas.entrypoints:run_dimensions",
    "ventas-fact = enterprise_fabric.retail.ventas.entrypoints:run_fact",
    "ventas-daily-kpi = enterprise_fabric.retail.ventas.entrypoints:run_daily_kpi",
}
EXPECTED_PACKAGE_FILES = {
    "enterprise_fabric/__init__.py",
    "enterprise_fabric/capability_names.py",
    "enterprise_fabric/cli.py",
    "enterprise_fabric/shared/__init__.py",
    "enterprise_fabric/shared/delta.py",
    "enterprise_fabric/shared/identifiers.py",
    "enterprise_fabric/shared/spark.py",
    "enterprise_fabric/retail/pedidos/__init__.py",
    "enterprise_fabric/retail/pedidos/bronze.py",
    "enterprise_fabric/retail/pedidos/entrypoints.py",
    "enterprise_fabric/retail/pedidos/quality.py",
    "enterprise_fabric/retail/pedidos/schemas.py",
    "enterprise_fabric/retail/pedidos/silver.py",
    "enterprise_fabric/retail/clientes/__init__.py",
    "enterprise_fabric/retail/clientes/bronze.py",
    "enterprise_fabric/retail/clientes/entrypoints.py",
    "enterprise_fabric/retail/clientes/schemas.py",
    "enterprise_fabric/retail/clientes/silver.py",
    "enterprise_fabric/retail/productos/__init__.py",
    "enterprise_fabric/retail/productos/bronze.py",
    "enterprise_fabric/retail/productos/entrypoints.py",
    "enterprise_fabric/retail/productos/schemas.py",
    "enterprise_fabric/retail/productos/silver.py",
    "enterprise_fabric/retail/ventas/__init__.py",
    "enterprise_fabric/retail/ventas/aggregate.py",
    "enterprise_fabric/retail/ventas/dimensions.py",
    "enterprise_fabric/retail/ventas/entrypoints.py",
    "enterprise_fabric/retail/ventas/fact.py",
    "enterprise_fabric/retail/ventas/keys.py",
    "enterprise_fabric/retail/ventas/semantic.py",
    "enterprise_fabric/retail/ventas/tables.py",
}


def inspect_wheel(
    wheel_path: Path,
    extra_modules: list[str] | None = None,
    extra_entry_points: list[str] | None = None,
) -> None:
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
    missing_entry_points = sorted(
        entry_point for entry_point in EXPECTED_ENTRY_POINTS if entry_point not in entry_points
    )
    if missing_entry_points:
        raise ValueError(f"Missing entry points: {', '.join(missing_entry_points)}")
    if missing_files:
        raise ValueError(f"Missing package files: {', '.join(missing_files)}")

    if extra_modules:
        for mod in extra_modules:
            mod_path = mod.replace(".", "/") + ".py"
            if mod_path not in names:
                raise ValueError(f"Missing requested module: {mod} ({mod_path})")

    if extra_entry_points:
        for ep in extra_entry_points:
            if ep not in entry_points:
                raise ValueError(f"Missing requested entry point: {ep}")

    print(f"OK wheel={wheel_path.name} distribution={distribution} version={version}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect wheel contents and entry points")
    parser.add_argument("wheel_path", type=Path, help="Path to wheel file")
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        default=[],
        help="Specific module required in wheel (e.g. enterprise_fabric.retail.ventas.aggregate)",
    )
    parser.add_argument(
        "--entry-point",
        action="append",
        dest="entry_points",
        default=[],
        help="Specific entry point required in wheel (e.g. ventas-daily-kpi)",
    )
    args = parser.parse_args()

    try:
        inspect_wheel(args.wheel_path, args.modules, args.entry_points)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

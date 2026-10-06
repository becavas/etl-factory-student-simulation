"""Databricks Job entrypoints for retail/pedidos."""

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from enterprise_fabric.retail.pedidos.bronze import ingest_bronze, parse_bool
from enterprise_fabric.retail.pedidos.silver import publish_silver


def build_bronze_parser() -> argparse.ArgumentParser:
    """Build the strict argument parser for Bronze task."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source_volume_path", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--fail_after_pedidos", default="false")
    parser.add_argument("--snapshot_mode", choices=("FULL", "INCREMENTAL"), default=None)
    parser.add_argument("--aggregate_mode", choices=("FULL", "INCREMENTAL"), default=None)
    return parser


def run_bronze(argv: list[str] | None = None) -> None:
    """Entry point invoked by python_wheel_task.

    Databricks resuelve este entry point vía `pyproject.toml` y lo invoca
    con cero argumentos de Python (`entry_point()`), exactamente igual que
    si el console-script se ejecutara manualmente desde una terminal. Los
    `named_parameters` del Job se inyectan como argumentos de línea de
    comandos (`--clave valor`) en `sys.argv`, no como kwargs de la función.
    Por eso este entry point parsea `sys.argv` explícitamente en vez de
    declarar los parámetros como argumentos de función.
    """
    args = build_bronze_parser().parse_args(argv)

    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("An active SparkSession is required")
    result = ingest_bronze(
        spark=spark,
        catalog=args.catalog,
        source_volume_path=args.source_volume_path,
        batch_id=args.batch_id,
        run_id=args.run_id,
        fail_after_pedidos=parse_bool(args.fail_after_pedidos),
    )
    print(json.dumps(asdict(result), sort_keys=True))


def build_silver_parser() -> argparse.ArgumentParser:
    """Build the strict argument parser for Silver task."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--quality_run_id", required=True)
    parser.add_argument(
        "--fail_after_pedidos", type=parse_bool, default=False, help=argparse.SUPPRESS
    )
    parser.add_argument("--snapshot_mode", choices=("FULL", "INCREMENTAL"), default=None)
    parser.add_argument("--aggregate_mode", choices=("FULL", "INCREMENTAL"), default=None)
    return parser


def run_silver(argv: list[str] | None = None) -> None:
    """Entry point invoked by python_wheel_task.

    Igual que `run_bronze` (§8.8, Fase 4): Databricks invoca este entry
    point sin argumentos de Python e inyecta los `named_parameters` en
    `sys.argv`. Se parsean explícitamente en vez de declararlos como
    argumentos de función.

    Los parámetros de nivel Job se propagan a las wheel tasks con
    named_parameters. Se declaran snapshot_mode, aggregate_mode y
    fail_after_pedidos como argumentos comunes conocidos, sin usarlos
    para cambiar la publicación Silver.
    """
    args = build_silver_parser().parse_args(argv)

    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("An active SparkSession is required")
    result = publish_silver(
        spark=spark,
        catalog=args.catalog,
        batch_id=args.batch_id,
        quality_run_id=args.quality_run_id,
    )
    print(json.dumps(asdict(result), sort_keys=True))

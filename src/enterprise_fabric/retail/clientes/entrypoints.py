"""Databricks Job entrypoints for retail/clientes."""

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from enterprise_fabric.retail.clientes.bronze import ingest_bronze
from enterprise_fabric.retail.clientes.silver import publish_silver


def _spark() -> SparkSession:
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("An active SparkSession is required")
    return spark


def build_bronze_parser() -> argparse.ArgumentParser:
    """Build the strict argument parser for Bronze task."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source_volume_path", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--snapshot_mode", choices=("FULL", "INCREMENTAL"), default=None)
    parser.add_argument("--aggregate_mode", choices=("FULL", "INCREMENTAL"), default=None)
    return parser


def run_bronze(argv: list[str] | None = None) -> None:
    """Entry point invoked by python_wheel_task.

    Databricks invoca este entry point sin argumentos de Python e inyecta
    los `named_parameters` en `sys.argv` (igual que en Fase 4, §8.8); se
    parsean explícitamente en vez de declararlos como argumentos de función.
    """
    args = build_bronze_parser().parse_args(argv)

    result = ingest_bronze(
        _spark(), args.catalog, args.source_volume_path, args.batch_id, args.run_id
    )
    print(json.dumps(asdict(result), sort_keys=True))


def build_silver_parser() -> argparse.ArgumentParser:
    """Build the strict argument parser for Silver task."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--quality_run_id", required=True)
    parser.add_argument("--snapshot_mode", choices=("FULL", "INCREMENTAL"), default=None)
    parser.add_argument("--aggregate_mode", choices=("FULL", "INCREMENTAL"), default=None)
    return parser


def run_silver(argv: list[str] | None = None) -> None:
    """Entry point invoked by python_wheel_task (ver nota en `run_bronze`)."""
    args = build_silver_parser().parse_args(argv)

    result = publish_silver(_spark(), args.catalog, args.batch_id, args.quality_run_id)
    print(json.dumps(asdict(result), sort_keys=True))

"""Databricks Job entrypoints for retail/ventas."""

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from enterprise_fabric.retail.ventas.dimensions import publish_dimensions
from enterprise_fabric.retail.ventas.fact import publish_fact
from enterprise_fabric.retail.ventas.tables import ensure_gold_tables


def _spark() -> SparkSession:
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("An active SparkSession is required")
    return spark


def run_dimensions() -> None:
    """Entry point invoked by python_wheel_task.

    Databricks invoca este entry point sin argumentos de Python e inyecta
    los `named_parameters` en `sys.argv` (igual que en Fase 4, §8.8); se
    parsean explícitamente en vez de declararlos como argumentos de función.

    Usa `parse_known_args()`, no `parse_args()` (hallazgo real de la Fase 5,
    §7): los parámetros de nivel Job (`resources.jobs.<job>.parameters`) se
    inyectan automáticamente como `--clave valor` en TODAS las tasks
    `python_wheel_task` que usan `named_parameters`, incluso si esa task no
    los declaró. Este Job ya tiene dos tasks con parámetros de nivel Job
    distintos (`snapshot_mode` no lo consume `run_fact`) y la Fase 10 agrega
    una tercera (`aggregate_mode`, que tampoco consume esta task) — sin
    `parse_known_args()`, cualquiera de las dos tasks fallaría con
    `unrecognized arguments` en cuanto reciba un parámetro que no declaró.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--snapshot_mode", required=True)
    args, _ = parser.parse_known_args()

    spark = _spark()
    ensure_gold_tables(spark, args.catalog)
    result = publish_dimensions(spark, args.catalog, args.batch_id, args.snapshot_mode)
    print(json.dumps(asdict(result), sort_keys=True))


def run_fact() -> None:
    """Entry point invoked by python_wheel_task (ver nota en `run_dimensions`)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--batch_id", required=True)
    args, _ = parser.parse_known_args()

    spark = _spark()
    ensure_gold_tables(spark, args.catalog)
    result = publish_fact(spark, args.catalog, args.batch_id)
    print(json.dumps(asdict(result), sort_keys=True))

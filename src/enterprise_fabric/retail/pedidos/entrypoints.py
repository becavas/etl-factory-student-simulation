"""Databricks Job entrypoints for retail/pedidos."""

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from enterprise_fabric.retail.pedidos.bronze import ingest_bronze, parse_bool


def run_bronze() -> None:
    """Entry point invoked by python_wheel_task.

    Databricks resuelve este entry point vía `pyproject.toml` y lo invoca
    con cero argumentos de Python (`entry_point()`), exactamente igual que
    si el console-script se ejecutara manualmente desde una terminal. Los
    `named_parameters` del Job se inyectan como argumentos de línea de
    comandos (`--clave valor`) en `sys.argv`, no como kwargs de la función.
    Por eso este entry point parsea `sys.argv` explícitamente en vez de
    declarar los parámetros como argumentos de función.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source_volume_path", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--fail_after_pedidos", default="false")
    args = parser.parse_args()

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

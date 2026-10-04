"""Databricks Job entrypoints for retail/productos."""

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from enterprise_fabric.retail.productos.bronze import ingest_bronze
from enterprise_fabric.retail.productos.silver import publish_silver


def _spark() -> SparkSession:
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("An active SparkSession is required")
    return spark


def run_bronze() -> None:
    """Entry point invoked by python_wheel_task."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source_volume_path", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--run_id", required=True)
    args = parser.parse_args()

    result = ingest_bronze(
        _spark(),
        args.catalog,
        args.source_volume_path,
        args.batch_id,
        args.run_id,
    )
    print(json.dumps(asdict(result), sort_keys=True))


def run_silver() -> None:
    """Entry point invoked by python_wheel_task."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--batch_id", required=True)
    parser.add_argument("--quality_run_id", required=True)
    args = parser.parse_args()

    result = publish_silver(_spark(), args.catalog, args.batch_id, args.quality_run_id)
    print(json.dumps(asdict(result), sort_keys=True))

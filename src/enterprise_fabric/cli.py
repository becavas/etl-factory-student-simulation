"""Entrypoints executed by Databricks Jobs."""

import json
from importlib.metadata import version
from pathlib import Path

from enterprise_fabric.capability_names import normalize_capability_name


def main() -> None:
    """Emit evidence that Databricks executed the installed wheel."""
    evidence = {
        "distribution": "enterprise-fabric",
        "version": version("enterprise-fabric"),
        "module_file": str(Path(__file__).resolve()),
        "sample_capability": normalize_capability_name("Pedidos Demo"),
    }
    print(json.dumps(evidence, sort_keys=True))

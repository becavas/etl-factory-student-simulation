#!/usr/bin/env python3
"""Verifica dependencias externas de sandbox sin crear ni modificar recursos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath


PROFILE = "sandbox"
EXPECTED_SCHEMAS = ("landing", "bronze", "silver", "gold")
EXPECTED_VOLUMES = ("pedidos_source", "clientes_source", "productos_source")
EXPECTED_SOURCE_ENTRIES = {
    "pedidos_source": ("pedidos", "pedido_items"),
    "clientes_source": ("clientes",),
    "productos_source": ("productos", "categorias"),
}
EXPECTED_TRAINING_FILES = {
    "pedidos_source": {"pedidos": "pedidos.csv", "pedido_items": "pedido_items.csv"},
    "clientes_source": {"clientes": "clientes.csv"},
    "productos_source": {"productos": "productos.csv", "categorias": "categorias.csv"},
}


@dataclass(frozen=True)
class CheckResult:
    status: str
    resource: str
    detail: str


class CliFailure(RuntimeError):
    def __init__(self, command: list[str], returncode: int, output: str) -> None:
        self.command = command
        self.returncode = returncode
        self.output = output.strip()
        super().__init__(self.output)


def run_json(*args: str) -> object:
    command = ["databricks", *args, "--profile", PROFILE, "-o", "json"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        raise CliFailure(command, completed.returncode, output)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CliFailure(command, completed.returncode, completed.stdout) from exc


def classify_failure(exc: CliFailure) -> str:
    normalized = exc.output.upper()
    missing_markers = (
        "RESOURCE_DOES_NOT_EXIST",
        "NOT FOUND",
        "DOES NOT EXIST",
        "NO SUCH",
    )
    forbidden_markers = (
        "PERMISSION_DENIED",
        "FORBIDDEN",
        "UNAUTHORIZED",
        "NOT AUTHORIZED",
        "INSUFFICIENT PERMISSIONS",
    )
    if any(marker in normalized for marker in missing_markers):
        return "MISSING"
    if any(marker in normalized for marker in forbidden_markers):
        return "FORBIDDEN"
    return "ERROR"


def failed(resource: str, exc: CliFailure) -> CheckResult:
    last_line = exc.output.splitlines()[-1] if exc.output else "sin detalle"
    return CheckResult(classify_failure(exc), resource, last_line)


def check_json(resource: str, *args: str) -> tuple[CheckResult, object | None]:
    try:
        payload = run_json(*args)
    except CliFailure as exc:
        return failed(resource, exc), None
    return CheckResult("OK", resource, "accesible"), payload


def list_volume_entries(path: str) -> set[str]:
    payload = run_json("fs", "ls", path)
    if not isinstance(payload, list):
        raise ValueError(f"Respuesta inesperada para {path}: {type(payload).__name__}")
    entries: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_entry = item.get("name") or item.get("path")
        if isinstance(raw_entry, str):
            normalized = raw_entry.rstrip("/")
            entries.add(PurePosixPath(normalized).name)
    return entries


def policy_allows_single_user(definition: object) -> bool:
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except json.JSONDecodeError:
            return False
    if not isinstance(definition, dict):
        return False
    rule = definition.get("data_security_mode")
    if rule is None:
        return True
    if not isinstance(rule, dict):
        return False
    if rule.get("type") == "fixed":
        return rule.get("value") in {"SINGLE_USER", "DATA_SECURITY_MODE_DEDICATED"}
    if rule.get("type") == "allowlist":
        values = set(rule.get("values", []))
        return bool(values & {"SINGLE_USER", "DATA_SECURITY_MODE_DEDICATED"})
    return True


def main() -> int:
    catalog = os.environ.get("EF_CATALOG", "").strip()
    if not catalog:
        print("ERROR: define EF_CATALOG con el catálogo asignado")
        return 2
    policy_id = os.environ.get("EF_POLICY_ID", "").strip()
    results: list[CheckResult] = []

    identity_result, identity = check_json("identity", "current-user", "me")
    if identity_result.status == "OK" and isinstance(identity, dict):
        identity_result = CheckResult(
            "OK", "identity", str(identity.get("userName", "desconocido"))
        )
    results.append(identity_result)

    catalog_result, _ = check_json(f"catalog:{catalog}", "catalogs", "get", catalog)
    results.append(catalog_result)

    for schema in EXPECTED_SCHEMAS:
        full_name = f"{catalog}.{schema}"
        result, _ = check_json(f"schema:{full_name}", "schemas", "get", full_name)
        results.append(result)

    for volume in EXPECTED_VOLUMES:
        full_name = f"{catalog}.landing.{volume}"
        result, _ = check_json(f"volume:{full_name}", "volumes", "read", full_name)
        results.append(result)
        if result.status != "OK":
            continue
        path = f"dbfs:/Volumes/{catalog}/landing/{volume}"
        try:
            observed = list_volume_entries(path)
        except CliFailure as exc:
            results.append(failed(f"files:{full_name}", exc))
            continue
        except ValueError as exc:
            results.append(CheckResult("ERROR", f"files:{full_name}", str(exc)))
            continue
        missing = sorted(set(EXPECTED_SOURCE_ENTRIES[volume]) - observed)
        if missing:
            results.append(
                CheckResult("MISSING", f"files:{full_name}", f"faltan: {', '.join(missing)}")
            )
        else:
            results.append(CheckResult("OK", f"files:{full_name}", "dataset disponible"))
            for entity, filename in EXPECTED_TRAINING_FILES[volume].items():
                batch_path = f"{path}/{entity}/batch_id=training_001"
                try:
                    batch_files = list_volume_entries(batch_path)
                except CliFailure as exc:
                    results.append(failed(f"file:{entity}:training_001", exc))
                    continue
                if filename not in batch_files:
                    results.append(CheckResult(
                        "MISSING", f"file:{entity}:training_001", f"falta {filename}"
                    ))
                else:
                    results.append(CheckResult(
                        "OK", f"file:{entity}:training_001", filename
                    ))

    if not policy_id:
        results.append(
            CheckResult(
                "MISSING",
                "compute_policy:uc_standard_job_compute",
                "EF_POLICY_ID no fue entregado por Data Platform",
            )
        )
    else:
        policy_result, policy = check_json(
            "compute_policy:uc_standard_job_compute",
            "cluster-policies",
            "get",
            policy_id,
        )
        if policy_result.status == "OK" and isinstance(policy, dict):
            policy_name = str(policy.get("name", "sin nombre"))
            if not policy_allows_single_user(policy.get("definition")):
                policy_result = CheckResult(
                    "ERROR",
                    "compute_policy:uc_standard_job_compute",
                    f"{policy_name}: no permite SINGLE_USER/Dedicated",
                )
            else:
                policy_result = CheckResult(
                    "OK",
                    "compute_policy:uc_standard_job_compute",
                    f"{policy_name}: SINGLE_USER/Dedicated permitido",
                )
        results.append(policy_result)

    print("STATUS     RESOURCE                                      DETAIL")
    print("---------- --------------------------------------------- --------------------")
    for result in results:
        print(f"{result.status:<10} {result.resource:<45} {result.detail}")

    failures = [result for result in results if result.status != "OK"]
    if failures:
        print(f"\nResultado: BLOQUEADO ({len(failures)} dependencia(s) pendiente(s)).")
        return 1
    print("\nResultado: LISTO para construir la primera capability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Capability retail/clientes

## Propósito y ownership

- Propósito: publicar clientes sintéticos tipados y trazables desde Landing hasta Silver.
- Owner de datos: `retail-data-governance` (@becavas).
- Owner técnico: `retail-data-engineering` (@becavas).
- Soporte de plataforma: consultar `docs/platform-dependencies.md`.

## Clasificación

Contiene datos personales: nombres, apellidos, email y fecha de nacimiento. Los datasets de
capacitación son sintéticos. Bronze y quarantine requieren acceso y retención restringidos.

## Entrada

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| clientes | `clientes/batch_id=<batch_id>` | CSV con header | batch completo e inmutable al declararse listo |

Volume sandbox: `retail_sbx_a001.landing.clientes_source`.

## Salidas

| Tabla | Grano | Uso |
|---|---|---|
| `bronze.clientes_raw` | fila fuente | preservación y lineage |
| `silver.clientes_curated` | cliente + batch | registro tipado, deduplicado y válido |
| `silver.clientes_quarantine` | registro + quality run | payload y reglas violadas |
| `silver.clientes_quality_metrics` | regla + quality run | evidencia por ejecución |

Silver deduplica dentro del batch; no representa todavía el cliente vigente entre batches.

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía |
|---|---|
| `CLI-001` | Bronze conserva las ocho columnas fuente como string y agrega lineage mínimo. |
| `CLI-002` | Reprocesar un batch reemplaza solo ese batch. |
| `CLI-003` | Silver normaliza strings vacíos y tipa fechas/timestamps de forma tolerante. |
| `CLI-004` | Un duplicado conserva el registro con mayor recencia y desempate determinista. |
| `CLI-005` | El email se normaliza a minúsculas y un formato inválido va a quarantine. |
| `CLI-006` | Fecha de nacimiento futura, país inválido y estado desconocido van a quarantine. |
| `CLI-007` | ID o timestamp obligatorio inválido persiste evidencia y falla Silver. |
| `CLI-008` | Métricas y quarantine conservan batch, quality run y lineage fuente. |
<!-- guarantees:end -->

Agregar o retirar una garantía exige actualizar sus tests. Cambiar su significado requiere un ID
nuevo o una decisión explícita revisada por el owner.

## Automatización

- Spec: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Estándar: [`docs/standards/bundle-job-specs.md`](../../../../../docs/standards/bundle-job-specs.md).

## Ejecución

```bash
cd domains/retail/capabilities/clientes
databricks bundle validate --target sandbox --profile sandbox
databricks bundle deploy --target sandbox --profile sandbox
databricks bundle run clientes_e2e_job --target sandbox --profile sandbox \
  -- --batch_id=training_001
```

Una regla `FAIL` conserva métricas y quarantine y evita publicar curated.

## Evidencia mínima

- commit, PR, Job URL y run ID;
- batch y conteos Bronze/Silver;
- métricas y quarantine del quality run;
- versiones Delta y `userMetadata`;
- reproceso idempotente;
- prueba negativa y owners que recibieron review.

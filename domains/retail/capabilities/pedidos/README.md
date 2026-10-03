# Capability retail/pedidos

## Propósito y ownership

- Propósito: publicar pedidos e items recibidos desde `pedidos_source` en Bronze trazable y Silver conformada con calidad observable.
- Owner de datos: `retail-data-governance`.
- Owner técnico: `retail-data-engineering`.
- Soporte de plataforma: consultar `docs/platform-dependencies.md`.

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Pedidos | `pedidos/batch_id=<batch_id>` | CSV con header | batch inmutable al declararse listo |
| Items | `pedido_items/batch_id=<batch_id>` | CSV con header | mismo batch lógico que pedidos |

Volume físico de sandbox: `retail_sbx_a001.landing.pedidos_source`.

## Salidas Bronze

| Tabla | Grano Bronze | Estrategia |
|---|---|---|
| `bronze.pedidos_raw` | una fila recibida por pedido y archivo | reemplazo selectivo por batch |
| `bronze.pedido_items_raw` | una fila recibida por item y archivo | reemplazo selectivo por batch |

Bronze no garantiza unicidad de claves ni validez semántica. Conserva campos fuente como string y añade metadata técnica.

## Salidas Silver

| Tabla | Grano | Uso |
|---|---|---|
| `silver.pedidos_curated` | pedido + batch | pedidos tipados que cumplen reglas |
| `silver.pedido_items_curated` | pedido + item + batch | items tipados que cumplen reglas |
| `silver.pedidos_quarantine` | registro rechazado + quality run | payload y reglas violadas |
| `silver.pedidos_quality_metrics` | regla + entidad + quality run | conteos observados por ejecución |

Silver deduplica dentro de cada batch. No representa todavía el estado global vigente entre batches.

## Operación inicial (Bronze únicamente)

```bash
cd domains/retail/capabilities/pedidos
databricks bundle validate --target sandbox --profile sandbox
databricks bundle deploy --target sandbox --profile sandbox
databricks bundle run pedidos_bronze_job --target sandbox --profile sandbox \
  -- --batch_id=training_001 --fail_after_pedidos=false
```

Reprocesar el mismo batch reemplaza sus filas; no lo duplica. Las dos tablas se publican mediante transacciones independientes. Ante un fallo parcial, corregir la causa y repetir el mismo `batch_id`.

## Ejecución E2E (Bronze + Silver)

```bash
cd domains/retail/capabilities/pedidos
databricks bundle run pedidos_e2e_job --target sandbox --profile sandbox \
  -- --batch_id=training_001 --fail_after_pedidos=false
```

El Job usa classic job compute compartido únicamente por sus tasks durante el run (`pedidos_shared_job_compute`).
Una regla `FAIL` conserva métricas y quarantine, no publica curated y termina la task con error (`QualityGateError`).

## Evidencia mínima

- URL y run ID del Job.
- Run ID y estado de ambas tasks (`ingest_pedidos_bronze`, `publish_pedidos_silver`).
- Batch ID y conteos Silver (`pedidos_curated`, `pedido_items_curated`).
- Métricas por regla en `pedidos_quality_metrics`.
- Cantidad y rule IDs de quarantine en `pedidos_quarantine`.
- `_record_hash` y archivos fuente observados.
- Versión Delta y `userMetadata` de cada salida.
- Resultado del reproceso idempotente.

## Contrato de automatización

- Spec: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso desplegable: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Schema y reglas: [`tools/bundle_generator`](../../../../../tools/bundle_generator).
- Estándar: [`docs/standards/bundle-job-specs.md`](../../../../../docs/standards/bundle-job-specs.md).

```bash
python -m tools.bundle_generator generate --spec \
  domains/retail/capabilities/pedidos/specs/jobs.yml
python -m tools.bundle_generator generate --all --check
```

`jobs.generated.yml` se revisa y versiona, pero no se edita manualmente.

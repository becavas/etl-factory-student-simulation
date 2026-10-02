# Capability retail/pedidos

## Propósito y ownership

- Propósito: publicar pedidos e items recibidos desde `pedidos_source` en Bronze trazable.
- Owner de datos: `retail-data-governance`.
- Owner técnico: `retail-data-engineering`.
- Soporte de plataforma: consultar `docs/platform-dependencies.md`.

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Pedidos | `pedidos/batch_id=<batch_id>` | CSV con header | batch inmutable al declararse listo |
| Items | `pedido_items/batch_id=<batch_id>` | CSV con header | mismo batch lógico que pedidos |

Volume físico de sandbox: `retail_sbx_a001.landing.pedidos_source`.

## Salidas

| Tabla | Grano Bronze | Estrategia |
|---|---|---|
| `bronze.pedidos_raw` | una fila recibida por pedido y archivo | reemplazo selectivo por batch |
| `bronze.pedido_items_raw` | una fila recibida por item y archivo | reemplazo selectivo por batch |

Bronze no garantiza unicidad de claves ni validez semántica. Conserva campos fuente como string y añade metadata técnica.

## Operación inicial

```bash
cd domains/retail/capabilities/pedidos
databricks bundle validate --target sandbox --profile sandbox
databricks bundle deploy --target sandbox --profile sandbox
databricks bundle run pedidos_bronze_job --target sandbox --profile sandbox \
  -- --batch_id=training_001 --fail_after_pedidos=false
```

Reprocesar el mismo batch reemplaza sus filas; no lo duplica. Las dos tablas se publican mediante transacciones independientes. Ante un fallo parcial, corregir la causa y repetir el mismo `batch_id`.

## Evidencia mínima

- URL y run ID del Job.
- batch ID ejecutado.
- conteos de ambas tablas para el batch.
- `_record_hash` y archivos fuente observados.
- versiones Delta producidas.
- resultado del reproceso idempotente.

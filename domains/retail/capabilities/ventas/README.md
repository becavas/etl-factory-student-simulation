# Capability: retail/ventas

## 1. Identificación y Gobernanza

- **Dominio**: `retail`
- **Capability**: `ventas`
- **Owner Técnico**: Data Engineering (@becavas)
- **Data Owner**: Retail Governance Team (@becavas)
- **Clasificación de Datos**: Confidencial / Datos personales sujetos a políticas corporativas.
- **SLO de Publicación**: Batch diario / bajo demanda tras completitud upstream.

---

## 2. Propósito y Alcance

La capability `retail/ventas` es responsable del modelo dimensional Gold en Unity Catalog (`retail_sbx_a001`). Consume datos curados de las capas Silver producidas independientemente por `pedidos`, `clientes` y `productos`, desacoplada de su código interno y comunicándose exclusivamente mediante tablas Delta y contratos gobernados.

Publica dos dimensiones Type 1 y una tabla de hechos transaccionales a nivel de línea de venta:
1. `gold.dim_cliente`: Dimensión Type 1 minimizada por `cliente_id`.
2. `gold.dim_producto`: Dimensión Type 1 de catálogo y categorías por `producto_id`.
3. `gold.fact_ventas`: Tabla de hechos granular por (`pedido_id`, `item_id`).

---

## 3. Minimización y Protección de Datos

`dim_cliente` implementa minimización estricta: incluye `cliente_id`, país y estado, pero **excluye** datos personales directos (nombres, apellidos, correo electrónico, fecha de nacimiento) innecesarios para el caso analítico de ventas.

`fact_ventas` conserva `_source_cliente_id` exclusivamente para trazabilidad técnica y resolución de dimensiones tardías; sigue siendo considerado un dato personal vinculado y mantiene las mismas políticas de acceso y auditoría que la capa Silver.

---

## 4. Grano y Políticas de Carga

| Tabla | Grano | Tipo de Carga | Política de Ausencia | Eliminación Física |
|---|---|---|---|---|
| `gold.dim_cliente` | Una fila por `cliente_id` | Type 1 `MERGE` | Desactiva solo con snapshot `FULL` | No automática |
| `gold.dim_producto` | Una fila por `producto_id` | Type 1 `MERGE` | Desactiva solo con snapshot `FULL` | No automática |
| `gold.fact_ventas` | Una fila por (`pedido_id`, `item_id`) | Upsert `MERGE` | Conserva líneas previas (no borra por omisión) | No automática |

### Modos de Snapshot
- `INCREMENTAL`: Inserta nuevas dimensiones y actualiza atributos si cambia `_payload_hash`. Una ausencia en el lote no modifica registros existentes.
- `FULL`: Además de insertar y actualizar, marca `is_active = false` para aquellas dimensiones ausentes en el lote, conservando su historial.

### Cancelaciones y Datos Tardíos
- **Venta cancelada**: Se conserva la línea en `fact_ventas` actualizando `estado_pedido = CANCELADO` e `is_cancelled = true`.
- **Miembro desconocido (Unknown Member)**: Clave canónica reservada de 64 ceros (`UNKNOWN_SK`) y clave natural `__UNKNOWN__`. Nunca se desactiva.
- **Late-Arriving Dimension**: Hechos con cliente o producto no disponible se asocian a `UNKNOWN_SK`. Al ingresar la dimensión tardía en un lote posterior y reprocesar el hecho, la FK se actualiza a la clave real conservando la `venta_linea_sk` original.

---

## 5. Garantías de Calidad y Contratos Verificables

<!-- guarantees:start -->
| ID | Garantía | Acción | Descripción |
|---|---|---|---|
| `VEN-IN-001` | Entradas Silver completas | FAIL | Las cinco entradas Silver existen para el batch solicitado antes de publicar Gold. |
| `VEN-IN-002` | Unicidad estricta de MERGE | FAIL | Cada fuente tiene una fila como máximo por clave de MERGE antes de escribir en Delta. |
| `VEN-DI-001` | Claves canónicas versionadas | FAIL | Las surrogate keys usan encoding canónico versionado `v1` sobre JSON determinista. |
| `VEN-DI-002` | Unknown member reservado | FAIL | El miembro desconocido existe con 64 ceros y clave reservada `__UNKNOWN__`, nunca se desactiva. |
| `VEN-DI-003` | Type 1 por payload hash | OBSERVE | La actualización Type 1 solo modifica atributos si `_payload_hash` cambia, preservando creación. |
| `VEN-DI-004` | Ausencias solo en FULL | OBSERVE | Dimensiones ausentes solo se desactivan (`is_active=false`) ante snapshot `FULL` explícito. |
| `VEN-FA-001` | Grano del hecho unitario | FAIL | `fact_ventas` mantiene exactamente una fila por (`pedido_id`, `item_id`). |
| `VEN-FA-002` | Reconciliación pedido/líneas | FAIL | El importe sumado de líneas reconcilia contra `monto_total` del pedido (tolerancia 0.01). |
| `VEN-FA-003` | Asignación de unknown member | OBSERVE | Dimensiones no encontradas o inactivas asignan `UNKNOWN_SK` sin perder la natural key origen. |
| `VEN-FA-004` | Resolución de datos tardíos | OBSERVE | Late arrival actualiza la clave foránea del hecho a la dimensión real sin duplicar la línea. |
| `VEN-FA-005` | Preservación de cancelaciones | OBSERVE | Las cancelaciones se auditan con `is_cancelled=true`; omisiones en lotes no borran hechos. |
| `VEN-MG-001` | Reproceso idempotente | OBSERVE | Una segunda ejecución con los mismos datos reporta 0 inserts y 0 updates en métricas Delta. |
| `VEN-CO-001` | Compute compartido en Job | OBSERVE | Ambas tasks compatibles del Job reutilizan el mismo cluster compartido (`ventas_shared_job_compute`). |
<!-- guarantees:end -->

---

## 6. Runbook Operativo

### Requisitos Previos
- Workspace Databricks autenticado (perfil `sandbox`).
- Variables de entorno mínimas:
  ```bash
  export BUNDLE_VAR_catalog="retail_sbx_a001"
  export BUNDLE_VAR_policy_id="0014E7B094CA30EB"
  export BUNDLE_VAR_spark_version="16.4.x-scala2.12"
  export BUNDLE_VAR_node_type_id="Standard_F4s_v2"
  ```

### Despliegue del Bundle
```bash
cd domains/retail/capabilities/ventas
databricks bundle deploy --target sandbox --profile sandbox
```

### Ejecución de Lote
```bash
databricks bundle run ventas_gold_job \
  --target sandbox \
  --profile sandbox \
  --params batch_id=gold_initial_001,snapshot_mode=FULL
```

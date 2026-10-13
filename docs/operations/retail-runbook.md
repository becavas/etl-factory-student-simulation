# Runbook de Operación y Recuperación — Dominio Retail

- **Servicio**: `retail-domain-e2e` (Parent Job orquestado por Lakeflow)
- **Roles y Operación**:
  - **Operador Real del Laboratorio**: Propietario del repositorio y alumno (`becavas`).
  - **Revisor y Aprobador Independiente (Emulación CI/CD)**: Cuenta GitHub `becavas83`.
    > *Nota de Gobernanza*: Una persona operando dos cuentas representa una emulación técnica formativa y **no demuestra segregación humana real ni mínimo privilegio estricto**.
  - **Administrador de Data Platform**: Codex (autor de guías, administrador de cuenta, entitlements SCIM, WIF y destinations).
  - **Canales, Guardias y Comités Corporativos**: Marcados como **pendientes de acreditación corporativa externa** (no acreditados en este laboratorio).
- **Horario y timezone**: 02:00 `America/Lima` diario (`0 0 2 * * ?`).
- **Source cutoff**: 01:30 `America/Lima`.
- **Contrato de Fuente Diaria**:
  - Los lotes declarados ready son inmutables; cualquier corrección se publica como un **batch sucesor** documentando la relación con el lote previo.
  - *Excepción acotada de laboratorio en CERTI*: En los ejercicios de calidad y reintentos (§§21.1–21.2), el owner autoriza la republicación controlada del mismo batch únicamente después de demostrar y capturar el fallo previsto en CERTI, conservando ambos manifests (fallido y corregido) antes de la reparación operativa. Esta excepción no altera el contrato productivo PROD.
- **SLO/freshness**: Publicación Gold finalizada antes de 06:00 `America/Lima`; 99 % mensual de éxito; 0 fallos de calidad.
- **RPO/RTO**:
  - RPO: 24 horas (último lote diario válido publicado en Gold).
  - RTO: 4 horas (tiempo máximo de diagnóstico, reparación/rollback y publicación).
- **Destinos de alerta**:
  - Canal privado de Slack personal `etl-factory-alertas` en workspace ADRs del propietario con app ETL Factory Lab Alerts, conectado vía Databricks Notification Destinations (`DATABRICKS_NOTIFICATION_DESTINATION_ID`).
  - Teams corporativo es una adaptación opcional del curso; no se utiliza en esta instalación.
- **Dashboards/queries**: `ops/observability/retail_operations.sql` (Timeline Jobs, DQ metrics Silver, Freshness Gold, Lineage, Audit y Billing).

## 1. Clasificación del Incidente

| Severidad | Condición | Tiempo de Respuesta | Acciones Iniciales |
|---|---|---|---|
| **SEV-1** | Fallo total en PROD, retraso de Gold pasada la ventana de negocio (06:00) o corrupción de datos | < 15 min | Escalamiento al Administrador de Plataforma; análisis de causa raíz; decisión entre repair o rollback |
| **SEV-2** | Fallo en tarea Silver/Bronze por anomalía transitoria o archivo faltante dentro de ventana | < 30 min | Contacto con owner de la fuente; verificación de reintentos acotados o reingesta controlada |
| **SEV-3** | Alerta de duración (warning > 7 200 s) sin fallo de tareas | < 1 hora | Inspección de cuellos de botella en compute o incremento atípico de volumen |

## 2. Diagnóstico Técnico

### Jobs UI / API (Acción Inmediata)
1. Localizar la ejecución en Jobs & Pipelines o mediante Databricks CLI con perfil operador explícito:
   ```bash
   export EF_OPERATOR_PROFILE="certi-platform"
   databricks jobs get-run "$PARENT_RUN_ID" \
     --include-history --include-resolved-values \
     --profile "$EF_OPERATOR_PROFILE" --output json > /tmp/parent-run-diagnostic.json
   ```
2. Identificar la tarea o child job que originó el fallo:
   - Tareas parentales reales: `run_pedidos`, `run_clientes`, `run_productos`, `run_ventas`.
3. Descargar el output de la tarea afectada para revisar trazas de error sin exponer credenciales:
   ```bash
   databricks jobs get-run-output "$TASK_RUN_ID" \
     --profile "$EF_OPERATOR_PROFILE" --output json
   ```

### DQ / Lineage / Audit / Coste
- Consultar `retail_prod.silver.*_quality_metrics` para confirmar violaciones con acción `FAIL`.
- Ejecutar las consultas de `ops/observability/retail_operations.sql` para rastrear lineage de tablas y consumo de clusters.

## 3. Protocolos de Recuperación y Mitigación

### Repair Permitido en CERTI (§21.1)
Aplicable ante fallos deterministas corregidos en Landing:

1. **Preservar Evidencia Original**:
   Capturar el parent en un archivo exclusivo que no se sobrescriba:
   ```bash
   export EF_OPERATOR_PROFILE="certi-platform"
   export FAILED_CERTI_PARENT_RUN_ID="<run-id-parent-CERTI-fallido>"
   databricks jobs get-run "$FAILED_CERTI_PARENT_RUN_ID" \
     --include-history --include-resolved-values \
     --profile "$EF_OPERATOR_PROFILE" --output json \
     > /tmp/retail-certi-failed-original.json
   FAILED_CERTI_BATCH_ID=$(jq -er \
     '.job_parameters[] | select(.name == "batch_id") | .value' \
     /tmp/retail-certi-failed-original.json)
   ```
2. **Reingesta Independiente de Bronze (si aplica)**:
   Si la tarea Bronze de productos terminó `SUCCESS` antes de corregir Landing, reingestar exclusivamente esa Bronze desde su Job CERTI independiente antes de retomar Silver:
   ```bash
   FAILED_CERTI_PRODUCTS_TASK_RUN_ID=$(jq -er \
     '.tasks[] | select(.task_key == "run_productos" and .attempt_number == 0) | .run_id' \
     /tmp/retail-certi-failed-original.json)
   databricks jobs get-run-output "$FAILED_CERTI_PRODUCTS_TASK_RUN_ID" \
     --profile "$EF_OPERATOR_PROFILE" --output json \
     > /tmp/retail-certi-productos-failed-output.json
   FAILED_CERTI_PRODUCTS_CHILD_RUN_ID=$(jq -er '.run_job_output.run_id' \
     /tmp/retail-certi-productos-failed-output.json)
   databricks jobs get-run "$FAILED_CERTI_PRODUCTS_CHILD_RUN_ID" \
     --include-history --include-resolved-values \
     --profile "$EF_OPERATOR_PROFILE" --output json \
     > /tmp/retail-certi-productos-before-repair.json
   CERTI_PRODUCTOS_JOB_ID=$(jq -er '.job_id' \
     /tmp/retail-certi-productos-before-repair.json)
   jq -n --argjson job_id "$CERTI_PRODUCTOS_JOB_ID" \
     --arg batch_id "$FAILED_CERTI_BATCH_ID" \
     '{job_id:$job_id,job_parameters:{batch_id:$batch_id},only:["ingest_productos_bronze"]}' \
     > /tmp/retail-certi-bronze-reingestion-request.json
   databricks jobs run-now \
     --json @/tmp/retail-certi-bronze-reingestion-request.json \
     --profile "$EF_OPERATOR_PROFILE" --timeout 2h --output json \
     > /tmp/retail-certi-bronze-reingestion-run.json
   ```
3. **Reparación del Parent Job**:
   Recuperar el historial actual, reafirmar parámetros originales y `latest_repair_id`:
   ```bash
   databricks jobs get-run "$FAILED_CERTI_PARENT_RUN_ID" \
     --include-history --include-resolved-values \
     --profile "$EF_OPERATOR_PROFILE" --output json \
     > /tmp/retail-certi-before-repair.json
   jq -n --argjson run_id "$FAILED_CERTI_PARENT_RUN_ID" \
     --slurpfile original /tmp/retail-certi-failed-original.json \
     --slurpfile current /tmp/retail-certi-before-repair.json \
     '{run_id:$run_id,
       job_parameters:($original[0].job_parameters
         | map({key:.name,value:(.value // .default)}) | from_entries),
       rerun_tasks:["run_productos"],rerun_dependent_tasks:true}
      + ([$current[0].repair_history[]? | select(.type == "REPAIR")] | last
         | if . == null then {} else {latest_repair_id:.id} end)' \
     > /tmp/retail-certi-repair-request.json
   databricks jobs repair-run \
     --json @/tmp/retail-certi-repair-request.json \
     --profile "$EF_OPERATOR_PROFILE" --timeout 2h --output json \
     > /tmp/retail-certi-repair.json
   ```
4. **Verificación Downstream**:
   Comprobar con `jobs get-run --include-resolved-values` que los parámetros y outputs efectivos son los esperados, que el lineage y reconciliaciones corresponden al batch corregido, y que `run_pedidos` y `run_clientes` no tuvieron nuevos intentos ni ejecuciones adicionales.

### Caso de Fuente Ausente (§21.2)
- Cuando la ingesta falla por fuente no disponible, la tarea ejecuta exactamente un retry automático tras al menos 60 segundos.
- Si el segundo intento falla, el parent aborta sin ejecutar Silver ni Gold.
- Una vez provista la fuente, la reparación del parent reejecuta directamente `run_productos` sin reingesta independiente previa (dado que Bronze nunca completó). Se conservan los dos intentos originales y la evidencia del intento reparado.

### Backfill Permitido
- Ejecutar mediante la función nativa de Lakeflow Jobs (**Run backfill**):
  - Rango: fechas específicas (máximo 7 días por campaña de ejercicio).
  - Intervalo: 1 día.
  - Parámetro: `batch_id: {{backfill.iso_date}}`.
  - Modos: `snapshot_mode=INCREMENTAL`, `aggregate_mode=INCREMENTAL`.
  - Concurrencia: estrictamente 1 (`max_concurrent_runs: 1`), respetando el encolamiento (`queue: enabled`) para evitar carreras sobre dimensiones y agregados compartidos.

### Rollback de Código y Despliegue
- El rollback de código consiste en volver a promover una versión y wheel conocidos y aprobados:
  - Nunca ejecutar `bundle destroy` en un ambiente productivo.
  - Nunca modificar jobs manualmente desde la UI de Databricks de manera definitiva.
  - No mover ni reescribir Git tags.
  - Localizar el último promotion record exitoso y verificar integridad del wheel SHA-256 (`EF_USE_PREBUILT_WHEEL=true`).
  - Redesplegar mediante `promote-release.yml` con el SHA previo aprobado.
  - Reproducir el `bundle_scope` histórico aprobado; no recortar informalmente las unidades desplegadas.

### Compatibilidad de Schema para Rollback

| Tipo de Cambio | Decisión de Rollback |
|---|---|
| Solo código o configuración de orquestación compatible | Rollback seguro mediante promoción del release anterior con gates completos |
| Columna nullable aditiva que el código anterior ignora | Permitido tras validación en CERTI |
| Rename/delete, cambio de tipo de datos o alteración de grano/semántica | **Prohibido el rollback binario directo**. Requiere corrección hacia adelante (*forward-fix*) |
| Migración irreversible de catálogo o estado externo | Seguir procedimiento específico del producto |

### PR de Reconciliación de Main
- Todo evento de rollback operacional en un ambiente compartido exige la apertura inmediata de una Pull Request corta en `main` para sincronizar el repositorio y evitar que despliegues futuros reintroduzcan el defecto.

## 4. Recuperación de Datos (Procedimiento Externo)
- **Referencia y Owner**: La restauración de tablas Delta, Time Travel, backups físicos o Point-in-Time Recovery es potestad exclusiva de Data Platform y del Custodio de Datos mediante su procedimiento corporativo externo. La fábrica de software no altera datos directamente mediante comandos manuales no auditados.

## 5. Escalamiento y Criterios de Cierre
- **Canal de Escalamiento**:
  - Escalamiento directo a Codex (Administrador de Data Platform). Canales corporativos quedan pendientes de acreditación.
- **Criterios de Cierre de Incidente**:
  1. Parent job completado con `result_state: SUCCESS`.
  2. Tablas Gold actualizadas con el `batch_id` esperado y reconciliaciones verificadas.
  3. Cero reglas de calidad con acción `FAIL`.
  4. Bitácora de incidente completada con causa raíz, cronología, run IDs y lecciones aprendidas.
- **Evidencia y Retención**:
  - Salidas JSON de `jobs get-run` y `jobs get-run-output` almacenadas en la carpeta de auditoría de la sesión.
  - Registros de ejecución conservados por 90 días en GitHub Actions y retenidos en Databricks de acuerdo con la política de retención de system tables (365 días).

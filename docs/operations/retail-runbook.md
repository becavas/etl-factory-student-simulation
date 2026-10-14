# Runbook de Operación y Recuperación — Dominio Retail

- **Servicio**: `retail-domain-e2e` (Parent Job orquestado por Lakeflow)
- **Roles y Responsabilidades**:
  - **Propietario del Laboratorio y Administrador Responsable**: Alumno del curso (`becavas`, identidad humana `bcastillo@techdic.onmicrosoft.com`). Es el administrador responsable de la plataforma, autoriza cambios operativos y ejecuta acciones administrativas.
  - **Asistente de Plataforma y Autor de la Guía**: Codex. Mantiene la guía oficial, valida especificaciones y asiste en documentación y cambios autorizados de plataforma. Codex **no es el owner administrativo ni una persona de guardia**.
  - **Revisor y Aprobador Independiente (Emulación CI/CD)**: Cuenta GitHub `becavas83`.
    > *Nota de Gobernanza*: Una persona operando dos cuentas representa una emulación técnica formativa y **no demuestra segregación humana real ni mínimo privilegio estricto**.
  - **Canales, Guardias y Comités Corporativos**: Marcados como **pendientes de acreditación corporativa externa** (no acreditados en este laboratorio).
- **Horario y Timezone**: 02:00 `America/Lima` diario (`0 0 2 * * ?`).
- **Source Cutoff**: 01:30 `America/Lima`.
- **Contrato de Fuente Diaria**:
  - Los lotes declarados ready son inmutables; cualquier corrección se publica como un **batch sucesor** documentando la relación con el lote previo.
  - *Excepción acotada de laboratorio en CERTI*: En los ejercicios de calidad y reintentos (§§21.1–21.2), el owner autoriza la republicación controlada del mismo batch únicamente después de demostrar y capturar el fallo previsto en CERTI, conservando ambos manifests (fallido y corregido) antes de la reparación operativa. Esta excepción no altera el contrato productivo PROD.
- **SLO y Freshness**:
  - El 99 % mensual de éxito es un **objetivo de diseño (SLO target)**, no un resultado probado por un único run de laboratorio.
  - Cero violaciones de calidad no gestionadas.
  - Publicación Gold finalizada antes de 06:00 `America/Lima`.
- **RPO/RTO**:
  - RPO: 24 horas (último lote diario válido publicado en Gold).
  - RTO: 4 horas (tiempo máximo de diagnóstico, reparación/rollback y publicación).
- **Destinos de Alerta**:
  - Canal privado de Slack personal `etl-factory-alertas` en workspace ADRs del propietario con app ETL Factory Lab Alerts, conectado vía Databricks Notification Destinations (`DATABRICKS_NOTIFICATION_DESTINATION_ID`).
  - Teams corporativo es una adaptación opcional del curso; no se utiliza en esta instalación.
- **Observabilidad de Plataforma**:
  - Consultas base: `ops/observability/retail_operations.sql` (Timeline Jobs, DQ metrics Silver, Freshness Gold, Lineage, Audit y Billing).
  - Acceso verificado: El 13 de octubre de 2026, Codex comprobó lectura exitosa sobre 7 system tables (`system.lakeflow.jobs`, `job_run_timeline`, `billing.usage`, `billing.list_prices`, `access.audit`, `access.table_lineage`, `information_schema.tables`) utilizando el warehouse CERTI `e637b60e6f465fde` bajo la identidad humana del admin (`certi-platform`). El warehouse fue devuelto a estado `STOPPED`. Este acceso pertenece al administrador humano comprobado; no está atribuido a runtime SPs ni a evaluadores externos.

## 1. Clasificación del Incidente

| Severidad | Condición | Tiempo de Respuesta | Acciones Iniciales |
|---|---|---|---|
| **SEV-1** | Fallo total en PROD, retraso de Gold pasada la ventana de negocio (06:00) o corrupción de datos | < 15 min | Escalamiento al Propietario del Laboratorio; análisis de causa raíz; decisión entre repair o rollback |
| **SEV-2** | Fallo en tarea Silver/Bronze por anomalía transitoria o archivo faltante dentro de ventana | < 30 min | Contacto con owner de la fuente; verificación de reintentos acotados o reingesta controlada |
| **SEV-3** | Alerta de duración (warning > 7 200 s) sin fallo de tareas | < 1 hora | Inspección de cuellos de botella en compute o incremento atípico de volumen |

## 2. Diagnóstico Técnico por Ambiente

### Coherencia de Perfiles, Workspaces y Catálogos
Es imperativo mantener total coherencia entre el perfil utilizado, el workspace de Databricks y el catálogo de datos. Un perfil CERTI nunca debe consultar el catálogo productivo `retail_prod`.

- **Diagnóstico en CERTI**:
  - Host: `https://adb-7405611412963889.9.azuredatabricks.net`
  - Perfil de operador: `export EF_OPERATOR_PROFILE="certi-platform"`
  - Catálogo: `retail_certi`
  - Compute: SQL Warehouse CERTI `e637b60e6f465fde`
- **Diagnóstico en PROD**:
  - Host: `https://adb-7405609727000776.16.azuredatabricks.net`
  - Perfil de operador: `export EF_OPERATOR_PROFILE="fuentes_prod"` (o perfil operador PROD autorizado)
  - Catálogo: `retail_prod`
  - Compute: SQL Warehouse PROD `8ed402583b098853` (debe verificarse estado inicial, iniciarse solo para lecturas autorizadas y apagarse al finalizar)

### Distinción Fundamental de Identidades
Un repair o reingesta operativa se invoca mediante el acceso OAuth personal del operador humano autorizado (`CAN_MANAGE_RUN`). Sin embargo, los Databricks Jobs continúan procesando bajo la identidad configurada `run_as` de su Service Principal de runtime (`etl-factory-certi-runtime` o `etl-factory-prod-runtime`). Una acción operativa de reparación **no representa un despliegue personal ni modifica los entitlements de runtime**.

### Diagnóstico de Ejecución
1. Localizar la ejecución en Jobs & Pipelines o mediante Databricks CLI con perfil de operador explícito:
   ```bash
   set -euo pipefail
   export EF_OPERATOR_PROFILE="certi-platform"
   databricks auth describe --profile "$EF_OPERATOR_PROFILE"
   databricks current-user me --profile "$EF_OPERATOR_PROFILE" --output json
   databricks jobs get-run "$PARENT_RUN_ID" \
     --include-history --include-resolved-values \
     --profile "$EF_OPERATOR_PROFILE" --output json > /tmp/parent-run-diagnostic.json
   ```
2. Identificar la tarea o child job que originó el fallo:
   - Tareas parentales reales: `run_pedidos`, `run_clientes`, `run_productos`, `run_ventas`.
3. Descargar el output de la tarea afectada para revisar trazas de error sin exponer secretos:
   ```bash
   set -euo pipefail
   databricks jobs get-run-output "$TASK_RUN_ID" \
     --profile "$EF_OPERATOR_PROFILE" --output json
   ```

## 3. Protocolos de Recuperación y Mitigación

Todos los bloques de recuperación deben ejecutarse con `set -euo pipefail` para detenerse de forma inmediata ante cualquier fallo o ausencia de variable.

### A. Incidente de Calidad en CERTI (§21.1)
Aplicable ante fallos deterministas corregidos en Landing (`release_negative_20260815_002`):

1. **Preservar Evidencia Original con Protección contra Sobrescritura**:
   Capturar el parent en un archivo exclusivo que no se sobrescriba (`set -o noclobber`):
   ```bash
   set -euo pipefail
   export EF_OPERATOR_PROFILE="certi-platform"
   export FAILED_CERTI_PARENT_RUN_ID="<run-id-parent-CERTI-fallido>"
   databricks auth describe --profile "$EF_OPERATOR_PROFILE"
   databricks current-user me --profile "$EF_OPERATOR_PROFILE" --output json
   (
     set -o noclobber
     databricks jobs get-run "$FAILED_CERTI_PARENT_RUN_ID" \
       --include-history --include-resolved-values \
       --profile "$EF_OPERATOR_PROFILE" --output json \
       > /tmp/retail-certi-failed-original.json
   )
   FAILED_CERTI_BATCH_ID=$(jq -er \
     '.job_parameters[] | select(.name == "batch_id") | .value' \
     /tmp/retail-certi-failed-original.json)
   test "$FAILED_CERTI_BATCH_ID" = 'release_negative_20260815_002'
   ```
   > *Regla de preservación*: Si `/tmp/retail-certi-failed-original.json` ya existe, la captura falla sin destruirlo. Se debe inspeccionar y validar que coincida con el workspace, run y batch antes de reutilizarlo; **nunca borrarlo para repetir el bloque**.

2. **Reingesta Independiente de Bronze (Obligatoria cuando Bronze completó SUCCESS)**:
   Si la Bronze de productos terminó `SUCCESS` antes de corregir Landing, reingestar exclusivamente esa Bronze desde su Job CERTI independiente antes de retomar Silver:
   ```bash
   set -euo pipefail
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
   > *Punto de detención*: Verificar que Bronze terminó en `SUCCESS`, Silver no se ejecutó en este run independiente, se cargaron los 2 productos/2 categorías del manifest corregido y existe lineage del batch. **Si falla, detenerse inmediatamente; no invocar repair.**

3. **Reparación del Parent Job con Validación de Parámetros**:
   Recuperar el historial actual, mantener `latest_repair_id` y validar que los parámetros `INCREMENTAL` se preserven:
   ```bash
   set -euo pipefail
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
   jq -e --arg batch "$FAILED_CERTI_BATCH_ID" \
     '.job_parameters.batch_id == $batch
      and .job_parameters.snapshot_mode == "INCREMENTAL"
      and .job_parameters.aggregate_mode == "INCREMENTAL"' \
     /tmp/retail-certi-repair-request.json
   databricks jobs repair-run \
     --json @/tmp/retail-certi-repair-request.json \
     --profile "$EF_OPERATOR_PROFILE" --timeout 2h --output json \
     > /tmp/retail-certi-repair.json
   ```
   > *Control*: Si `jq -e` falla o falta un parámetro, la ejecución se interrumpe y no se envía la solicitud.

4. **Verificación Downstream Completa**:
   Verificar individualmente cada tarea Silver de productos y Silver/Gold de ventas con `jobs get-run --include-resolved-values` y `jobs get-run-output`. Comprobar outputs efectivos, lineage, reconciliación del batch corregido y confirmar que `run_pedidos` y `run_clientes` no tuvieron nuevas ejecuciones ni attempts adicionales. El estado parent `SUCCESS` por sí solo no acredita el cierre.

### B. Incidente de Fuente Ausente en CERTI (§21.2)
Aplicable al escenario de fallo de ingesta por fuente no disponible (`release_missing_20260815_003`):

1. **Captura Exclusiva y Distinta**:
   Utilizar una ruta exclusiva que no interfiera con la del caso de calidad:
   ```bash
   set -euo pipefail
   export EF_OPERATOR_PROFILE="certi-platform"
   export FAILED_CERTI_MISSING_RUN_ID="<run-id-parent-CERTI-fuente-ausente>"
   (
     set -o noclobber
     databricks jobs get-run "$FAILED_CERTI_MISSING_RUN_ID" \
       --include-history --include-resolved-values \
       --profile "$EF_OPERATOR_PROFILE" --output json \
       > /tmp/retail-certi-missing-source-failed-original.json
   )
   ```
2. **Sin Reingesta Previa de Bronze**:
   En este caso Bronze terminó en `FAILED` en ambos reintentos; por lo tanto, **no se requiere la reingesta previa independiente**. La reparación del parent reejecutará Bronze de manera natural.
3. **Reparación del Parent**:
   Una vez que el owner de fuentes repone el archivo en Landing, se genera el request reafirmando los parámetros originales (`release_missing_20260815_003`), `rerun_tasks: ["run_productos"]` y `rerun_dependent_tasks: true`, validando con `jq -e` antes de invocar `repair-run`.
4. **Verificación de Retry y Reconciliación**:
   Comprobar que en el run original se registraron exactamente 2 intentos (intento inicial y 1 retry tras >= 60 s de intervalo entre inicios), y verificar parámetros/outputs del intento reparado y ausencia de reejecución en pedidos/clientes.

### C. Modalidad Acotada: Ciclo PAUSED → UNPAUSED → PAUSED en PROD
Para la prueba programada de laboratorio en PROD:
1. **Estado Inicial**: Ambos ambientes (CERTI y PROD) permanecen desplegados con schedule `PAUSED` por control operativo.
2. **Preparación de Fuente Sintética**: El alumno genera y publica el paquete sintético controlado para la fecha de prueba (`seed_labs.py --catalog retail_prod --scenario scheduled --batch <fecha-ISO>`), asegurando 5 CSVs coherentes y 73.50 PEN antes del cutoff (01:30 Lima).
3. **Activación vía Código**: Se promueve una Pull Request que cambia exclusivamente el estado de PROD a `UNPAUSED` (CERTI permanece `PAUSED`).
4. **Disparo Nativo**: El parent se inicia automáticamente por el scheduler a las 02:00 Lima (`trigger=PERIODIC` en API, `trigger_type=CRON` en `system.lakeflow.job_run_timeline`).
5. **Verificación**: Validación de Gold, 73.50 PEN, lineage y terminación antes de 06:00 Lima.
6. **Pausa vía Código**: Inmediatamente tras verificar la prueba, se abre, aprueba y promueve la Pull Request que devuelve PROD a `PAUSED` antes del siguiente ciclo diario.

### D. Backfill Permitido
- Ejecutar mediante la función nativa de Lakeflow Jobs (**Run backfill**):
  - Rango acotado: máximo 7 días por campaña de ejercicio.
  - Intervalo: 1 día.
  - Parámetro: `batch_id: {{backfill.iso_date}}`.
  - Modos: `snapshot_mode=INCREMENTAL`, `aggregate_mode=INCREMENTAL`.
  - Concurrencia: 1 (`max_concurrent_runs: 1`) con encolamiento (`queue: enabled`).

### E. Rollback de Código y Despliegue
- Rollback significa volver a promover una versión y wheel preexistentes y aprobados:
  - Prohibido ejecutar `bundle destroy` en ambientes compartidos.
  - Prohibido modificar jobs manualmente desde la UI o mover Git tags.
  - Localizar el promotion record anterior y verificar checksum (`EF_USE_PREBUILT_WHEEL=true`).
  - Redesplegar mediante `promote-release.yml` con el SHA previo y el scope completo de las 5 raíces (`clientes`, `pedidos`, `productos`, `ventas`, `orchestration`).
  - Abrir de inmediato la PR de reconciliación en `main`.

## 4. Recuperación de Datos (Procedimiento Externo)
La restauración de tablas Delta, Time Travel, backups físicos o Point-in-Time Recovery es potestad exclusiva de Data Platform y del Custodio de Datos mediante su procedimiento externo. La fábrica de software no altera datos directamente mediante comandos manuales no auditados.

## 5. Escalamiento y Criterios de Cierre

- **Canal de Escalamiento**:
  - Escalamiento administrativo al **Propietario del Laboratorio** (`becavas`).
  - Consultas y contrastes técnicos de especificación con **Codex** (asistente de plataforma/guía).
  - Canales corporativos continúan pendientes de acreditación.
- **Criterios de Cierre de Incidente**:
  1. Parent job completado con `result_state: SUCCESS`.
  2. Tablas Gold actualizadas con el `batch_id` esperado y reconciliaciones verificadas.
  3. Cero reglas de calidad con acción `FAIL`.
  4. Bitácora de incidente completada con causa raíz, cronología, run IDs y lecciones aprendidas.
- **Evidencia y Retención**:
  - Salidas JSON y diagnósticos conservados en la bitácora de auditoría de la sesión (`etl-factory-course-audit/sesion-4`).
  - Registros de workflow y artifacts en GitHub Actions: La retención efectiva para este repositorio específico permanece **pendiente de acreditación/verificación documental** (el valor nominal por defecto de hasta 90 días no sustituye la inspección de la configuración efectiva o volcado de API de la organización/cuenta).
  - Registros y logs en Databricks: La política formal de retención de system tables (ej. 365 días) y logs de compute permanece igualmente **pendiente de verificación/acreditación documental**.

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
- **Definición y Principios**:
  - Rollback significa volver a promover una versión y wheel preexistentes y previamente aprobados.
  - Prohibido ejecutar `bundle destroy` en ambientes compartidos.
  - Prohibido modificar jobs manualmente desde la UI o mover/eliminar Git tags.
  - Localizar el promotion record anterior y verificar el checksum inmutable del wheel (`EF_USE_PREBUILT_WHEEL=true`).

- **Control de Destino Operativo (`deployment_goal`)**:
  - `certi_only`: **Obligatorio para simulaciones, ejercicios formativos, dry-runs y pruebas de regresión controladas**. Garantiza que `deploy-prod` sea omitido inmediatamente (`deploy-prod=skipped` en 0 s), sin requerir aprobaciones humanas del entorno PROD ni alterar jobs, clusters, schedules, tags o parámetros de producción.
  - `certi_and_prod`: **Estrictamente reservado para contingencias e incidentes reales autorizados en producción**. Requiere validación satisfactoria previa de smoke tests en CERTI y aprobación explícita humana en el environment gate de PROD (`becavas83`).

- **Reglas Estrictas de Scope y Granularidad**:
  - El redeploy respeta con exactitud el `bundle_scope` registrado en el promotion record del artefacto DEV recuperado. Si la evidencia histórica abarca las 5 raíces (`clientes`, `pedidos`, `productos`, `ventas`, `orchestration`), el rollback debe promover ese scope transversal completo; queda prohibido recortar raíces informalmente para forzar un rollback parcial por capability.
  - Cuando se requiera revertir exclusivamente una capability específica manteniendo el resto del inventario, se debe formular una PR hacia adelante (forward fix) desde `main`.

- **Matriz de Compatibilidad de Schema**:
  Antes de autorizar la promoción del release anterior, se debe clasificar el impacto:
  | Naturaleza del Cambio | Decisión Operativa | Acción Requerida |
  |---|---|---|
  | Solo código o configuración compatible | Release anterior elegible | Promover mediante gates normales |
  | Columna nullable aditiva que el código anterior ignora | Release anterior elegible previa verificación | Validar mediante test suite y plan de despliegue |
  | Rename/drop de columna, cambio de tipo de dato o grano | Incompatible para rollback retrospectivo | Escalar de inmediato; prohibido rollback retrospectivo; preparar corrección hacia delante |
  | Migración irreversible de catálogo o mutación externa | Incompatible | Ejecutar procedimiento específico de contingencia |

- **Inviolabilidad de Tags y Verificación de Assets**:
  - Los tags namespaced (`retail/<unidad>/v*`) están protegidos contra sobreescritura y borrado accidental por el Ruleset de GitHub `etl-factory-release-tags-immutable` (ID `25029202`).
  - La integridad de los assets de release (`promotion-record.json`) se audita mediante verificación criptográfica de hash SHA-256 (digest `fd32fd20cc00719001825c1254ba01ff32d95b195d3d492707af2824872a28b8`), reconociendo que el flag de API `immutable=false` no impide por sí mismo la sustitución sin el control del ruleset y el hash.

- **Reconciliación Inmediata de `main`**:
  Tras completar el rollback y validar el servicio en Databricks, el operador debe abrir de inmediato una Pull Request de reconciliación en la rama `main` del repositorio para asegurar que el próximo despliegue no reintroduzca el defecto revertido.

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
- **Evidencia y Retención de Plataforma**:
  - **Confirmación Administrativa de la Cuenta (18 de octubre de 2026)**:
    - El propietario de la cuenta (`becavas`) confirmó formalmente que la funcionalidad *Account Console → Previews → System Tables Configurable Retention* **no está habilitada** (`enabled: false`).
    - En consecuencia, el default corporativo de 395 días de la retención configurable no aplica a este entorno; rige la política estándar específica por cada tabla del sistema.
    - La existencia de una ventana formal no presupone la presencia de registros para todo el período ni reemplaza las garantías de recuperación ante desastre.

  - **Matriz de Políticas de Retención por Recurso**:
    | Recurso / Sistema | Política de Retención | Fuente Oficial y Verificación | Custodio / Owner | Calificación y Reglas Operativas |
    |---|---|---|---|---|
    | `system.lakeflow.jobs` | 365 días | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Histórico de cambios en definiciones de Jobs; el **último registro por entidad se conserva indefinidamente** aun si excede la ventana |
    | `system.lakeflow.job_run_timeline` | 365 días | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Registro de ejecuciones segmentado por slices temporales; requiere agregación por `run_id` |
    | `system.billing.usage` | 365 días | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Registro de consumo medido por SKU y atribuible por `job_id` y `job_run_id` |
    | `system.access.audit` | 365 días | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Registro de auditoría de llamadas de API y eventos de control de acceso |
    | `system.access.table_lineage` | 365 días | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Trazabilidad y dependencias entre tablas y jobs de runtime |
    | `system.billing.list_prices` | Indefinida | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Listas de precios oficiales vigentes en la plataforma |
    | `system.information_schema.tables` | Sin ventana histórica de eventos | Doc oficial Databricks (2026-10-18) | `becavas` (`bcastillo@techdic.onmicrosoft.com`) | Describe metadata viva del catálogo y filtra dinámicamente según privilegios del llamador |
    | GitHub Actions (runs, logs, checks) | 90 días | Configuración de repositorio verificada (2026-10-17) | `becavas` / `becavas83` | Retención de historial de workflows, logs de CI/CD y checks |
    | GitHub Build Artifacts (`build-artifact`) | 1 día | Workflow `deploy-dev.yml` (2026-10-17) | `becavas` / `becavas83` | Artefacto temporal para transferencia entre jobs del pipeline de despliegue DEV |
    | GitHub Release Assets (`promotion-record.json`) | 90 días (vence 2027-01-15) | Releases API inspeccionada (2026-10-17) | `becavas` / `becavas83` | Vinculados a releases publicadas; integridad auditada por digest SHA-256 |
    | Evidencia y Bitácora de Auditoría Privada | Permanente | Auditoría local (2026-10-18) | Antigravity / Alumno | Conservada en `etl-factory-course-audit/sesion-4/` |

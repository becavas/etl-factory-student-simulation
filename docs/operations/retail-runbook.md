# Runbook de Operación y Recuperación — Dominio Retail

- **Servicio**: `retail-domain-e2e` (Parent Job orquestado)
- **Owners y rotación**:
  - Plataforma: Data Platform (`#data-platform-soporte`)
  - Dominio y Reglas Funcionales: Data Owner / Retail Engineering Lead
  - Gobierno de Datos: Data Governance
  - Operación: Guardia de Operaciones / Grupo operador (`admins`)
- **Horario y timezone**: 02:00 `America/Lima` diario (`0 0 2 * * ?`)
- **Source cutoff**: 01:30 `America/Lima` (las tres fuentes completas y validadas)
- **SLO/freshness**: Publicación Gold finalizada antes de 06:00 `America/Lima`; 99 % mensual de éxito; 0 fallos de calidad
- **RPO/RTO**:
  - RPO: 24 horas (último lote diario válido)
  - RTO: 4 horas (tiempo máximo de diagnóstico, reparación/rollback y publicación)
- **Destinos de alerta**:
  - Webhook corporativo administrado vía Databricks Notification Destination ID (`DATABRICKS_NOTIFICATION_DESTINATION_ID`)
  - Alternativa de laboratorio: buzón autorizado de guardia (`DATABRICKS_NOTIFICATION_EMAIL`)
- **Dashboards/queries**: `ops/observability/retail_operations.sql` (Timeline Jobs, DQ metrics, Freshness Gold, Lineage, Audit y Billing)

## 1. Clasificación del Incidente

| Severidad | Condición | Tiempo de Respuesta | Acciones Iniciales |
|---|---|---|---|
| **SEV-1** | Fallo total en PROD, corrupción de datos, retraso de Gold pasada la ventana de negocio (06:00) | < 15 min | Escalamiento inmediato a Data Platform y Data Owner; análisis de causa raíz; decisión entre repair o rollback |
| **SEV-2** | Fallo en tarea Silver/Bronze por anomalía transitoria o archivo faltante dentro de ventana | < 30 min | Contacto con owner de la fuente; reintento acotado o reingesta controlada |
| **SEV-3** | Alerta de duración (warning > 7 200 s) sin fallo de tareas | < 1 hora | Inspección de cuellos de botella en compute o incremento de volumetría |

## 2. Diagnóstico Técnico

### Jobs UI / API (Acción Inmediata)
1. Localizar la ejecución fallida en Jobs & Pipelines o mediante Databricks CLI:
   ```bash
   databricks jobs get-run <PARENT_RUN_ID> --include-history --include-resolved-values --output json
   ```
2. Identificar la tarea o child job que originó el fallo (`run_pedidos`, `run_clientes`, `run_productos`, `run_ventas`).
3. Descargar el output de la tarea afectada para revisar trazas de error sin exponer tokens:
   ```bash
   databricks jobs get-run-output <TASK_RUN_ID> --output json
   ```

### DQ / Lineage / Audit / Coste
- Consultar `retail_prod.silver.*_quality_metrics` para confirmar si el fallo proviene de violaciones con acción `FAIL`.
- Ejecutar las consultas de `ops/observability/retail_operations.sql` para rastrear lineage de tablas afectadas y uso de clusters.

## 3. Protocolos de Recuperación y Mitigación

### Repair Permitido
- **Fallo de calidad determinista corregido en Landing**:
  1. Si la tarea Bronze ya terminó `SUCCESS`, reingestar exclusivamente Bronze desde su job child independiente con el nuevo paquete corregido.
  2. Disparar `jobs repair-run` sobre el parent job reafirmando los parámetros originales (`batch_id`, `snapshot_mode=INCREMENTAL`, `aggregate_mode=INCREMENTAL`) y `latest_repair_id` si aplica.
  3. Comprobar que tareas no afectadas no se repitan innecesariamente.
- **Fallo por fuente ausente**:
  1. Cuando la fuente sea provista por su productor, ejecutar `repair-run` sobre el parent seleccionando la tarea de ingesta fallida y dependientes.

### Backfill Permitido
- Ejecutar mediante la funcionalidad nativa de Lakeflow Jobs (**Run backfill**):
  - Rango: fechas específicas (máximo 7 días por campaña en ejercicios controlados).
  - Intervalo: 1 día.
  - Parámetro: `batch_id: {{backfill.iso_date}}`.
  - Concurrencia: estrictamente 1 (`max_concurrent_runs: 1`), respetando queue y consistencia en dimensiones compartidas.

### Rollback de Código y Despliegue
- El rollback de código consiste en volver a promover una versión y wheel conocidos y aprobados:
  - Nunca ejecutar `bundle destroy` en un ambiente productivo.
  - Nunca modificar jobs manualmente desde la UI de Databricks de manera definitiva.
  - No mover ni reescribir Git tags.
  - Localizar el último promotion record exitoso y verificar integridad del wheel SHA-256 (`EF_USE_PREBUILT_WHEEL=true`).
  - Redesplegar mediante `promote-release.yml` con el SHA previo aprobado.

### Compatibilidad de Schema para Rollback

| Tipo de Cambio | Decisión de Rollback |
|---|---|
| Solo lógica de código o configuración de orquestación | Rollback seguro mediante promoción del release anterior con gates completos |
| Cambio de schema con columna nullable aditiva ignorada por versión anterior | Permitido tras validación en CERTI |
| Eliminación de columnas, renombrado, cambio de tipo de datos o alteración de grano | **Prohibido el rollback binario directo**. Requiere corrección hacia adelante (*forward-fix*) |
| Migración irreversible de catálogo o estado externo | Seguir procedimiento específico corporativo de Data Platform |

### PR de Reconciliación de Main
- Todo evento de rollback operacional en un ambiente compartido exige la apertura inmediata de una Pull Request corta en `main` para sincronizar el repositorio y evitar que despliegues futuros reintroduzcan la versión defectuosa.

## 4. Recuperación de Datos (Procedimiento Externo)
- **Referencia y Owner**: La restauración de tablas Delta, Time Travel, backups físicos o Point-in-Time Recovery es potestad exclusiva de Data Platform y del Custodio de Datos mediante su procedimiento externo corporativo de Recuperación ante Desastres (DR). La fábrica de software no altera datos directamente mediante comandos manuales no auditados.

## 5. Escalamiento y Criterios de Cierre
- **Canales de Escalamiento**:
  - Data Platform: Slack `#data-platform-soporte`
  - Incidencias de Producción: Canal de guardia P1/P2
- **Criterios de Cierre de Incidente**:
  1. Parent job completado con `result_state: SUCCESS`.
  2. Tablas Gold actualizadas con el `batch_id` esperado y reconciliaciones verificadas.
  3. Cero reglas de calidad con acción `FAIL`.
  4. Bitácora de incidente completada con causa raíz, cronología, run IDs y lecciones aprendidas.
- **Evidencia y Retención**:
  - Salidas JSON de `jobs get-run` y `jobs get-run-output` almacenadas en la carpeta de auditoría del ciclo.
  - Registros de ejecución conservados por 90 días en GitHub Actions y retenidos en Databricks de acuerdo con la política de retención de system tables (365 días).

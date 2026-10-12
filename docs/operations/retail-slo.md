# Objetivos Operativos del Dominio Retail (SLO)

Este documento define los objetivos de nivel de servicio (SLO), recuperación y disponibilidad para el servicio de datos orquestado `retail-domain-e2e` en el ambiente productivo (`PROD`).

## 1. Objetivos Operativos Iniciales

| Objetivo | Valor inicial del curso | Evidencia |
|---|---:|---|
| schedule | 02:00 `America/Lima` diario | Bundle summary / Lakeflow schedule |
| source cutoff | 01:30 `America/Lima` | contrato del productor / landing metadata |
| advertencia de duración PROD | 2 horas (7 200 s) | health event + notification destination |
| timeout total | 4 horas (14 400 s) | configuración del parent Job y result state |
| freshness | batch del día publicado antes de 06:00 `America/Lima` | run timestamp + query Gold |
| ejecución exitosa | 99 % mensual, excluyendo ventanas aprobadas | job run timeline en system tables |
| calidad obligatoria | cero reglas `FAIL` violadas | tablas de métricas DQ en Silver |
| RPO inicial | 24 horas | último batch diario válido publicado en Gold |
| RTO inicial | 4 horas | cronología del ejercicio y runbook de recuperación |

> **Nota de Gobernanza**: Estos valores representan los objetivos iniciales del caso formativo y de operación de plataforma. Un SLA contractual formal con consecuencias de negocio requiere aprobación explícita de Data Governance, Data Owner del dominio, soporte 24/7 y validación con volumetría real.

## 2. Diferenciación de Tiempos Críticos

Para evitar interpretaciones ambiguas en el cálculo de métricas operativas y trazabilidad de lotes:

- **Trigger time (`{{job.trigger.time.iso_date}}`)**: Momento en que el planificador de Lakeflow Jobs dispara la ejecución. La fábrica lo toma como el identificador determinista del `batch_id` diario en UTC (a las 02:00 de Lima, la fecha UTC coincide con la fecha local de negocio).
- **Start time**: Momento exacto en que las tareas del Job inician procesamiento activo en el compute asignado (puede presentar latencia debido al aprovisionamiento de nodos o encolamiento en cola).
- **Business date**: Fecha de negocio que procesa el pipeline ETL, parametrizada explícitamente mediante `batch_id=YYYY-MM-DD`.

## 3. Límites de Ejecución y Concurrencia

- **Concurrencia máxima**: 1 run concurrente tanto a nivel parent como a nivel de cada child Job, protegiendo las dimensiones compartidas y la consistencia de hechos y KPIs.
- **Encolamiento (Queue)**: Activado (`enabled: true`) en el parent Job para no perder ejecuciones en caso de solapamiento operacional o durante campañas de backfill.
- **Política de Retries**:
  - Ingesta Bronze idempotente: 1 reintento automático con intervalo mínimo de 60 segundos, cubriendo anomalías transitorias de red o compute.
  - Tareas Silver, Gold y DQ: 0 reintentos automáticos (las violaciones de integridad o fallos deterministas requieren análisis y reparación gobernada).
  - Tareas child del parent: 0 reintentos automáticos para evitar duplicidad de invocaciones.

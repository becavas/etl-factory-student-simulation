# Instancia de Deprecación: retail_sbx_a001.silver.clientes_governance_lab

Este documento registra la instancia concreta del checklist de deprecación para el activo de laboratorio de Fase 15 (§25).

> [!NOTE]
> Conforme al principio de rigor y no invención de políticas corporativas, los requisitos de retención, custodia legal y comités formales no acreditados permanecen expresamente como **pendientes** (`[ ]`). Por tanto, esta instancia de laboratorio permanece **incompleta** y no autoriza el retiro ni borrado físico del activo.

---

## 1. Identidad del Activo

- Capability afectada: `clientes`
- Tablas y recursos gobernados involucrados: `retail_sbx_a001.silver.clientes_governance_lab` (tipo `MANAGED_SHALLOW_CLONE`)
- Jobs y workflows asociados: Ninguno (creado interactivamente para validación de gobernanza y metadata)
- Technical Owner: `becavas` (Data Engineering Retail)
- Data Owner: `bcastillo@techdic.onmicrosoft.com` / `becavas` (Simulación aprobada de laboratorio; ref: `docs/platform-dependencies.md`)
- Estado actual: `deprecated` (transicionado en Fase 15 §18/§25; tag `lifecycle='deprecated'`)
- Estado propuesto: `retired`
- Fecha efectiva del cambio: `2026-10-21` (fecha de deprecación)
- Fecha de retiro simulada: `2026-11-20` (referenciada en el comentario de tabla y evidencia de ejercicio)
- Activo de reemplazo recomendado: `retail_sbx_a001.silver.clientes_curated`
- Release / commit Git que formaliza la decisión: Commit del baseline de gobierno en PR #33

---

## 2. Consumidores y Dependencias Downstream

- [x] Lineage de Unity Catalog consultado y verificado (sin dependencias downstream activas hacia este activo de prueba).
- [x] Activo de reemplazo definido y validado: `retail_sbx_a001.silver.clientes_curated`.
- [ ] Consumidores identificados y confirmación formal recibida (pendiente de comité corporativo).
- [ ] Período de gracia y fecha límite formalmente comunicados a la organización.

---

## 3. Controles Operativos

- [x] Schedule del Job padre: Inactivo / no aplica (activo sintético de laboratorio sin Job programado).
- [x] Monitoreo y alertas operacionales: No configuradas para esta tabla sintética.
- [x] Preservación de datos fuente: Tabla curada original `clientes_curated` verificada intacta antes y después (13 filas).
- [ ] Runbook operacional actualizado con procedimiento de retiro definitivo (pendiente).

---

## 4. Datos y Políticas de Retención

- [x] Tipo de almacenamiento Delta verificado: `MANAGED_SHALLOW_CLONE` sobre storage de sandbox.
- [x] **Prohibición de Borrado Prematuro**: Se prohíbe taxativamente la ejecución de `DROP TABLE` o `VACUUM` sobre este activo durante la evaluación.
- [ ] Política de retención corporativa identificada e informada formalmente (pendiente: no inventar política no aprobada).
- [ ] Legal hold y procedimiento corporativo de custodia acreditados (pendiente: excepción de laboratorio).

---

## 5. Cierre y Aprobación

- [ ] Bloqueo de acceso en catálogo/esquema implementado (pendiente).
- [ ] Dependencias downstream formalmente migradas (pendiente).
- [x] Evidencia de auditoría y ejecución de laboratorio conservada en bitácora de Fase 15 (`etl-factory-course-audit/sesion-4/`).
- [ ] Aprobación formal corporativa del retiro (pendiente de finalización de Fase 15).

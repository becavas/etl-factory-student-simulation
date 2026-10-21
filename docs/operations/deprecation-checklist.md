# Checklist de deprecación de una capability

Este checklist establece los controles obligatorios para transicionar una capability o tabla a estado `deprecated` o `retired`. Ningún activo puede ser retirado o eliminado físicamente sin completar estas verificaciones.

---

## 1. Identidad del Activo

- Capability afectada:
- Tablas y recursos gobernados involucrados:
- Jobs y workflows asociados:
- Technical Owner: `becavas` (Data Engineering Retail)
- Data Owner: `becavas` (Simulación aprobada de laboratorio; ref: `docs/platform-dependencies.md`)
- Estado actual:
- Estado propuesto (`deprecated` / `retired`):
- Fecha efectiva del cambio:
- Release / commit Git que formaliza la decisión:

---

## 2. Consumidores y Dependencias Downstream

- [ ] Lineage de Unity Catalog consultado y verificado (adjuntar timestamp y consulta).
- [ ] Consumidores identificados (pipelines internos, modelos analíticos o usuarios de consulta).
- [ ] Notificación y confirmación formal por parte de los owners de las capabilities consumidoras.
- [ ] Activo de reemplazo definido y validado (especificar tabla/versión sucesora).
- [ ] Período de gracia y fecha límite de transición comunicados a los consumidores.

---

## 3. Controles Operativos

- [ ] Schedule del Job padre / tasks pausado formalmente mediante Pull Request aprobada en `main`.
- [ ] Alertas, health rules y monitoreo operacional actualizados o desactivados según corresponda.
- [ ] Runbook operacional actualizado con el estado de deprecación y rutas de diagnóstico.
- [ ] Preservación histórica de la última ejecución válida y del último batch procesado exitosamente.

---

## 4. Datos y Políticas de Retención

- [ ] Política de retención identificada y contrastada con `docs/operations/retail-runbook.md` (§5).
- [ ] Procedimiento corporativo de custodia, legal hold y recuperación ante desastre referenciado formalmente.
- [ ] Tipo de almacenamiento Delta (Managed / External) y comportamiento de conservación verificado.
- [ ] **Prohibición de Borrado Prematuro**: El cambio de tag o estado a `deprecated` o `retired` **no autoriza** la ejecución de comandos `DROP TABLE`, `VACUUM` ni la eliminación de almacenamiento subyacente.

---

## 5. Cierre y Aprobación

- [ ] Bloqueo de acceso para nuevos consumidores configurado a nivel de catálogo/esquema.
- [ ] Dependencias downstream completamente desacopladas o migradas al activo sucesor.
- [ ] Evidencia de auditoría y bitácora conservadas en el repositorio.
- [ ] Aprobación formal del Data Owner y Code Owner registrada en la Pull Request de cierre.

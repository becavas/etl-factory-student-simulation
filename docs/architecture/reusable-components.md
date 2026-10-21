# Componentes Reutilizables de la Fábrica ETL

Este documento consolida el inventario formal de componentes compartidos desarrollados y mantenidos en el repositorio para acelerar la creación de nuevas capacidades y garantizar consistencia operativa, organizados en tres categorías fundamentales.

---

## 1. Runtime Compartido

El **runtime compartido** proporciona las primitivas de ejecución y utilidades comunes empaquetadas en la librería base de la plataforma:

- `src/enterprise_fabric/`:
  - `capability_names.py`: Validación y normalización canónica de identificadores de capabilities del dominio.
  - `cli.py`: Entrypoint ejecutado por Databricks Jobs que emite evidencia en formato JSON de la ejecución del wheel instalado en el cluster (distribución, versión, ruta del módulo y validación de capability), sin actuar como despachador de pipelines ETL.
- `src/enterprise_fabric/shared/`:
  - `spark.py`: Primitivas funcionales para transformaciones Spark, incluyendo `normalized_text` (limpieza de espacios y conversión de strings vacíos a nulos) y `deterministic_latest` (deduplicación determinista por claves y recencia preservando claves incompletas para evaluación de reglas de calidad). La inicialización y gestión de la sesión Spark es delegada al runtime de Databricks o a fixtures locales de prueba.
  - `delta.py`: Primitiva de publicación atómica `replace_where_value` sobre tablas Delta utilizando el predicado selectivo `replaceWhere` y registrando metadatos de auditoría explícitos mediante `userMetadata`.
  - `identifiers.py`: Validación estricta de cadenas de identificación (`require_safe_value`) mediante expresiones regulares para garantizar valores seguros en rutas, nombres, predicados y metadatos de ejecución.

---

## 2. Tooling de Desarrollo

El **tooling de desarrollo** automatiza la generación de recursos estandarizados y elimina configuraciones manuales propensas a errores:

- `tools/bundle_generator/`:
  - Generador automatizado de especificaciones de Lakeflow Jobs a recursos Databricks Asset Bundles (`resources/jobs.generated.yml`).
  - Aplica políticas de compute corporativas, health rules, umbrales de alerta y variables de entorno a partir de contratos declarativos `specs/jobs.yml`.
  - Proporciona validación estática del esquema con `python -m tools.bundle_generator generate --all --check`.

---

## 3. Controles de Entrega

Los **controles de entrega** gobiernan la integración y despliegue continuo (CI/CD) para garantizar trazabilidad, aislamiento e inmutabilidad en todos los ambientes:

- `scripts/affected_bundles.py`:
  - Selector determinista de Bundles afectados por cambios en el repositorio.
  - Soporta filtrado explícito con `--target <target>` (ej. `dev`) para aislar capabilities exclusivas de sandbox frente a despliegues en DEV.
- `scripts/inspect_wheel.py`:
  - Inspección del contrato y verificación del archivo wheel compilado (`dist/*.whl`) previo a la distribución.
- `scripts/write_deployment_record.py`:
  - Emisión auditable del registro de despliegue (`deployment-record.json`) tras publicaciones en DEV, vinculando commit Git, wheel SHA-256 y recursos desplegados.
- `scripts/write_promotion_record.py`:
  - Generación del registro criptográfico de promoción a ambientes superiores (CERTI / PROD).
- `scripts/verify_release_publication.py`:
  - Verificación de integridad y concordancia de tags inmutables de releases en GitHub (`*/*/v*`).

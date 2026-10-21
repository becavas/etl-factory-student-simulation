# Componentes Reutilizables de la Fábrica ETL

Este documento consolida el inventario formal de componentes compartidos desarrollados y mantenidos en el repositorio para acelerar la creación de nuevas capacidades y garantizar consistencia operativa, organizados en tres categorías fundamentales.

---

## 1. Runtime Compartido

El **runtime compartido** proporciona las primitivas de ejecución y utilidades comunes empaquetadas en la librería base de la plataforma:

- `src/enterprise_fabric/shared/`:
  - `spark.py`: Inicialización segura y configuración estandarizada de sesiones Spark en clusters Databricks y entornos locales de pruebas.
  - `paths.py`: Resolución determinista de rutas de catálogo, esquemas, volúmenes y almacenamiento en Unity Catalog según el ambiente de ejecución.
  - `hashing.py`: Generación determinista de hashes de registro (`_record_hash`) y claves canónicas versionadas para idempotencia y reconciliación.

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

# etl-factory-databricks

Fábrica empresarial de ETLs sobre Databricks Declarative Automation Bundles.

## Requisitos iniciales

- Conda
- Python 3.11
- Databricks CLI 1.12.x
- Git y GitHub CLI
- Acceso personal al workspace sandbox

## Preparación local

```bash
make env
conda activate etl-factory-databricks
make doctor
```

Los Bundles y las capabilities se incorporan progresivamente durante el recorrido hands-on.

## Calidad y empaquetado

Instalación local del paquete:

```bash
conda activate etl-factory-databricks
make env-update
make install
```

Gate local completo:

```bash
make quality
```

El gate comprueba formato, lint, unit tests, construcción e integridad del wheel. Los Pull Requests ejecutan los mismos controles mediante `engineering-quality`.

Validación remota del Bundle de sandbox:

```bash
set -a
source .env.local
set +a
databricks bundle validate --target sandbox --profile sandbox
```

CI no despliega en Databricks ni utiliza credenciales del workspace. Los recursos base consumidos por el repositorio están documentados en `docs/platform-dependencies.md` dentro del repositorio hands-on.

## Arquitectura y dependencias

- [Arquitectura de la fábrica](docs/architecture/overview.md)
- [Estándar de naming](docs/standards/naming.md)
- [Dependencias de plataforma](docs/platform-dependencies.md)
- [Runbook operativo del dominio retail](docs/operations/retail-runbook.md)

Verificación read-only de sandbox:

```bash
export EF_CATALOG="<catalogo_asignado>"
export EF_POLICY_ID="<policy-id-aprobado>"
python scripts/verify_platform_prerequisites.py
```

El script no aprovisiona infraestructura. Los recursos faltantes o prohibidos se escalan al owner indicado en `docs/platform-dependencies.md`.

## Capabilities

- [`retail/pedidos`](domains/retail/capabilities/pedidos/README.md): ingesta de pedidos e items desde Landing hasta Bronze.
- [`retail/clientes`](domains/retail/capabilities/clientes/README.md): clientes desde Landing hasta Silver.
- [`retail/devoluciones`](domains/retail/capabilities/devoluciones/README.md): devoluciones gobernadas desde Landing hasta Silver (modo sandbox).

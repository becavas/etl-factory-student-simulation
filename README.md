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

## Bundle nativo de laboratorio

El repositorio contiene un Bundle desechable para practicar el ciclo nativo de Bundles en sandbox.

Requiere un cluster de aprendizaje aprobado por Data Platform:

```bash
export BUNDLE_VAR_sandbox_cluster_id="<cluster-id-aprobado>"
databricks bundle validate -t sandbox -p sandbox
databricks bundle deploy -t sandbox -p sandbox
databricks bundle run -t sandbox -p sandbox native_hello_job
```

El laboratorio utiliza un cluster existente solamente para aprendizaje. No representa el patrón de compute productivo de la fábrica.

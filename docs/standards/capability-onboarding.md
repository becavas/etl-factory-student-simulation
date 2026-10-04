# Capability onboarding

## Información requerida

- dominio y nombre machine-friendly;
- propósito y owners reales;
- clasificación de datos;
- fuentes, garantías y owner de cada dependencia;
- salidas, grano e idempotencia;
- reglas de calidad y comportamiento de fallo;
- evidencia operativa y procedimiento de reproceso.

## Estructura mínima

```text
domains/<domain>/capabilities/<capability>/
├── README.md
├── databricks.yml
├── specs/jobs.yml
└── resources/jobs.generated.yml

src/enterprise_fabric/<domain>/<capability>/
├── __init__.py
├── bronze.py
├── entrypoints.py
├── schemas.py
└── silver.py

tests/<domain>/<capability>/
├── conftest.py
├── test_bronze.py
├── test_contract_coverage.py
└── test_silver.py
```

## Orden obligatorio

1. documentar contrato y garantías;
2. implementar tests y lógica;
3. declarar spec con el schema vigente;
4. generar y revisar el YAML;
5. ejecutar calidad local y CI;
6. validar y desplegar solo el Bundle de la capability;
7. ejecutar pruebas válida y negativa;
8. integrar mediante Pull Request y eliminar la rama.

No se copia una capability existente completa. Puede consultarse como referencia, pero cada
campo, regla y recurso debe provenir del contrato de la nueva capability.

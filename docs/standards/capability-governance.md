# Gobierno mínimo de una capability

## Fuente de verdad

- README: propósito, contexto, owners, operación y lifecycle.
- arquitectura: frontera de capability, tablas/capas cubiertas y dependencias operacionales reales.
- `specs/jobs.yml`: intención estructurada de Jobs soportada por el generador.
- contratos: schema, semántica y clasificación de compatibilidad cuando cambian consumidores.
- código y tests: comportamiento ejecutable.
- Unity Catalog: owner, grants, tags, comments y lineage efectivos.
- runbook: diagnóstico, escalamiento, rollback de código y referencia al procedimiento externo de recuperación de datos.

## Ownership obligatorio

Registrar grupos reales para data owner/steward, technical owner y operación. Enlazar el owner
de plataforma desde `docs/platform-dependencies.md`. No usar placeholders. En una simulación
expresamente aprobada, enlazar el mapeo de roles reales y sus límites; los owners efectivos de
activos compartidos siguen siendo grupos de cuenta o service principals aprobados.

## Clasificación

Declarar sensibilidad por dataset/columna, propósito de uso y grupos consumidores esperados.
Los governed tags deben provenir de la taxonomía corporativa. Un tag no sustituye grants,
masking, row filters ni aprobación de acceso.

## Lifecycle

Estados permitidos: `proposed`, `active`, `deprecated`, `retired`.
Todo cambio de estado requiere owner, fecha, decisión, consumidores afectados y evidencia.
`retired` no autoriza por sí mismo `DROP`, `VACUUM` o eliminación de almacenamiento.

## Gate

No se fusiona una capability sin README, owners reales, CODEOWNERS, spec válida, tests,
Bundle validado, evidencia válida/negativa y runbook.

# Bundle Job specifications

## Propósito

`specs/jobs.yml` expresa el subconjunto repetitivo de Lakeflow Jobs aprobado por la fábrica.
El generador produce YAML nativo de Databricks Declarative Automation Bundles.

## Ownership

- La capability es responsable de su spec, YAML generado y golden tests.
- Los maintainers de la fábrica son responsables del schema y del generador.
- Data Platform mantiene policies y valores de compute referenciados por variables.

## Fuente de verdad

La spec es fuente de intención. `resources/jobs.generated.yml` es un artefacto versionado,
revisable y desplegable, pero no se edita manualmente.

```bash
python -m tools.bundle_generator generate --spec \
  domains/<domain>/capabilities/<capability>/specs/jobs.yml

python -m tools.bundle_generator generate --all --check
```

La generación es offline. La validez final del Bundle se comprueba desde su raíz con
`databricks bundle validate`.

## Versionado

`spec_version: 1` identifica la semántica del contrato. Una versión no soportada falla.
Un cambio incompatible requiere un schema nuevo y una migración explícita; no se cambia
silenciosamente el significado de una spec existente.

## Extensión

No se aceptan propiedades libres. Para soportar un campo nuevo:

1. demostrarlo primero en YAML nativo;
2. actualizar schema y generador;
3. agregar pruebas positiva y negativa;
4. actualizar golden y documentación;
5. comprobar `generate --check` y `bundle validate`.

Herramientas de especificación o asistentes de código pueden proponer cambios sobre la spec,
pero no sustituyen schema, generator tests, revisión humana ni gates de CI.

## Recursos nativos fuera de la spec v1

La spec v1 cubre Jobs de capability basados en Python wheel y classic job compute.
Un patrón no soportado puede permanecer como YAML nativo cuando todavía no existe
repetición suficiente para ampliar el generador.

El recurso nativo debe:

- tener ownership y propósito explícitos;
- ser pequeño y no contener mapas libres de configuración empresarial;
- pasar tests estructurales y `databricks bundle validate`;
- permanecer como única fuente de verdad, sin una spec paralela;
- justificar una ampliación del generador cuando aparezca un segundo consumidor real.


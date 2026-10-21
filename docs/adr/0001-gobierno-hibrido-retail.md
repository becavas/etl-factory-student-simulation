# ADR-0001: gobierno híbrido para el dominio retail

- Estado: Accepted
- Fecha: 2026-10-20
- Decisores: Beto Castillo Vásquez (operando en simulación de laboratorio de una sola persona las identidades técnicas de autor/administrador @becavas y de revisor GitHub @becavas83; ref: `docs/platform-dependencies.md`)

## Contexto

El dominio retail necesita evolucionar sus pipelines ETL y modelos dimensionales sin adquirir privilegios de cuenta ni duplicar la plataforma de gobierno corporativo.

## Decisión

Centralizar identidades, taxonomía corporativa, ABAC, catálogos, bindings y grants base. Delegar al dominio contratos, clasificación propuesta mediante governed tags aprobados, comments, métricas de calidad, operación de Jobs y custodia de evidencia de ejecución. El repositorio ETL no contiene `iac/` y no crea governed tags ni identidades.

## Consecuencias

- Cambios de plataforma requieren coordinación y evidencia externa a través de Data Platform.
- El dominio puede versionar significado y contratos semánticos sin administrar privilegios globales.
- Los tags no se interpretan como enforcement sin una policy verificada centralmente.
- Los ownerships técnico (código en GitHub), de datos (Unity Catalog) y de plataforma se registran por separado.

## Alternativas descartadas

- Gobierno totalmente central: Cuello de botella para cambios de significado y evolución ágil del negocio.
- Gobierno totalmente federado: Riesgo de taxonomías y grants incompatibles entre dominios y ambientes.
- IaC dentro del repo ETL: Mezcla privilegios de infraestructura y lifecycle que pertenecen a plataforma.

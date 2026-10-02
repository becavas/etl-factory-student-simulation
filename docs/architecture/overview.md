# Arquitectura de la fábrica ETL

## Propósito

Este repositorio contiene código, tests y Databricks Bundles para desarrollar y operar ETLs empresariales. La unidad organizativa principal es el dominio y la unidad desplegable es una capability.

## Organización

```text
domains/<dominio>/capabilities/<capability>/
```

Cada capability mantiene su Bundle, código, tests y README. Puede publicar una o varias tablas y cubrir una o varias capas cuando comparten owner, SLA, release y operación. No se crea una capability por tabla o capa de manera automática. El código compartido se incorpora únicamente cuando existe reutilización real y consumidores identificados.

## Capas de datos

- `landing`: archivos fuente gobernados en Unity Catalog Volumes.
- `bronze`: representación fiel y trazable de la fuente.
- `silver`: datos tipados, normalizados y validados.
- `gold`: hechos, dimensiones y métricas orientados a consumo.

## Unidad desplegable

Una capability es un Bundle independiente cuando tiene owner y ciclo de despliegue propios. La orquestación de dominio coordina únicamente dependencias operacionales reales sin fusionar ownership; productor y consumidor también pueden operar con schedules independientes mediante contratos y freshness/readiness.

## Compute

- Classic job compute gobernado por compute policy.
- Access mode inicial: `SINGLE_USER`/Dedicated.
- All-purpose compute no es el patrón de Jobs productivos.
- Serverless se evalúa cuando coste, compatibilidad y operación lo justifiquen.
- `job_clusters` comparte compute únicamente entre tasks compatibles del mismo Job y run.

## Separación de responsabilidades

El repositorio administra código, Bundles, Jobs y configuración de aplicación. Data Platform administra catálogos, storage credentials, external locations, Volumes base, policies, grupos, identidades, federation policies, bindings y grants base.

Las dependencias externas se declaran en `docs/platform-dependencies.md`.

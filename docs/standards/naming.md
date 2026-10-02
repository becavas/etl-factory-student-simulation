# Estándar de naming

## Principios

- Nombres estables y predecibles.
- Sin nombres personales ni IDs de workspace en archivos versionados.
- El ambiente se parametriza; no se copia la implementación.

## Convenciones

| Elemento | Convención | Ejemplo |
|---|---|---|
| Dominio | `snake_case` singular | `retail` |
| Capability | `snake_case` | `pedidos` |
| Directorio | `snake_case` | `domains/retail/capabilities/pedidos` |
| Bundle name | `<dominio>_<capability>` | `retail_pedidos` |
| Resource key | `<capability>_<capa>_job` | `pedidos_bronze_job` |
| Job visible | `<dominio>-<capability>-<capa>` | `retail-pedidos-bronze` |
| Task key | verbo o resultado en `snake_case` | `ingest_pedidos` |
| Catálogo | `retail_sbx_<id_alumno>` en sandbox; `<dominio>_<ambiente>` en otros ambientes | `retail_sbx_alumno01` (ejemplo) |
| Schema | capa en minúscula | `bronze` |
| Tabla Bronze | `<entidad>_raw` | `pedidos_raw` |
| Tabla Silver | `<entidad>_curated` | `pedidos_curated` |
| Variable | `snake_case` | `catalog_name` |
| Rama feature | `feature/<dominio>-<capability>-<cambio>` | `feature/retail-pedidos-bronze` |

## Tags mínimos de recursos

- `domain`
- `capability`
- `layer`
- `owner`
- `environment`
- `managed_by`
- `criticality`

Los tags de Jobs y compute sirven para operación y costes. La clasificación de tablas y columnas se aplica en Unity Catalog y no se sustituye con tags de compute.

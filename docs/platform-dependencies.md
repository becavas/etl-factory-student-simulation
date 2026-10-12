# Dependencias de plataforma

Este repositorio consume los siguientes recursos. Su aprovisionamiento y lifecycle pertenecen a Data Platform; las capabilities los referencian mediante configuración por ambiente.

## Sandbox

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `sandbox` | URL administrada fuera de Git | Usuario U2M habilitado | Data Platform | Verificado |
| Catálogo | `retail` | `retail_sbx_a001` | Visible y vinculado al workspace sandbox | Data Platform | Verificado |
| Schema | `landing` | `retail_sbx_a001.landing` | `USE SCHEMA` | Data Platform | Verificado |
| Schema | `bronze` | `retail_sbx_a001.bronze` | Crear/modificar objetos según rol acordado | Data Platform | Verificado |
| Schema | `silver` | `retail_sbx_a001.silver` | Crear/modificar objetos según rol acordado | Data Platform | Verificado |
| Schema | `gold` | `retail_sbx_a001.gold` | Crear/modificar objetos según rol acordado | Data Platform | Verificado |
| Volume | `pedidos_source` | `retail_sbx_a001.landing.pedidos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Volume | `clientes_source` | `retail_sbx_a001.landing.clientes_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Volume | `productos_source` | `retail_sbx_a001.landing.productos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Compute policy | `uc_standard_job_compute` | Policy ID administrado externamente | `CAN_USE`, classic job compute, `SINGLE_USER` permitido | Data Platform | Verificado |

## DEV

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `dev` | Workspace compartido DEV | URL oficial y workspace assignment de ambos SPs | Data Platform | Verificado |
| Deployer SP / WIF | `etl-factory-dev-deployer` | Subject `repo:<org>/<repo>:environment:dev` | Autenticación federada OIDC sin secretos en runner | IAM / Data Platform | Configurado (prueba conectada pendiente) |
| Runtime SP | `etl-factory-dev-runtime` | SP runtime en workspace | Application ID estable y workspace assignment | IAM / Data Platform | Verificado |
| SP role | `Service Principal User` | Rol deployer → runtime | Deployer autorizado a configurar Run as del runtime | IAM | Configurado (prueba conectada pendiente) |
| Catálogo | `retail_dev` | `retail_dev` | Catálogo aislado y schemas `landing`, `bronze`, `silver`, `gold` | Data Platform | Verificado |
| Volume | `pedidos_source` | `retail_dev.landing.pedidos_source` | `READ VOLUME` en fuentes gobernadas DEV | Data Platform | Verificado |
| Volume | `clientes_source` | `retail_dev.landing.clientes_source` | `READ VOLUME` en fuentes gobernadas DEV | Data Platform | Verificado |
| Volume | `productos_source` | `retail_dev.landing.productos_source` | `READ VOLUME` en fuentes gobernadas DEV | Data Platform | Verificado |
| Compute policy | `policy-factory-sandbox-uc-standard-job-compute` | Variable `vars.DATABRICKS_POLICY_ID` | `CAN_USE` en policy compartida para deployer y runtime SPs; node `vars.DATABRICKS_NODE_TYPE_ID` | Data Platform | Configuración verificada |
| UC grants | Permisos runtime DEV | Grants sobre `retail_dev` heredados a schemas/Volumes | Runtime autorizado a leer Landing y publicar Bronze/Silver/Gold (excepción de laboratorio) | Data Governance | Configuración verificada |
| Child Job ACL | Child Job permissions | `CAN_MANAGE_RUN` en child jobs | Runtime puede ejecutar children desde el parent | Bundle configuration | Declarado en YAML (verificación remota pendiente) |
| Carpeta Bundle | State compartido | `/Workspace/Shared/.bundle` | Carpeta de state escribible por deployer | Data Platform | Verificado |
| Grupo operador | Operador DEV | `admins` | Grupo con permisos de ejecución/observación | Data Governance | Verificado |
| GitHub Environment | `dev` | Environment `dev` | Deployment branch restringida a `main` y 6 variables configuradas | Repository admin | Verificado |

> **Nota sobre permisos Unity Catalog en DEV (Excepción de Laboratorio)**:
> Por acuerdo para este laboratorio, el runtime SP (`etl-factory-dev-runtime`) dispone de los permisos necesarios otorgados directamente sobre el catálogo `retail_dev` y heredados por sus schemas y Volumes hijos. Esta decisión se conserva como excepción controlada de capacitación y **no representa el estándar de mínimo privilegio estricto por schema y Volume**, el cual se gobernará en fases posteriores (CERTI/PROD).

## CERTI

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `certi` | Workspace compartido CERTI | URL oficial y workspace assignment de ambos SPs | Data Platform | Configurado |
| Deployer SP / WIF | `etl-factory-certi-deployer` | Subject `<repo>:environment:certi` | Autenticación federada OIDC sin secretos en runner | IAM / Data Platform | Configurado |
| Runtime SP | `etl-factory-certi-runtime` | SP runtime en workspace CERTI | Application ID estable y workspace assignment | IAM / Data Platform | Configurado |
| SP role | `Service Principal User` | Rol deployer → runtime | Deployer autorizado a configurar Run as del runtime | IAM | Configurado |
| Catálogo | `retail_certi` | `retail_certi` | Binding exclusivo y schemas `landing`, `bronze`, `silver`, `gold` | Data Platform | Configurado |
| Volume | `pedidos_source` | `retail_certi.landing.pedidos_source` | `READ VOLUME` en fuentes gobernadas CERTI; dataset smoke | Data Platform | Configurado |
| Volume | `clientes_source` | `retail_certi.landing.clientes_source` | `READ VOLUME` en fuentes gobernadas CERTI; dataset smoke | Data Platform | Configurado |
| Volume | `productos_source` | `retail_certi.landing.productos_source` | `READ VOLUME` en fuentes gobernadas CERTI; dataset smoke | Data Platform | Configurado |
| Compute policy | ID externo | Variable `vars.DATABRICKS_POLICY_ID` | `CAN_USE`, classic job compute, `SINGLE_USER`, node `vars.DATABRICKS_NODE_TYPE_ID` | Data Platform | Configurado |
| Child Job ACL | Child Job permissions | `CAN_MANAGE_RUN` en child jobs | Runtime puede ejecutar children desde el parent | Bundle configuration | Declarado en YAML |
| Carpeta Bundle | State compartido | `/Workspace/Shared/.bundle/.../certi` | State separado y escribible por deployer | Data Platform | Configurado |
| Grupo operador | Operador CERTI | Grupo CERTI | Permisos según segregación | Data Governance | Configurado |
| GitHub Environment | `certi` | Environment `certi` | Deployment branch restringida a `main` y variables configuradas | Repository admin | Configurado |

## PROD

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `prod` | Workspace productivo PROD | URL oficial y workspace assignment de ambos SPs | Data Platform | Configurado |
| Deployer SP / WIF | `etl-factory-prod-deployer` | Subject `<repo>:environment:prod` | Autenticación federada OIDC sin secretos en runner | IAM / Data Platform | Configurado |
| Runtime SP | `etl-factory-prod-runtime` | SP runtime en workspace PROD | Application ID estable y workspace assignment | IAM / Data Platform | Configurado |
| SP role | `Service Principal User` | Rol deployer → runtime | Deployer autorizado a configurar Run as del runtime | IAM | Configurado |
| Catálogo | `retail_prod` | `retail_prod` | Binding exclusivo y schemas `landing`, `bronze`, `silver`, `gold` | Data Platform | Configurado |
| Volume | `pedidos_source` | `retail_prod.landing.pedidos_source` | `READ VOLUME` en fuentes gobernadas PROD | Data Platform | Configurado |
| Volume | `clientes_source` | `retail_prod.landing.clientes_source` | `READ VOLUME` en fuentes gobernadas PROD | Data Platform | Configurado |
| Volume | `productos_source` | `retail_prod.landing.productos_source` | `READ VOLUME` en fuentes gobernadas PROD | Data Platform | Configurado |
| Compute policy | ID externo | Variable `vars.DATABRICKS_POLICY_ID` | `CAN_USE`, classic job compute, `SINGLE_USER`, node `vars.DATABRICKS_NODE_TYPE_ID` | Data Platform | Configurado |
| Child Job ACL | Child Job permissions | `CAN_MANAGE_RUN` en child jobs | Runtime puede ejecutar children desde el parent | Bundle configuration | Declarado en YAML |
| Carpeta Bundle | State compartido | `/Workspace/Shared/.bundle/.../prod` | State separado y escribible por deployer | Data Platform | Configurado |
| Grupo operador | Operador PROD | Grupo PROD | Permisos según segregación | Data Governance | Configurado |
| GitHub Environment | `prod` | Environment `prod` | Deployment branch restringida a `main`, required reviewers y variables configuradas | Repository admin | Configurado |

El runtime PROD recibe grants sobre datos PROD; el deployer PROD no. Ambos pueden requerir `CAN_USE` sobre la policy para configurar/ejecutar el Job según el control de plataforma.

## Contrato de fuente diaria

```text
Daily source contract
- Timezone de negocio: America/Lima.
- Cutoff: 01:30.
- Schedule del dominio: 02:00.
- Batch ID: YYYY-MM-DD correspondiente al día del trigger.
- Los tres productores publican el mismo batch antes del cutoff.
- Un batch declarado ready es inmutable; una corrección reemplaza el batch completo.
- Un atraso se escala al owner de la fuente; no se procesa silenciosamente otro día.
```

Los Volumes continúan organizados por `batch_id=<batch_id>`. No se introduce otra columna o controlador de calendario.

## Dependencias operativas de plataforma

| Dependencia | CERTI | PROD | Garantía |
|---|---|---|---|
| notification destination ID | ID corporativo | ID corporativo | no secreto, administrado externamente |
| system tables | acceso read-only | acceso read-only | `lakeflow`, `billing`, `access` según disponibilidad |
| SQL warehouse | ID gobernado | consulta solamente cuando esté autorizado | no creado por Bundle |
| tag ruleset | `*/*/v*` | repositorio | impedir update/delete; creación automatizada aprobada |

El destino puede ser Teams, Slack, PagerDuty o webhook corporativo. Databricks almacena su ID; el repositorio no hospeda el receptor.
Si se habilita la ruta de email nativo de laboratorio (§8.1), se utiliza `DATABRICKS_NOTIFICATION_EMAIL` en lugar de destination ID.

## Contrato de acceso

- El Data Engineer utiliza identidad personal solo en sandbox.
- Los grants duraderos se asignan a grupos, no directamente a personas.
- DEV, CERTI y PROD utilizan identidades automatizadas.
- Los catálogos de ambientes se aíslan mediante grants y bindings administrados por plataforma.

## Configuración local de verificación

```bash
export EF_CATALOG="<catalogo_asignado>"
# Sustituye el marcador por el nombre exacto de tu ficha antes de continuar.
export EF_POLICY_ID="<policy-id-aprobado>"
export EF_PLATFORM_OWNER="Data Platform"
export EF_PLATFORM_SUPPORT_CHANNEL="#data-platform-soporte"
```

Estos valores no son secretos, pero los identificadores específicos del workspace se mantienen fuera de Git. El repositorio versiona nombres lógicos y garantías.

## Escalamiento

Cuando una dependencia falta o está prohibida, adjuntar:

- workspace y profile utilizados;
- identidad devuelta por `current-user me`;
- recurso lógico y físico;
- comando read-only ejecutado;
- error completo sin tokens;
- clasificación `MISSING`, `FORBIDDEN` o `ERROR`;
- canal: #data-platform-soporte.


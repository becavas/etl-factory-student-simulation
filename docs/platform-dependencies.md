# Dependencias de plataforma

Este repositorio consume los siguientes recursos. Su aprovisionamiento y lifecycle pertenecen a Data Platform; las capabilities los referencian mediante configuración por ambiente.

## Sandbox

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `sandbox` | ID `7405615183307398` (`https://adb-7405615183307398.18.azuredatabricks.net`) | Usuario U2M habilitado | Data Platform | Verificado |
| Catálogo | `retail` | `retail_sbx_a001` | Catálogo aislado (`ISOLATED`), visible y vinculado exclusivamente al workspace sandbox | Data Platform | Verificado |
| Schema | `landing` | `retail_sbx_a001.landing` | `USE SCHEMA` | Data Platform | Verificado |
| Schema | `bronze` | `retail_sbx_a001.bronze` | Crear/modificar objetos según rol acordado | Data Platform | Verificado |
| Schema | `silver` | `retail_sbx_a001.silver` | Crear/modificar objetos según rol acordado; incluye tabla `silver.clientes_curated` | Data Platform | Verificado |
| Schema | `gold` | `retail_sbx_a001.gold` | Crear/modificar objetos según rol acordado | Data Platform | Verificado |
| Volume | `pedidos_source` | `retail_sbx_a001.landing.pedidos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Volume | `clientes_source` | `retail_sbx_a001.landing.clientes_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Volume | `productos_source` | `retail_sbx_a001.landing.productos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Verificado |
| Volume | `devoluciones_source` | `retail_sbx_a001.landing.devoluciones_source` | `USE CATALOG`, `USE SCHEMA`, `READ VOLUME`, `WRITE VOLUME` para publicación/evaluación; el owner humano existente (`becavas`) posee las facultades aplicables y conserva poderes administrativos como excepción (sin mínimo privilegio ni grants redundantes) | Data Platform | Verificado (preexistente) |
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
- Un batch declarado ready es inmutable; una corrección se publica como batch sucesor
  y se documenta su relación con la entrega anterior.
- Un atraso se escala al owner de la fuente; no se procesa silenciosamente otro día.
```

Los Volumes continúan organizados por `batch_id=<batch_id>`. No se introduce otra columna o controlador de calendario.

> **Excepción acotada de laboratorio en CERTI**: Los fixtures negativos CERTI de §§21.1–21.2 disponen de una excepción explícita de laboratorio: el owner de la fuente autoriza la republicación controlada del mismo batch únicamente después de demostrar y capturar el fallo previsto en CERTI, conservando ambos manifests (fallido y corregido) antes de la reparación operativa. Esta excepción no altera el contrato diario PROD ni la inmutabilidad de la evaluación final de Fase 15.

## Dependencias operativas de plataforma

| Dependencia | CERTI | PROD | Garantía |
|---|---|---|---|
| ruta de notificación | ID Slack del laboratorio (canal privado `etl-factory-alertas`) | ID Slack del laboratorio (canal privado `etl-factory-alertas`) | Webhook independiente por ambiente custodiado en Slack y Databricks; destination ID no secreto |
| system tables | acceso read-only | acceso read-only | `lakeflow`, `billing`, `access` según disponibilidad |
| SQL warehouse | ID gobernado | consulta solamente cuando esté autorizado | no creado por Bundle |
| tag ruleset | `*/*/v*` | repositorio | impedir update/delete; creación automatizada aprobada |

La ruta operativa elegida para esta instalación es **Slack personal**. El propietario del laboratorio opera el canal privado `etl-factory-alertas` en su workspace ADRs y la app ETL Factory Lab Alerts. Gmail sirve únicamente para identificar al propietario de Slack; no recibe las alertas. Teams es una adaptación corporativa opcional del curso. `DATABRICKS_NOTIFICATION_DESTINATION_ID` se custodia en cada GitHub Environment; el repositorio no hospeda el receptor ni contiene webhooks.

## Governed Tags de Cuenta (Taxonomía de Laboratorio)

Creados y autorizados en la cuenta Databricks por el Administrador de Plataforma y validados bajo la simulación de Fase 15 §2.1:

| Clave de Tag | Valores Permitidos | Alcance | Propósito |
|---|---|---|---|
| `data_domain` | `retail` | Cuenta | Identificación formal del dominio de datos |
| `data_classification` | `internal`, `confidential`, `restricted` | Cuenta | Clasificación de confidencialidad y criticidad |
| `lifecycle` | `active`, `deprecated`, `retired` | Cuenta | Estado del ciclo de vida del activo de datos |

Estos tags constituyen una taxonomía de laboratorio aprobada por el propietario (`account_admin` con permiso implícito `ASSIGN`) para validar controles técnicos de gobierno; no representan una política corporativa externa.

## Operador, Responsabilidades y Contrato de Acceso

- **Propietario del Laboratorio, Administrador de Plataforma y Autor (`becavas`)**: El alumno y propietario (`bcastillo@techdic.onmicrosoft.com`) es el autor del código, administrador responsable de la plataforma del laboratorio y titular del rol `account_admin` en Databricks (con facultad implícita `ASSIGN` sobre tags gobernados). Autoriza las operaciones y mantiene los recursos.
- **Identidad Revisora GitHub en Simulación (`becavas83`)**: Cuenta secundaria del operador utilizada para la revisión formal de Pull Requests y la aprobación obligatoria de compuertas de despliegue (Environment `prod`). Cuenta con permiso `write` verificado en el repositorio. Se documenta formalmente conforme a Fase 15 §2.1 y §10.1 que **una persona operando dos cuentas representa una emulación técnica y no demuestra segregación humana real ni mínimo privilegio estricto**.
- **Estado de Protecciones de Rama `main` (Integradas y Comprobadas)**:
  La PR preparatoria #31 fue aprobada formalmente por `becavas83` sobre el commit `2153721ba505d9fd30f5a12c850ccc9b9610ff98` e integrada en `main` (`74754a244abeaae8295ab2256c0ed90b00d60cbe`) el 2026-10-20. El despliegue automático a DEV (Run ID `39504376658`) confirmó el despliegue de las 5 raíces existentes con el wheel inmutable `c0f4874c2677b282312f6fa0edfe09987cb6a531ae58df791e0d4ff1c3fecb09`.
  Posteriormente, el Administrador activó y verificó las reglas de protección de rama sobre `main`:
  - 1 aprobación obligatoria de Code Owner (`require_code_owner_reviews: true`, `required_approving_review_count: 1`).
  - Descarte de aprobaciones obsoletas tras nuevos commits (`dismiss_stale_reviews: true`).
  - Aprobación requerida sobre el último push (`require_last_push_approval: true`).
  - Resolución obligatoria de conversaciones (`required_conversation_resolution: true`).
  - Aplicación estricta a administradores (`enforce_admins: true`).
  - Check de calidad estricto requerido (`engineering-quality`, App ID 15368).
  - Bloqueo de force pushes y eliminación de rama.
  El bloqueo efectivo de revisión fue comprobado empíricamente mediante la PR negativa #32 en `ops/governance/`, la cual permaneció bloqueada sin aprobación aún tras aprobar CI y fue cerrada sin merge.
- **Herramienta de Asistencia e Implementación (Antigravity)**: Asistente técnico de IA para desarrollo de código, pruebas, verificación y recolección de evidencias. Opera como herramienta de soporte técnico del alumno; no asume autoría humana, ownership ni rol de aprobación.
- **Evaluador Técnico y Auditor del Curso (Codex)**: Mantiene la guía oficial del curso y evalúa técnicamente las evidencias de la fábrica antes de decisiones de gate y fusiones en `main`. No es el owner administrativo de la infraestructura ni persona de guardia de operaciones.
- Canales corporativos no acreditados (ej. `#data-platform-soporte`), guardias de operaciones rotativas y comités de gobernanza corporativos quedan marcados como **pendientes de acreditación corporativa externa**.
- El Data Engineer utiliza identidad personal exclusivamente en sandbox; DEV, CERTI y PROD operan mediante identidades automatizadas segregadas (deployer y runtime SPs). Acciones operativas de repair son ejecutadas por el operador autorizado vía OAuth con permisos `CAN_MANAGE_RUN`, procesando bajo el runtime SP del ambiente.

## Observabilidad y Retención Verificada

- **Observabilidad de Plataforma**: Codex y el operador comprobaron lectura exitosa sobre 7 system tables (`system.lakeflow.jobs`, `job_run_timeline`, `billing.usage`, `billing.list_prices`, `access.audit`, `access.table_lineage`, `information_schema.tables`) utilizando el warehouse CERTI `e637b60e6f465fde` con la identidad humana `bcastillo@techdic.onmicrosoft.com` (`certi-platform`). Los SQL warehouses permanecen en estado `STOPPED` y solo se inician temporalmente bajo autorización explícita para lecturas de auditoría acotadas.
- **Políticas de Retención Verificadas**:
  Las políticas de retención, fuentes oficiales y procedimientos de custodia técnica están documentados y enlazados formalmente en [`docs/operations/retail-runbook.md`](operations/retail-runbook.md#5-políticas-de-retención-y-custodia-de-artefactos). Para preservar una única fuente de verdad documental, no se duplica la matriz técnica en este documento; el runbook contiene los plazos verificados (artefactos de GitHub Actions 90 días, GitHub Releases sin expiración por API, y retención configurable de Databricks deshabilitada a nivel de cuenta / default de Beta).


## Configuración local de verificación

```bash
export EF_CATALOG="<catalogo_asignado>"
export EF_POLICY_ID="<policy-id-aprobado>"
export EF_PLATFORM_OWNER="Propietario del Laboratorio (becavas)"
export EF_OPERATOR_PROFILE="certi-platform" # En CERTI; usar perfil correspondiente en PROD
```

Estos valores no son secretos. Los identificadores específicos de infraestructura se administran fuera de Git.

## Escalamiento

Cuando una dependencia falte o esté bloqueada, adjuntar:

- workspace y profile utilizados;
- identidad devuelta por `current-user me`;
- recurso lógico y físico;
- comando read-only ejecutado;
- error completo sin tokens ni secretos;
- clasificación `MISSING`, `FORBIDDEN` o `ERROR`;
- canal: escalamiento al **Propietario del Laboratorio** (`becavas`) para autorizaciones y ejecución administrativa; contraste y consultas de especificación técnica con **Codex**.



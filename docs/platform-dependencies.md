# Dependencias de plataforma

Este repositorio consume los siguientes recursos. Su aprovisionamiento y lifecycle pertenecen a Data Platform; las capabilities los referencian mediante configuración por ambiente.

## Sandbox

| Tipo | Nombre lógico | Nombre físico | Garantía requerida | Owner | Estado |
|---|---|---|---|---|---|
| Workspace | `sandbox` | URL administrada fuera de Git | Usuario U2M habilitado | Data Platform | Pendiente de verificar |
| Catálogo | `retail` | `retail_sbx_a001` | Visible y vinculado al workspace sandbox | Data Platform | Pendiente de verificar |
| Schema | `landing` | `retail_sbx_a001.landing` | `USE SCHEMA` | Data Platform | Pendiente de verificar |
| Schema | `bronze` | `retail_sbx_a001.bronze` | Crear/modificar objetos según rol acordado | Data Platform | Pendiente de verificar |
| Schema | `silver` | `retail_sbx_a001.silver` | Crear/modificar objetos según rol acordado | Data Platform | Pendiente de verificar |
| Schema | `gold` | `retail_sbx_a001.gold` | Crear/modificar objetos según rol acordado | Data Platform | Pendiente de verificar |
| Volume | `pedidos_source` | `retail_sbx_a001.landing.pedidos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Pendiente de verificar |
| Volume | `clientes_source` | `retail_sbx_a001.landing.clientes_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Pendiente de verificar |
| Volume | `productos_source` | `retail_sbx_a001.landing.productos_source` | `READ VOLUME` y dataset de capacitación | Data Platform | Pendiente de verificar |
| Compute policy | `uc_standard_job_compute` | Policy ID administrado externamente | `CAN_USE`, classic job compute, `SINGLE_USER` permitido | Data Platform | Pendiente de verificar |

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

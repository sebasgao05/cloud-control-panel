# Separación de Facturación por Tags (Cost Allocation)

## Resumen

Este proyecto utiliza **AWS Cost Allocation Tags** para separar la facturación del
Cloud Control Panel de otros proyectos en la misma cuenta AWS. Todos los recursos
(estáticos y dinámicos) son etiquetados automáticamente durante el deploy.

## Tags aplicados

| Tag Key       | Valor por defecto        | Propósito                              |
|---------------|--------------------------|----------------------------------------|
| `Project`     | `cloud-control-panel`    | Identificador del proyecto (principal) |
| `Environment` | `production`             | Ambiente (production, staging, dev)    |
| `Owner`       | `platform-team`          | Equipo responsable                     |
| `CostCenter`  | `cloud-ops`              | Centro de costo para billing           |
| `ManagedBy`   | `cloudformation`         | Herramienta de gestión                 |
| `Component`   | (varía por recurso)      | Componente: compute, api, cdn, etc.    |

## Recursos etiquetados

### Infraestructura (CloudFormation)
- DynamoDB Table → `Component: database`
- Lambda Function → `Component: compute`
- IAM Roles → `Component: iam`
- API Gateway HTTP API → `Component: api`
- CloudFront Distribution → `Component: cdn`
- S3 Bucket (frontend) → `Component: frontend`
- S3 Bucket (deploy artifacts) → `Component: deployment`

### Recursos dinámicos (creados por Lambda)
- EventBridge Schedules → `Component: scheduler`, `ManagedBy: lambda-scheduler`

## Activación en AWS (obligatorio)

Para que los tags aparezcan en Cost Explorer y reportes de facturación:

1. Ir a **AWS Billing Console** → **Cost Allocation Tags**
2. En la pestaña **User-defined cost allocation tags**, buscar:
   - `Project`
   - `Environment`
   - `CostCenter`
   - `Owner`
3. Seleccionarlos y hacer clic en **Activate**
4. Esperar ~24 horas para que los datos aparezcan en Cost Explorer

## Cómo filtrar costos en Cost Explorer

1. Ir a **AWS Cost Explorer**
2. En filtros, seleccionar **Tag** → `Project` → `cloud-control-panel`
3. Esto muestra SOLO los costos de este proyecto, separados del resto

### Agrupación por componente
- Filtrar por `Project = cloud-control-panel`
- Agrupar por `Tag: Component`
- Verás el desglose: compute, api, cdn, database, scheduler, etc.

## Personalización

Los valores por defecto están en `config/tags.json` (referencia) y se configuran como
parámetros del CloudFormation template. Para cambiarlos:

### Opción 1: En el deploy
```bash
# Linux/Mac
./deploy.sh --stack-tag ccp-staging --env staging

# PowerShell
.\deploy.ps1 -StackTag "ccp-staging"
```

### Opción 2: Override de parámetros CloudFormation
```bash
aws cloudformation deploy \
  --parameter-overrides \
    ProjectTag=mi-proyecto \
    EnvironmentTag=staging \
    OwnerTag=equipo-dev \
    CostCenterTag=centro-123
```

## Múltiples instancias del panel

Si despliegas varias instancias del panel (por ejemplo staging + production),
cada una tendrá su propio valor de `Environment` y `StackTag`, lo que permite
distinguir costos entre ambientes en Cost Explorer.

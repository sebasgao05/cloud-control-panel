# Guia del Administrador - Cloud Control Panel

## Responsabilidades del Admin

El administrador es quien:
- Configura las cuentas e instancias en `config/accounts.json`
- Crea y distribuye API Keys a los usuarios
- Despliega y actualiza la infraestructura
- Configura roles cross-account (si aplica)

---

## 1. Primer Despliegue

### Prerequisitos

- AWS CLI instalado y configurado con la cuenta principal
- PowerShell (Windows)
- Permisos: CloudFormation, IAM, Lambda, API Gateway, S3, CloudFront

### Pasos

1. Clonar el repositorio
   ```bash
   git clone <repo-url>
   cd cloud-control-panel
   ```

2. Editar configuracion
   ```bash
   notepad config/accounts.json
   ```
   Ver seccion "Configuracion" mas abajo.

3. Desplegar
   ```powershell
   .\deploy.ps1 -StackTag "ccp-prod"
   ```

4. Anotar la URL que devuelve el script y distribuirla con la API Key.

---

## 2. Configuracion (accounts.json)

### Estructura base

```json
{
  "settings": {
    "defaultRegion": "us-east-1",
    "pollIntervalSeconds": 30,
    "timezone": "America/Bogota"
  },
  "apiKeys": { ... },
  "accounts": [ ... ]
}
```

### Agregar una API Key

```json
"apiKeys": {
  "tu-key-secreta-aqui": {
    "name": "Nombre visible en el panel",
    "role": "admin",
    "accounts": ["*"]
  }
}
```

- La key es el string que el usuario ingresa en el login
- `accounts`: lista de IDs de cuenta permitidos, o `["*"]` para todas
- Genera keys seguras: `openssl rand -hex 24`

### Agregar una cuenta

```json
{
  "id": "mi-cuenta",
  "name": "Nombre visible en el panel",
  "awsAccountId": "123456789012",
  "region": "us-east-1",
  "crossAccountRoleArn": null,
  "instances": [],
  "groups": []
}
```

- `id`: slug unico (sin espacios, minusculas)
- `crossAccountRoleArn`: null si es la cuenta donde esta la Lambda, ARN del rol si es remota

### Agregar una instancia

```json
{
  "id": "mi-server",
  "name": "Servidor Web",
  "instanceId": "i-0abc123def456789",
  "description": "Servidor web de produccion",
  "dashboardPort": 5476,
  "group": null
}
```

- `id`: slug unico dentro de la cuenta
- `instanceId`: ID real de EC2 (empieza con i-)
- `dashboardPort`: puerto para boton "Dashboard" (null si no aplica)
- `group`: ID del grupo al que pertenece (null si es independiente)

### Agregar un grupo

```json
{
  "id": "core-servers",
  "name": "Core",
  "description": "Se encienden y apagan juntas",
  "startOrder": ["db-server", "app-server", "web-server"],
  "stopOrder": ["web-server", "app-server", "db-server"]
}
```

- `startOrder`: orden de encendido (DB primero, web ultimo)
- `stopOrder`: orden de apagado (inverso al encendido tipicamente)
- Los IDs en startOrder/stopOrder deben coincidir con el `id` de las instancias

---

## 3. Operaciones Comunes

### Agregar nueva instancia a cuenta existente

1. Obtener el Instance ID desde la consola AWS
2. Editar `config/accounts.json`, agregar al array `instances` de la cuenta
3. Ejecutar `.\deploy.ps1`

### Agregar nueva cuenta (multi-cuenta)

1. Crear el rol en la cuenta remota (ver docs/cross-account-setup.md)
2. Agregar la cuenta al array `accounts` en el config
3. Crear API Key para el equipo de esa cuenta (opcional)
4. Ejecutar `.\deploy.ps1`

### Cambiar API Key de un usuario

1. Editar `apiKeys` en el config: cambiar la key string
2. Ejecutar `.\deploy.ps1`
3. Comunicar la nueva key al usuario

### Revocar acceso de un usuario

1. Eliminar su entrada de `apiKeys`
2. Ejecutar `.\deploy.ps1`

---

## 4. Seguridad

### Buenas practicas

- Usa keys largas y aleatorias: `openssl rand -hex 24`
- No compartas keys de admin con operadores
- Restringe `accounts` al minimo necesario por key
- Rota keys periodicamente
- No subas `accounts.json` con keys reales a repositorios publicos

### Permisos IAM minimos para la Lambda

La Lambda necesita:
- `ec2:StartInstances`, `ec2:StopInstances`, `ec2:DescribeInstances`
- `ssm:SendCommand`, `ssm:GetCommandInvocation`
- `sts:AssumeRole` (solo para cross-account)

### Permisos IAM para el Admin (despliegue)

El admin que ejecuta `deploy.ps1` necesita:
- CloudFormation full access
- IAM (crear roles)
- Lambda (crear/actualizar funciones)
- API Gateway (crear APIs)
- S3 (crear buckets, subir objetos)
- CloudFront (crear distribuciones)

---

## 5. Troubleshooting

### "Deploy failed"
```powershell
aws cloudformation describe-stack-events --stack-name cloud-control-ccp-prod --region us-east-1
```

### Lambda no puede asumir rol remoto
- Verificar que el Trust Policy del rol remoto apunte al ARN de la Lambda role
- Verificar que la Lambda role tenga permiso `sts:AssumeRole`

### Usuario no ve una cuenta
- Verificar que su API Key tenga la cuenta en el array `accounts`

### Instancia no responde a Start/Stop
- Verificar que el Instance ID sea correcto
- Verificar que la instancia no este en estado "terminated"
- Si es cross-account, verificar el rol remoto

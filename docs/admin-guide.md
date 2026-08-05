# Guia del Administrador - Cloud Control Panel

## Responsabilidades del Admin

El administrador es quien:
- Configura las cuentas, instancias y features en `config/accounts.json`
- Crea y distribuye API Keys a los usuarios
- Configura el scheduler, notificaciones y costos
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

3. Desplegar
   ```powershell
   .\deploy.ps1 -StackTag "ccp-prod"
   ```

4. Anotar la URL que devuelve el script y distribuirla con la API Key.

---

## 2. Configuracion (accounts.json)

### Estructura completa

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

### API Keys y permisos

```json
"apiKeys": {
  "tu-key-secreta-aqui": {
    "name": "Admin Principal",
    "role": "admin",
    "accounts": ["*"]
  },
  "operador-key": {
    "name": "Operador Equipo X",
    "role": "operator",
    "accounts": ["sanidad"],
    "scheduler": {
      "view": true,
      "edit": false
    }
  }
}
```

#### Permisos del scheduler por API Key

| Configuracion | Comportamiento |
|---------------|----------------|
| `role: "admin"` | Siempre ve y edita todo (scheduler, notificaciones, costos) |
| `"scheduler": {"edit": true}` | Ve y edita el scheduler (edit implica view) |
| `"scheduler": {"view": true, "edit": false}` | Solo ve los horarios, no puede modificar |
| `"scheduler": {"view": false}` | No ve la seccion de scheduler |
| Sin campo `scheduler` | No ve el scheduler |

#### Notificaciones y costos

Solo el admin puede ver y gestionar notificaciones y costos estimados.
Los operadores no ven estas secciones.

### Agregar una cuenta con features

```json
{
  "id": "mi-cuenta",
  "name": "Nombre visible en el panel",
  "awsAccountId": "123456789012",
  "region": "us-east-1",
  "crossAccountRoleArn": null,
  "features": {
    "scheduler": true,
    "notifications": true,
    "costEstimate": true
  },
  "instances": [],
  "groups": []
}
```

### Agregar una instancia

```json
{
  "id": "mi-server",
  "name": "Servidor Web",
  "instanceId": "i-0abc123def456789",
  "instanceType": "t3.medium",
  "description": "Servidor web de produccion",
  "dashboardPort": 5476,
  "group": null
}
```

- `instanceType`: Tipo de instancia EC2 (usado para estimacion de costos)
- `group`: ID del grupo al que pertenece (null si es independiente)

### Agregar un grupo con color

```json
{
  "id": "core-servers",
  "name": "Core",
  "description": "Se encienden y apagan juntas",
  "color": "#6366f1",
  "startOrder": ["db-server", "app-server", "web-server"],
  "stopOrder": ["web-server", "app-server", "db-server"]
}
```

- `color`: Color hex para la etiqueta visual del grupo en el panel
- `startOrder`: Orden de encendido
- `stopOrder`: Orden de apagado

---

## 3. Scheduler (Programacion)

### Configuracion en el JSON

```json
{
  "features": { "scheduler": true },
  "schedule": {
    "timezone": "America/Bogota",
    "rules": [
      {
        "id": "rule-1",
        "instances": ["app-server", "db-server"],
        "startCron": "0 7 * * 1-5",
        "stopCron": "0 20 * * 1-5",
        "description": "L-V 7am a 8pm",
        "enabled": true
      }
    ]
  }
}
```

### Configuracion desde el panel

1. Abrir el panel de configuracion (icono ⚙️ en el header)
2. Expandir "Programacion"
3. Click "+ Agregar regla"
4. Seleccionar dias (L M Mi J V S D), horas de encendido/apagado, e instancias
5. Guardar

### Implementacion tecnica

- Se implementa con **EventBridge Scheduler** (sin costo adicional por regla)
- Las reglas cron se generan automaticamente desde el selector visual
- Solo se ejecutan las reglas con `"enabled": true`

---

## 4. Notificaciones

### Configuracion en el JSON

```json
{
  "features": { "notifications": true },
  "notifications": {
    "channels": [
      {
        "id": "ch-1",
        "type": "email",
        "name": "Admin Email",
        "config": {
          "to": "admin@empresa.com",
          "smtpHost": "smtp.gmail.com",
          "smtpPort": 587,
          "smtpUser": "alerts@empresa.com"
        },
        "events": ["started", "stopped", "error"],
        "enabled": true
      },
      {
        "id": "ch-2",
        "type": "telegram",
        "name": "Canal DevOps",
        "config": {
          "botToken": "123456:ABC-DEF",
          "chatId": "-1001234567890"
        },
        "events": ["started", "stopped", "scheduler_executed"],
        "enabled": true
      },
      {
        "id": "ch-3",
        "type": "teams",
        "name": "Teams Infra",
        "config": {
          "webhookUrl": "https://outlook.office.com/webhook/..."
        },
        "events": ["error"],
        "enabled": true
      }
    ]
  }
}
```

### Canales soportados

| Canal | Costo | Requisitos | Guia de configuracion |
|-------|-------|-----------|----------------------|
| Email (SMTP) | Gratis | Servidor SMTP (Gmail, Outlook, Mailgun, etc) | [setup-email-smtp.md](setup-email-smtp.md) |
| Telegram | Gratis | Bot token + Chat ID | [setup-telegram.md](setup-telegram.md) |
| Teams | Gratis | Webhook URL del canal | [setup-teams.md](setup-teams.md) |

> Consulta cada guia para el paso a paso de como obtener las credenciales necesarias.

### Eventos disponibles

| Evento | Se dispara cuando |
|--------|-------------------|
| `started` | Una instancia se enciende |
| `stopped` | Una instancia se apaga |
| `error` | Ocurre un error en una operacion |
| `scheduler_executed` | El scheduler ejecuta una regla |

### Gestion desde el panel

1. Abrir configuracion (⚙️)
2. Expandir "Notificaciones"
3. Agregar, editar, activar/desactivar o probar canales
4. El boton de avioncito envia una notificacion de prueba

---

## 5. Estimacion de Costos

### Como funciona

- Se registra cada evento start/stop con timestamp
- Se calcula el uptime acumulado del mes por instancia
- Se multiplica por el precio/hora del `instanceType` (tabla de precios On-Demand us-east-1)
- Se muestra el costo acumulado y proyeccion a fin de mes

### Configuracion

```json
{
  "features": { "costEstimate": true }
}
```

Ademas, cada instancia debe tener su `instanceType`:

```json
{
  "id": "app-server",
  "instanceType": "t3.medium",
  ...
}
```

### Almacenamiento del historial

- En produccion: DynamoDB (tabla con PK=instanceId, SK=timestamp, action=start|stop)
- En mock: Memoria del proceso (se regenera al reiniciar)

### Ver costos

1. Abrir configuracion (⚙️)
2. Expandir "Costos estimados"
3. Ver desglose por instancia con tipo, uptime, costo y proyeccion

---

## 6. Operaciones Comunes

### Agregar nueva instancia

1. Obtener el Instance ID y tipo desde la consola AWS
2. Editar `config/accounts.json`, agregar al array `instances`
3. Ejecutar `.\deploy.ps1`

### Agregar nueva cuenta

1. Crear el rol en la cuenta remota (ver docs/cross-account-setup.md)
2. Agregar la cuenta al array `accounts` con features habilitados
3. Crear API Key para el equipo
4. Ejecutar `.\deploy.ps1`

### Revocar acceso de un usuario

1. Eliminar su entrada de `apiKeys`
2. Ejecutar `.\deploy.ps1`

---

## 7. Seguridad

### Buenas practicas

- Usa keys largas y aleatorias: `openssl rand -hex 24`
- No compartas keys de admin con operadores
- Restringe `accounts` al minimo necesario por key
- Rota keys periodicamente
- No subas `accounts.json` a repositorios publicos

### Permisos IAM minimos para la Lambda

- `ec2:StartInstances`, `ec2:StopInstances`, `ec2:DescribeInstances`
- `ssm:SendCommand`, `ssm:GetCommandInvocation`
- `sts:AssumeRole` (solo para cross-account)

---

## 8. Troubleshooting

### Usuario no ve el scheduler
- Verificar que `features.scheduler: true` en la cuenta
- Verificar que su API Key tenga `scheduler.view: true` (o sea admin)

### Notificaciones no se envian
- Verificar que el canal tenga `enabled: true`
- Verificar que el evento este en la lista `events` del canal
- Probar con el boton de test en el panel

### Costos muestran $0
- Verificar que `features.costEstimate: true`
- Verificar que las instancias tengan `instanceType` configurado
- Los costos se calculan desde el historial de actividad del mes actual

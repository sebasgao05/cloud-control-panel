# Configuracion - Cloud Control Panel

## Archivo de configuracion

Toda la configuracion vive en un solo archivo: `config/accounts.json`.
Este archivo se empaqueta con la Lambda en cada deploy.

| Archivo | Contenido | Commitear? |
|---------|-----------|------------|
| `config/accounts.example.json` | Plantilla multi-cuenta (referencia) | SI |
| `config/accountsMono.example.json` | Plantilla mono-cuenta (referencia) | SI |
| `config/accounts.json` | Config real (cuentas, keys, instancias) | **NO** (.gitignore) |

---

## Estructura completa del archivo

```json
{
  "settings": { ... },
  "apiKeys": { ... },
  "accounts": [ ... ]
}
```

---

## Settings

```json
"settings": {
  "defaultRegion": "us-east-1",
  "pollIntervalSeconds": 30,
  "timezone": "America/Bogota"
}
```

---

## API Keys

```json
"apiKeys": {
  "key-admin-secreta": {
    "name": "Admin Principal",
    "role": "admin",
    "accounts": ["*"]
  },
  "key-operador": {
    "name": "Equipo Desarrollo",
    "role": "operator",
    "accounts": ["sanidad", "nuvu-10"],
    "scheduler": {
      "view": true,
      "edit": false
    }
  }
}
```

### Campos

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `name` | string | Nombre visible en el panel |
| `role` | string | `"admin"` o `"operator"` |
| `accounts` | array | IDs de cuentas permitidas, o `["*"]` para todas |
| `scheduler` | object | (Opcional) Permisos del scheduler para operadores |
| `scheduler.view` | boolean | Si puede ver los horarios |
| `scheduler.edit` | boolean | Si puede crear/editar reglas (implica view) |

### Reglas de permisos

- **Admin**: Siempre ve y edita todo (scheduler, notificaciones, costos)
- **Operador sin `scheduler`**: No ve el scheduler
- **Operador con `edit: true`**: Ve y edita (no necesita `view: true`)
- **Operador con `view: true, edit: false`**: Solo lectura
- Notificaciones y costos: Solo visibles para admin

---

## Accounts

```json
{
  "id": "sanidad",
  "name": "SAN - TEST - Sanidad Wisse",
  "awsAccountId": "111111111111",
  "region": "us-east-1",
  "crossAccountRoleArn": "arn:aws:iam::111111111111:role/CloudControlRemoteAccess",
  "features": {
    "scheduler": true,
    "notifications": true,
    "costEstimate": true
  },
  "notifications": { ... },
  "schedule": { ... },
  "instances": [ ... ],
  "groups": [ ... ]
}
```

### Campos

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `id` | string | Slug unico (sin espacios) |
| `name` | string | Nombre visible |
| `awsAccountId` | string | ID de la cuenta AWS |
| `region` | string | Region AWS |
| `crossAccountRoleArn` | string/null | ARN del rol remoto (null si es cuenta local) |
| `features` | object | Features habilitados para esta cuenta |

### Features disponibles

| Feature | Descripcion |
|---------|-------------|
| `scheduler` | Habilita programacion automatica |
| `notifications` | Habilita canales de notificacion |
| `costEstimate` | Habilita estimacion de costos |

---

## Instances

```json
{
  "id": "app-server",
  "name": "App Server",
  "instanceId": "i-0abc123def456789",
  "instanceType": "t3.medium",
  "description": "Servidor principal de aplicacion",
  "dashboardPort": 5476,
  "group": "core-servers"
}
```

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `id` | string | Slug unico dentro de la cuenta |
| `name` | string | Nombre visible |
| `instanceId` | string | ID real de EC2 (empieza con i-) |
| `instanceType` | string | Tipo EC2 (para estimacion de costos) |
| `description` | string | Texto descriptivo |
| `dashboardPort` | number/null | Puerto del dashboard (null si no tiene) |
| `group` | string/null | ID del grupo (null si es independiente) |

---

## Groups

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

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `id` | string | Slug unico |
| `name` | string | Nombre visible |
| `description` | string | Descripcion del grupo |
| `color` | string | Color hex para la etiqueta visual |
| `startOrder` | array | Orden de encendido (IDs de instancias) |
| `stopOrder` | array | Orden de apagado (IDs de instancias) |

---

## Schedule

```json
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
```

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `timezone` | string | Zona horaria para las reglas |
| `rules[].id` | string | ID unico de la regla |
| `rules[].instances` | array | IDs de instancias afectadas |
| `rules[].startCron` | string | Cron de encendido (min hour * * dow) |
| `rules[].stopCron` | string | Cron de apagado |
| `rules[].description` | string | Descripcion legible |
| `rules[].enabled` | boolean | Si la regla esta activa |

---

## Notifications

```json
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
    }
  ]
}
```

### Tipos de canal

| Tipo | Campos config requeridos |
|------|-------------------------|
| `email` | `to`, `smtpHost`, `smtpPort`, `smtpUser` |
| `telegram` | `botToken`, `chatId` |
| `teams` | `webhookUrl` |

### Eventos

| Evento | Descripcion |
|--------|-------------|
| `started` | Instancia encendida |
| `stopped` | Instancia apagada |
| `error` | Error en operacion |
| `scheduler_executed` | Scheduler ejecuto una regla |

---

## Flujo de trabajo para cambios

1. Editar `config/accounts.json`
2. Ejecutar `.\deploy.ps1`
3. Listo — la Lambda toma la nueva configuracion

## Seguridad

- **NUNCA commitear** `config/accounts.json` (contiene API keys)
- El archivo esta en `.gitignore` por defecto
- Las API keys deben ser strings largos y aleatorios en produccion
- Genera keys con: `openssl rand -hex 24`

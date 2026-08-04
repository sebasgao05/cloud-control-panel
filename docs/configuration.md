# Configuracion - Cloud Control Panel

## Archivo de configuracion

Toda la configuracion (cuentas, instancias, API keys) vive en un solo archivo: `config/accounts.json`.
Este archivo se empaqueta con la Lambda en cada deploy.

| Archivo | Contenido | Commitear? |
|---------|-----------|------------|
| `config/accounts.example.json` | Plantilla multi-cuenta (referencia) | SI |
| `config/accountsMono.example.json` | Plantilla mono-cuenta (referencia) | SI |
| `config/accounts.json` | Config real (cuentas, keys, instancias) | **NO** (está en .gitignore) |

## Setup inicial

Segun tu caso, copia la plantilla correspondiente:

**Multi-cuenta** (varias cuentas AWS, roles cross-account):
```bash
copy config\accounts.example.json config\accounts.json
```

**Mono-cuenta** (una sola cuenta AWS, sin roles remotos):
```bash
copy config\accountsMono.example.json config\accounts.json
```

Luego edita `config/accounts.json` con tus datos reales (IDs de instancias, ARNs, API keys, etc).

---

## Estructura del archivo

```json
{
  "settings": { ... },
  "apiKeys": { ... },
  "accounts": [ ... ]
}
```

## Settings

```json
"settings": {
  "defaultRegion": "us-east-1",
  "pollIntervalSeconds": 30,
  "timezone": "America/Bogota"
}
```

## API Keys

Cada key permite acceso al panel. Puedes tener 1 o N keys.
Las keys van directamente en `config/accounts.json`.

```json
"apiKeys": {
  "tu-key-secreta-aqui": {
    "name": "Nombre del usuario/equipo",
    "role": "admin",
    "accounts": ["*"]
  },
  "otra-key-limitada": {
    "name": "Equipo X",
    "role": "operator",
    "accounts": ["sanidad"]
  }
}
```

- `role`: "admin" o "operator" (mismo acceso por ahora, preparado para futuro)
- `accounts`: lista de IDs de cuenta a los que tiene acceso, o ["*"] para todas

## Accounts

Cada cuenta agrupa instancias y opcionalmente grupos.

```json
{
  "id": "sanidad",
  "name": "SAN - TEST - Sanidad Wisse",
  "awsAccountId": "111111111111",
  "region": "us-east-1",
  "crossAccountRoleArn": "arn:aws:iam::111111111111:role/CloudControlRemoteAccess",
  "instances": [...],
  "groups": [...]
}
```

- `id`: identificador unico (slug, sin espacios)
- `crossAccountRoleArn`: null si es la misma cuenta donde se despliega la Lambda

## Instances

```json
{
  "id": "san-app-server",
  "name": "App Server",
  "instanceId": "i-0abc123def456",
  "description": "Servidor principal",
  "dashboardPort": 5476,
  "group": "sanidad-core"
}
```

- `id`: identificador unico dentro de la cuenta
- `instanceId`: ID real de la instancia EC2
- `dashboardPort`: puerto del dashboard (null si no tiene)
- `group`: ID del grupo al que pertenece (null si es independiente)

## Groups

```json
{
  "id": "sanidad-core",
  "name": "Core Sanidad",
  "description": "Se encienden/apagan juntas",
  "startOrder": ["san-db-server", "san-app-server"],
  "stopOrder": ["san-app-server", "san-db-server"]
}
```

- `startOrder`: orden en que se encienden (DB primero, app despues)
- `stopOrder`: orden en que se apagan (app primero, DB despues)

---

## Flujo de trabajo para cambios

1. Editar `config/accounts.json`
2. Ejecutar `.\deploy.ps1`
3. Listo - la Lambda toma la nueva configuracion

## Seguridad

- **NUNCA commitear** `config/accounts.json` (contiene API keys y datos sensibles)
- El archivo está en `.gitignore` por defecto
- Solo los archivos `.example` se versionan como referencia
- Las API keys deben ser strings largos y aleatorios en produccion

## Mono-cuenta vs Multi-cuenta

La logica del backend es la misma. La diferencia es solo configuracion:

- **Mono-cuenta**: `crossAccountRoleArn` es `null` → Lambda usa sus propias credenciales
- **Multi-cuenta**: `crossAccountRoleArn` tiene un ARN → Lambda hace `STS AssumeRole` para operar en la cuenta remota

No hay un flag o modo especial. Simplemente configura las cuentas con o sin ARN de rol.

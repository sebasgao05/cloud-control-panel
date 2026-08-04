# Configuracion - Cloud Control Panel

## Archivo de configuracion

Toda la configuracion vive en `config/accounts.json`. Este archivo se empaqueta
con la Lambda en cada deploy.

## Estructura

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

## Flujo de trabajo para cambios

1. Editar `config/accounts.json`
2. Ejecutar `.\deploy.ps1`
3. Listo - la Lambda toma la nueva configuracion

## Ejemplos

### Mono-cuenta (1 cuenta, 1 instancia)
```json
{
  "settings": { "defaultRegion": "us-east-1" },
  "apiKeys": {
    "mi-super-key": { "name": "Admin", "role": "admin", "accounts": ["*"] }
  },
  "accounts": [{
    "id": "principal",
    "name": "Mi Cuenta",
    "awsAccountId": "123456789012",
    "region": "us-east-1",
    "crossAccountRoleArn": null,
    "instances": [{
      "id": "server-1",
      "name": "Servidor Principal",
      "instanceId": "i-0abc123",
      "description": "Mi servidor",
      "dashboardPort": 5476,
      "group": null
    }],
    "groups": []
  }]
}
```

### Multi-cuenta (2 cuentas, varias instancias, 1 grupo)
Ver el archivo `config/accounts.json` incluido como ejemplo.

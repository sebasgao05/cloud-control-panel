# Arquitectura - Cloud Control Panel

## Vision General

Cloud Control Panel es un panel serverless para gestionar instancias EC2 en multiples cuentas AWS.
Permite encender, apagar, actualizar, programar, monitorear costos y recibir notificaciones,
todo desde una SPA liviana servida via CloudFront.

## Stack Tecnologico

| Capa | Tecnologia | Justificacion |
|------|-----------|---------------|
| Frontend | HTML + CSS + JS (ES6 Modules, Vanilla) | Sin build step, deploy directo a S3, modular y ligero |
| Backend | Python 3.13 (Lambda, arm64) | Cold start rapido, AWS SDK nativo, validacion con Pydantic |
| API | API Gateway HTTP API v2 | Bajo costo, baja latencia, CORS integrado, throttling |
| CDN | CloudFront | HTTPS, cache, routing frontend/API, OAC |
| Storage | S3 | Hosting estatico del frontend (privado, solo OAC) |
| Config DB | DynamoDB (single-table, PAY_PER_REQUEST) | Config dinamico, activity log, API keys hasheadas |
| Scheduler | EventBridge Scheduler | Cron automatico start/stop sin costo adicional |
| Updates | SSM (Systems Manager) | RunCommand para git pull + restart en instancias |
| Cross-account | STS + IAM Roles | AssumeRole para operar en cuentas remotas |
| IaC | CloudFormation (template.yaml) | Infraestructura completa en un archivo |
| Auth | API Key + bcrypt + DynamoDB | Roles: superadmin, admin, operator |
| Validacion | Pydantic v2 | Modelos estrictos para todos los request bodies |
| CI/CD | GitHub Actions | Lint → Test → Deploy (main), Release (tags) |
| Linter | Ruff | Check + format del backend Python |
| Tests | pytest + moto + coverage | Unit tests con DynamoDB mock + integration tests |

## Diagrama de Flujo Principal

```
+------------------+
|     Usuario      |
|    (Browser)     |
+--------+---------+
         | HTTPS
         v
+------------------+
|   CloudFront     | ── Cache + HTTPS + Routing + OAC
+--------+---------+
         |
         +── /* (frontend)──────────────+
         |                              |
         |                              v
         |                     +------------------+
         |                     |       S3         |
         |                     | HTML + JS + CSS  |
         |                     | (ES6 Modules)    |
         |                     +------------------+
         |
         +── /api/* (backend)──────────+
                                       |
                                       v
                              +------------------+
                              |  API Gateway v2  |
                              |  HTTP API        |
                              |  (CORS+Throttle) |
                              +--------+---------+
                                       |
                                       v
                              +------------------+
                              |     Lambda       |
                              |  Python 3.13     |
                              |  arm64 / 256MB   |
                              +--------+---------+
                                       |
          +----------------------------+----------------------------+
          |              |             |             |              |
          v              v             v             v              v
   +-----------+  +-----------+  +---------+  +----------+  +-----------+
   | DynamoDB  |  |    EC2    |  |   SSM   |  |   STS    |  | EventBridge|
   | (config,  |  | (start/  |  | (update |  | (Assume  |  | Scheduler  |
   |  keys,    |  |  stop,   |  |  via    |  |  Role)   |  | (cron auto)|
   |  activity)|  | describe)|  | RunCmd) |  |          |  |            |
   +-----------+  +-----------+  +---------+  +----+-----+  +-----+-----+
                                                   |               |
                                                   v               v
                                             +-----------+    +---------+
                                             | EC2 Remota|    | Lambda  |
                                             | (cuenta   |    | (invoca |
                                             |  remota)  |    |  a hora)|
                                             +-----------+    +---------+

                              +------ Notificaciones ------+
                              |              |             |
                              v              v             v
                         +--------+    +----------+   +-------+
                         |  SMTP  |    | Telegram |   | Teams |
                         | Email  |    |   Bot    |   |Webhook|
                         +--------+    +----------+   +-------+
```

## Modulos del Backend

```
backend/
├── app.py              <- Lambda handler: routing de requests a handlers
├── auth.py             <- Autenticacion bcrypt, RBAC, permisos scheduler
├── ec2_ops.py          <- EC2 start/stop/describe, SSM update, cross-account, grupos
├── scheduler.py        <- EventBridge CRUD, cron conversion, activity log
├── notifications.py    <- Email (SMTP), Telegram (HTTP), Teams (webhook)
├── admin.py            <- CRUD cuentas/instancias/grupos/keys, costos EC2
├── utils.py            <- DynamoDB helpers, migraciones, pricing table, response helper
└── validators.py       <- Modelos Pydantic para validacion de requests
```

## Modulos del Frontend (ES6)

```
frontend/
├── app.js              <- Entry point, imports + window bindings
├── index.html          <- SPA (pantallas: auth, accounts, instances, groups, detail)
├── style.css           <- Dark theme responsive
└── js/
    ├── utils.js        <- Estado global, API helper (fetch + auth header), toast, escape
    ├── auth.js         <- Login/logout, localStorage persistence
    ├── navigation.js   <- showScreen(), goBack, routing entre vistas
    ├── accounts.js     <- Lista cuentas, CRUD cuentas (superadmin)
    ├── instances.js    <- Lista instancias, detalle, start/stop/update, activity log
    ├── groups.js       <- Grupos, encendido/apagado ordenado, CRUD
    ├── scheduler.js    <- Visual scheduler (day/time picker), cron generation, rule CRUD
    ├── notifications.js <- Canal CRUD (email/telegram/teams), toggle, test
    ├── costs.js        <- Estimacion costos con barras y proyeccion mensual
    ├── keys.js         <- API Key management, creacion/eliminacion/permisos
    ├── admin.js        <- CRUD instancias, asignacion de operadores a cuentas
    └── settings.js     <- Panel lateral, export/import config JSON
```

## Modelo de Datos (DynamoDB - Single Table)

| PK | SK | Contenido |
|----|-----|-----------|
| `CONFIG` | `SETTINGS` | Region, timezone, poll interval |
| `CONFIG` | `APIKEY#{uuid}` | hash (bcrypt), name, role, accounts[], scheduler{} |
| `CONFIG` | `KEYS_MIGRATED` | Flag de migracion bcrypt completada |
| `CONFIG` | `ACCOUNT#{id}` | name, awsAccountId, region, crossAccountRoleArn, features{} |
| `ACCOUNT#{id}` | `INSTANCE#{id}` | name, instanceId, description, dashboardPort, group |
| `ACCOUNT#{id}` | `GROUP#{id}` | name, color, description, startOrder[], stopOrder[] |
| `ACCOUNT#{id}` | `SCHEDULE#{id}` | startCron, stopCron, instances[], enabled, description |
| `ACCOUNT#{id}` | `CHANNEL#{id}` | type, name, config{}, events[], enabled |
| `ACTIVITY#{id}` | `{timestamp}` | action, user, instanceIds[], ruleId? |

## Flujo de Autenticacion

```
1. Usuario ingresa API Key en el frontend
2. Frontend envia X-Api-Key header en cada request
3. Lambda itera keys en DynamoDB
4. Para cada key, compara con bcrypt.checkpw(provided, stored_hash)
5. Si match -> retorna user_info (name, role, accounts[], scheduler{})
6. Filtra datos/acciones segun rol y cuentas asignadas
7. Si no match -> 401 Unauthorized
```

### Migraciones automaticas

- **JSON → DynamoDB**: Si DynamoDB esta vacio y existe `accounts.json`, migra automaticamente
- **Plaintext → bcrypt**: Keys legacy se migran a bcrypt hash en el primer request (flag `KEYS_MIGRATED`)

## Flujo del Scheduler

```
1. Superadmin crea regla en el panel (selector visual: dias + horas + instancias)
2. Frontend genera request con cron expression (ej: "0 7 * * 1-5")
3. Lambda valida con Pydantic (ScheduleRule model)
4. Lambda convierte cron a formato EventBridge: cron(0 7 ? * MON-FRI *)
5. Lambda crea/actualiza EventBridge Schedule (start + stop) con timezone
6. EventBridge invoca Lambda a la hora programada con payload:
   { source: "scheduler", action: "start/stop", accountId, instanceIds, ruleId }
7. Lambda ejecuta start/stop en las instancias (incluyendo cross-account)
8. Se registra en activity log + se envia notificacion a canales habilitados
```

## Flujo de Notificaciones

```
1. Se ejecuta una accion (manual o scheduler)
2. Lambda lee canales de la cuenta desde DynamoDB
3. Para cada canal habilitado que matchee el evento (started/stopped/error/scheduler_executed):
   - Email: SMTP directo (smtplib + starttls)
   - Telegram: HTTP POST a api.telegram.org/bot{token}/sendMessage
   - Teams: HTTP POST a webhook URL con JSON {text: ...}
4. Mensaje incluye: recurso, cuenta, quien lo hizo, rol, fecha UTC
5. Errores de envio se loguean pero no bloquean la operacion
```

## Flujo de Updates via SSM

```
1. Usuario presiona "Update" en una instancia running
2. Lambda obtiene SSM client (con cross-account si aplica)
3. Ejecuta ssm.send_command con:
   - DocumentName: AWS-RunShellScript
   - Commands: cd ~/app && git pull && bash install.sh; systemctl restart app
   - Timeout: 600s
4. Retorna commandId al frontend para tracking
```

## Flujo de Costos

```
1. Frontend solicita GET /accounts/{id}/costs
2. Lambda obtiene estado real de EC2 (describe_instances)
3. Calcula uptime basado en LaunchTime de instancias running
4. Aplica tabla de precios On-Demand (EC2_PRICING en utils.py)
5. Retorna: costo acumulado, horas uptime, rate/hora, proyeccion mensual
```

## Seguridad

### Autenticacion
- API Keys almacenadas como hash bcrypt en DynamoDB
- UUID interno como key_id (separado del valor de la key)
- Key plaintext solo se muestra una vez al crear (nunca mas recuperable)
- Listado muestra solo preview (primeros 8 chars del UUID)

### Autorizacion (RBAC)
- Superadmin: acceso total, CRUD completo, export/import
- Admin: start/stop, costos, gestionar operadores
- Operator: start/stop solo en cuentas asignadas, scheduler segun config

### Protecciones
- No se puede crear superadmin desde el panel (solo via JSON inicial)
- No se puede eliminar tu propia API Key
- Admin no puede escalar a admin/superadmin (solo crear operators)
- Superadmin no puede eliminar a otro superadmin
- Validacion Pydantic en todos los endpoints mutables
- Validacion regex en path parameters (max 50 chars, alfanumerico + guiones)
- Errores sanitizados (nunca se exponen detalles internos)

### Infraestructura
- HTTPS forzado via CloudFront (redirect-to-https)
- S3 privado con Origin Access Control (OAC)
- CORS restringido a origen CloudFront + localhost:8080
- API throttling: burst 200, rate 100 req/s
- Cross-account con roles IAM de minimo privilegio
- Lambda con least-privilege policy (solo recursos necesarios)

## CI/CD Pipeline

```
Pull Request a main:
  ┌─────────┐    ┌──────────┐    ┌───────────────┐    ┌───────────────┐
  │  Lint   │───>│   Test   │───>│ Deploy Staging│───>│ Destroy (auto)│
  │ (ruff)  │    │ (pytest  │    │ (stack efímero│    │ (al cerrar/   │
  │         │    │  + cov)  │    │  por cada PR) │    │  mergear PR)  │
  └─────────┘    └──────────┘    └───────────────┘    └───────────────┘

Push a main (post-merge):
  ┌─────────┐    ┌──────────┐    ┌─────────────┐
  │  Lint   │───>│   Test   │───>│   Deploy     │
  │ (ruff)  │    │ (pytest  │    │  Production  │
  │         │    │  + cov)  │    │ (ccp-main)   │
  └─────────┘    └──────────┘    └─────────────┘

Tag v*.*.*:
  ┌──────────────────┐
  │  GitHub Release  │
  │ (release notes)  │
  └──────────────────┘
```

### Staging efímero

Cada PR crea un stack `cloud-control-ccp-staging-prN` completamente aislado:
- DynamoDB, Lambda, API Gateway, S3, CloudFront propios
- Se comenta la URL de staging en el PR para testing
- Se destruye automaticamente al cerrar o mergear el PR
- Usa `accounts.example.json` como config (keys de prueba)

### Pipeline de Deploy

```
1. pip install (dependencias para Linux arm64: --platform manylinux2014_aarch64)
2. cp config/accounts.json backend/ (solo para primer deploy/migración)
3. aws cloudformation package (template.yaml → S3)
4. aws cloudformation deploy (stack con CAPABILITY_NAMED_IAM)
5. aws s3 sync frontend/ → S3 bucket
6. aws cloudfront create-invalidation (/*)
7. Cleanup (elimina accounts.json + dependencias pip del directorio backend/)
```

## API Endpoints

| Metodo | Path | Rol minimo | Descripcion |
|--------|------|-----------|-------------|
| GET | /api/accounts | operator | Listar cuentas accesibles |
| POST | /api/accounts | superadmin | Crear cuenta |
| DELETE | /api/accounts/{id} | superadmin | Eliminar cuenta |
| GET | /api/accounts/{id}/instances | operator | Listar instancias + estado |
| POST | /api/accounts/{id}/instances | superadmin | Crear instancia |
| DELETE | /api/accounts/{id}/instances/{id} | superadmin | Eliminar instancia |
| GET | /api/accounts/{id}/instances/{id}/status | operator | Estado en vivo |
| POST | /api/accounts/{id}/instances/{id}/start | operator | Encender instancia |
| POST | /api/accounts/{id}/instances/{id}/stop | operator | Apagar instancia |
| POST | /api/accounts/{id}/instances/{id}/update | operator | Update via SSM |
| GET | /api/accounts/{id}/instances/{id}/dashboard-url | operator | URL del dashboard |
| POST | /api/accounts/{id}/groups | superadmin | Crear grupo |
| DELETE | /api/accounts/{id}/groups/{id} | superadmin | Eliminar grupo |
| GET | /api/accounts/{id}/groups/{id}/status | operator | Estado del grupo |
| POST | /api/accounts/{id}/groups/{id}/start | operator | Encender grupo (ordenado) |
| POST | /api/accounts/{id}/groups/{id}/stop | operator | Apagar grupo (ordenado) |
| GET | /api/accounts/{id}/schedule | operator* | Ver programacion |
| PUT | /api/accounts/{id}/schedule | superadmin | Actualizar programacion |
| GET | /api/accounts/{id}/notifications | superadmin | Ver canales |
| PUT | /api/accounts/{id}/notifications | superadmin | Actualizar canales |
| POST | /api/accounts/{id}/notifications/test | superadmin | Probar canal |
| GET | /api/accounts/{id}/costs | admin | Estimacion de costos |
| GET | /api/accounts/{id}/activity | operator | Ver activity log |
| DELETE | /api/accounts/{id}/activity | admin | Limpiar activity log |
| GET | /api/keys/list | admin | Listar API Keys |
| POST | /api/keys/create | admin | Crear API Key |
| PUT | /api/keys/{id}/accounts | superadmin | Actualizar acceso de key |
| DELETE | /api/keys/{id} | admin | Eliminar API Key |
| GET | /api/config | superadmin | Exportar config completa |
| PUT | /api/config | superadmin | Importar config (reemplaza todo) |
| POST | /api/migrate | admin | Forzar migracion JSON→DynamoDB |

*operator: acceso a scheduler segun campo `scheduler.view` de la key

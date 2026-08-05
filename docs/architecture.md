# Arquitectura - Cloud Control Panel

## Vision General

Cloud Control Panel es un panel serverless para gestionar instancias EC2 en multiples cuentas AWS.
Permite encender, apagar, programar, monitorear costos y recibir notificaciones.

## Stack Tecnologico

| Capa | Tecnologia | Justificacion |
|------|-----------|---------------|
| Frontend | HTML + CSS + JS (Vanilla) | Sin build step, deploy directo a S3, <25KB |
| Backend | Python 3.13 (Lambda) | Cold start rapido, AWS SDK nativo |
| API | API Gateway HTTP API v2 | Bajo costo, baja latencia |
| CDN | CloudFront | HTTPS, cache, routing frontend/API |
| Storage | S3 | Hosting estatico del frontend |
| Config DB | DynamoDB | Config dinamico, activity log, sin servidor |
| Scheduler | EventBridge Scheduler | Cron automatico sin costo adicional |
| IaC | CloudFormation | Infraestructura como codigo |
| Auth | API Key + DynamoDB | Roles: superadmin, admin, operator |

## Diagrama de Flujo

```
+-------------+
|   Usuario   |
|  (Browser)  |
+------+------+
       | HTTPS
       v
+--------------+
|  CloudFront  |--- Cache + HTTPS + Routing
+------+-------+
       |
       +-- /* (frontend)
       |        |
       |        v
       |   +---------+
       |   |   S3    | HTML + JS + CSS
       |   +---------+
       |
       +-- /api/* (backend)
                |
                v
       +----------------+
       |  API Gateway   | HTTP API v2
       +-------+--------+
               |
               v
       +----------------+
       |    Lambda      | Python 3.13 (app.py)
       +-------+--------+
               |
               +-- DynamoDB (config, keys, activity log)
               |
               +-- EC2 (start/stop/describe)
               |
               +-- SSM (update via RunCommand)
               |
               +-- STS (AssumeRole para cross-account)
               |
               +-- EventBridge Scheduler (crear/eliminar schedules)
               |
               +-- SMTP / Telegram API / Teams Webhook (notificaciones)
```

## Modelo de Datos (DynamoDB - Single Table)

| PK | SK | Contenido |
|----|-----|-----------|
| `CONFIG` | `SETTINGS` | Region, timezone, poll interval |
| `CONFIG` | `APIKEY#{uuid}` | name, role, accounts[], scheduler{} |
| `CONFIG` | `ACCOUNT#{id}` | name, awsAccountId, region, features{} |
| `ACCOUNT#{id}` | `INSTANCE#{id}` | name, instanceId, description, port, group |
| `ACCOUNT#{id}` | `GROUP#{id}` | name, color, startOrder[], stopOrder[] |
| `ACCOUNT#{id}` | `SCHEDULE#{id}` | startCron, stopCron, instances[], enabled |
| `ACCOUNT#{id}` | `CHANNEL#{id}` | type, name, config{}, events[], enabled |
| `ACTIVITY#{id}` | `{timestamp}` | action, user, instanceIds[] |

## Flujo de Autenticacion

```
1. Usuario ingresa API Key en el frontend
2. Frontend envia X-Api-Key header en cada request
3. Lambda lee keys de DynamoDB
4. Si key existe -> filtra datos segun rol y cuentas asignadas
5. Si no existe -> 401 Unauthorized
```

## Flujo del Scheduler

```
1. Superadmin crea regla en el panel (dias + horas + instancias)
2. Lambda genera cron expression y crea EventBridge Schedule
3. EventBridge invoca Lambda a la hora programada
4. Lambda ejecuta start/stop en las instancias
5. Se registra en activity log + se envia notificacion
```

## Flujo de Notificaciones

```
1. Se ejecuta una accion (manual o scheduler)
2. Lambda lee canales configurados de la cuenta
3. Para cada canal habilitado que matchee el evento:
   - Email: SMTP directo (smtplib)
   - Telegram: HTTP POST a api.telegram.org
   - Teams: HTTP POST a webhook URL
4. Mensaje incluye: recurso, cuenta, quien lo hizo, rol, fecha
```

## Seguridad

- API Keys almacenadas en DynamoDB (no en codigo)
- Permisos por rol (superadmin > admin > operator)
- Proteccion contra escalacion de privilegios
- Proteccion contra auto-eliminacion
- Cross-account con IAM roles de minimo privilegio
- HTTPS forzado via CloudFront
- S3 privado con OAC
- No se puede crear superadmin desde el panel

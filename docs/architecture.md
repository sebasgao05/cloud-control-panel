# Arquitectura - Cloud Control Panel

## Vision General

Cloud Control Panel es un panel de control serverless para gestionar instancias EC2
en una o multiples cuentas AWS. Permite encender, apagar, actualizar y monitorear
instancias de forma centralizada.

## Stack Tecnologico

| Capa | Tecnologia | Justificacion |
|------|-----------|---------------|
| Frontend | HTML + CSS + JS (Vanilla) | Sin build step, deploy directo a S3, <20KB total |
| Backend | Python 3.13 (Lambda) | Cold start rapido, sin frameworks, AWS SDK nativo |
| API | API Gateway HTTP API v2 | Bajo costo, baja latencia, routing simple |
| CDN | CloudFront | HTTPS, cache, routing frontend/API |
| Storage | S3 | Hosting estatico del frontend |
| IaC | CloudFormation (SAM) | Infraestructura como codigo, deploy reproducible |
| Auth | API Key en config | Simple, sin Cognito, sin base de datos |

## Diagrama de Flujo

```
+-------------+
|   Usuario   |
|  (Browser)  |
+------+------+
       | HTTPS
       v
+--------------+
|  CloudFront  |-------- Cache + HTTPS + Routing
+------+-------+
       |
       +-- /index.html, /app.js, /style.css
       |        |
       |        v
       |   +---------+
       |   |   S3    | Frontend estatico
       |   +---------+
       |
       +-- /api/*
                |
                v
       +----------------+
       |  API Gateway   | HTTP API v2
       |  (HTTP API)    |
       +-------+--------+
               |
               v
       +----------------+
       |    Lambda      | Python 3.13
       |  (app.py)      |
       +-------+--------+
               |
               +-- Auth: Valida X-Api-Key contra accounts.json
               |
               +-- Cuenta local (sin crossAccountRoleArn)
               |        |
               |        v
               |   +---------+
               |   |   EC2   | DescribeInstances, Start, Stop
               |   |   SSM   | SendCommand (update)
               |   +---------+
               |
               +-- Cuenta remota (con crossAccountRoleArn)
                        |
                        v
                   +---------+
                   |   STS   | AssumeRole
                   +----+----+
                        |
                        v
                   +---------+
                   |   EC2   | En cuenta remota
                   |   SSM   |
                   +---------+
```

## Flujo de Autenticacion

```
1. Usuario ingresa API Key en el frontend
2. Frontend envia X-Api-Key en cada request
3. Lambda recibe request, lee accounts.json
4. Busca la key en apiKeys
5. Si existe -> retorna datos filtrados por permisos
6. Si no existe -> 401 Unauthorized
```

## Flujo de Operacion (Encender instancia)

```
1. Usuario hace click en "Encender"
2. Frontend: POST /api/accounts/{id}/instances/{id}/start
3. Lambda:
   a. Valida API Key
   b. Busca cuenta en config
   c. Si crossAccountRoleArn -> STS AssumeRole
   d. Llama ec2.start_instances()
   e. Retorna 200 OK
4. Frontend: Muestra toast + refresca status en 3s
```

## Estructura de Archivos

```
cloud-control-panel/
|-- config/
|   +-- accounts.json        <- Configuracion central (admin edita aqui)
|-- backend/
|   |-- app.py               <- Lambda handler
|   +-- requirements.txt     <- Dependencias Python (solo boto3 en Lambda)
|-- frontend/
|   |-- index.html           <- SPA principal
|   |-- app.js               <- Logica del frontend
|   +-- style.css            <- Estilos
|-- docs/
|   |-- architecture.md      <- Este documento
|   |-- admin-guide.md       <- Guia para administradores
|   |-- user-guide.md        <- Guia para usuarios
|   |-- configuration.md     <- Referencia de configuracion
|   +-- cross-account-setup.md <- Setup multi-cuenta
|-- mock/
|   +-- server.py            <- Servidor mock para desarrollo local
|-- template.yaml            <- CloudFormation template
|-- deploy.ps1               <- Script de despliegue
+-- samconfig.toml           <- Configuracion SAM
```

## Seguridad

- API Keys: Definidas en config, no en DB ni en UI
- Permisos por cuenta: Cada key solo ve las cuentas asignadas
- Cross-account: Roles IAM con minimo privilegio
- HTTPS: Forzado via CloudFront
- Sin datos persistentes: No hay DB, todo es stateless
- S3 privado: Solo accesible via CloudFront OAC

## Escalabilidad

- Agregar cuenta: Editar JSON + re-deploy (~3 min)
- Agregar instancia: Editar JSON + re-deploy
- Agregar usuario: Agregar key al JSON + re-deploy
- Cold start Lambda: ~200ms (sin framework)
- Limite instancias: Sin limite tecnico, limitado por describe_instances batch (max 1000)

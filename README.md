# Cloud Control Panel

Panel de control serverless para gestionar instancias EC2 en una o multiples cuentas AWS.

## Caracteristicas

- **Multi-cuenta**: Gestiona instancias en diferentes cuentas AWS desde un solo panel
- **Multi-instancia**: Controla N instancias por cuenta
- **Grupos**: Agrupa instancias para encender/apagar juntas con orden definido y colores personalizados
- **Scheduler**: Programacion automatica de encendido/apagado con EventBridge (selector visual de dias y horas)
- **Notificaciones**: Alertas por Email (SMTP), Telegram y Microsoft Teams con detalle de quien ejecuto la accion
- **Estimacion de costos**: Seguimiento de uptime y costo estimado por instancia basado en datos reales de EC2
- **Roles y permisos**: Superadmin, Admin y Operador con permisos diferenciados
- **DynamoDB**: Configuracion dinamica sin necesidad de re-deploy para cambios
- **CRUD desde el panel**: Crear/editar/eliminar cuentas, instancias, grupos y API Keys desde la UI
- **Export/Import**: Exportar e importar la configuracion completa como JSON
- **Activity log**: Historial de acciones persistente en DynamoDB
- **Estado en tiempo real**: Visualizacion del estado de cada instancia con auto-refresh
- **Cross-account**: Usa roles IAM para operar instancias en cuentas remotas
- **Serverless**: Lambda + API Gateway + CloudFront + S3 + DynamoDB + EventBridge

## Arquitectura

```
Usuario -> CloudFront -> S3 (frontend)
                      -> API Gateway -> Lambda -> DynamoDB (config dinamico)
                                               -> EC2 (misma cuenta)
                                               -> STS AssumeRole -> EC2 (cuenta remota)
                                               -> EventBridge Scheduler (cron automatico)
                                               -> SMTP / Telegram / Teams (notificaciones)
```

## Roles y Permisos

| Accion | Superadmin | Admin | Operador |
|--------|:---:|:---:|:---:|
| Start/Stop instancias | ✅ | ✅ | ✅ |
| Ver costos | ✅ | ✅ | ❌ |
| Crear API Keys operadores | ✅ | ✅ | ❌ |
| Eliminar operadores | ✅ | ✅ | ❌ |
| Programacion (scheduler) | ✅ | ❌ | segun config |
| Notificaciones | ✅ | ❌ | ❌ |
| CRUD cuentas/instancias/grupos | ✅ | ❌ | ❌ |
| Crear admins | ✅ | ❌ | ❌ |
| Exportar/Importar config | ✅ | ❌ | ❌ |

## Inicio rapido

### 1. Configurar cuentas e instancias

**Multi-cuenta** (varias cuentas AWS con roles cross-account):
```bash
copy config\accounts.example.json config\accounts.json
```

**Mono-cuenta** (una sola cuenta AWS):
```bash
copy config\accountsMono.example.json config\accounts.json
```

Edita `config/accounts.json` con tus datos reales.

### 2. (Solo multi-cuenta) Crear roles remotos

Crea el rol `CloudControlRemoteAccess` en cada cuenta remota.
Ver [docs/cross-account-setup.md](docs/cross-account-setup.md).

### 3. Desplegar

```powershell
.\deploy.ps1 -StackTag "ccp-main"
```

### 4. Usar

Ingresa al URL que devuelve el deploy con tu API key configurada.
En el primer request, la Lambda migra automaticamente el JSON a DynamoDB.
A partir de ahi, todos los cambios se hacen desde el panel sin necesidad de re-deploy.

> **Nota:** `config/accounts.json` esta en `.gitignore`. Solo los `.example` se versionan.

## Desarrollo local (Mock)

```bash
python mock/server.py
# Abre http://localhost:8080
```

### API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Superadmin | Ve todo, edita todo |
| `sanidad-key` | Operador | Solo cuenta Sanidad, ve scheduler (no edita) |
| `nuvu-key` | Operador | Solo cuenta Nuvu, sin acceso a scheduler |

## Estructura del proyecto

```
cloud-control-panel/
├── config/
│   ├── accounts.example.json       <- Plantilla multi-cuenta
│   ├── accountsMono.example.json   <- Plantilla mono-cuenta
│   └── accounts.json               <- Config real (NO se commitea)
├── backend/
│   ├── app.py                      <- Lambda handler (DynamoDB + EC2 + EventBridge)
│   └── requirements.txt
├── frontend/
│   ├── index.html                  <- SPA del panel
│   ├── app.js                      <- Logica frontend
│   └── style.css                   <- Estilos (dark theme)
├── mock/
│   └── server.py                   <- Servidor mock para desarrollo local
├── docs/
│   ├── architecture.md             <- Arquitectura del sistema
│   ├── admin-guide.md              <- Guia para administradores
│   ├── user-guide.md               <- Guia para usuarios
│   ├── configuration.md            <- Referencia de configuracion
│   ├── cross-account-setup.md      <- Setup cross-account IAM
│   ├── setup-email-smtp.md         <- Guia config email
│   ├── setup-telegram.md           <- Guia config Telegram
│   ├── setup-teams.md              <- Guia config Teams
│   └── ROADMAP.md                  <- Propuestas futuras
├── template.yaml                   <- CloudFormation (Lambda + API GW + S3 + CF + DynamoDB)
├── deploy.ps1                      <- Script de despliegue
└── samconfig.toml
```

## Servicios AWS utilizados

| Servicio | Uso | Costo estimado |
|----------|-----|----------------|
| Lambda | Backend API | Free tier (1M requests/mes) |
| API Gateway v2 | HTTP API | Free tier (1M requests/mes) |
| DynamoDB | Config dinamico + activity log | Free tier (25GB + 25 RCU/WCU) |
| S3 | Hosting frontend | ~$0.01/mes |
| CloudFront | CDN + HTTPS + routing | ~$0.01/mes |
| EventBridge Scheduler | Cron automatico | Sin costo por regla |
| **Total** | | **~$0/mes** (free tier) |

## Seguridad

- API keys en DynamoDB (no en UI publica)
- Cada key tiene acceso solo a cuentas especificas
- Roles diferenciados: superadmin > admin > operator
- Proteccion contra auto-eliminacion de superadmin
- Cross-account con roles IAM de minimo privilegio
- Frontend servido via CloudFront (HTTPS forzado)
- No se puede crear superadmin desde el panel (solo via JSON inicial)

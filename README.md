# Cloud Control Panel

Panel de control serverless para gestionar instancias EC2 en una o multiples cuentas AWS.

## Caracteristicas

- **Multi-cuenta**: Gestiona instancias en diferentes cuentas AWS desde un solo panel
- **Multi-instancia**: Controla N instancias por cuenta
- **Grupos**: Agrupa instancias para encender/apagar juntas con orden definido y colores personalizados
- **Scheduler**: Programacion automatica de encendido/apagado con EventBridge Scheduler (selector visual de dias y horas)
- **Notificaciones**: Alertas por Email (SMTP), Telegram y Microsoft Teams con detalle de quien ejecuto la accion
- **Estimacion de costos**: Seguimiento de uptime y costo estimado por instancia basado en datos reales de EC2
- **Roles y permisos**: Superadmin, Admin y Operador con permisos diferenciados
- **Seguridad**: API Keys con hash bcrypt, validacion Pydantic, proteccion contra escalacion de privilegios
- **DynamoDB**: Configuracion dinamica (single-table design) sin necesidad de re-deploy para cambios
- **CRUD desde el panel**: Crear/editar/eliminar cuentas, instancias, grupos y API Keys desde la UI
- **Export/Import**: Exportar e importar la configuracion completa como JSON con validacion
- **Activity log**: Historial de acciones persistente en DynamoDB
- **Estado en tiempo real**: Visualizacion del estado de cada instancia con auto-refresh
- **Update remoto**: Actualizar instancias via SSM RunCommand (git pull + restart)
- **Cross-account**: Usa roles IAM para operar instancias en cuentas remotas via STS AssumeRole
- **Serverless**: Lambda + API Gateway + CloudFront + S3 + DynamoDB + EventBridge
- **CI/CD**: Pipeline GitHub Actions (lint + test + deploy) con release automatico

## Arquitectura

```
Usuario -> CloudFront -> S3 (frontend estático, ES6 modules)
                      -> API Gateway HTTP v2 -> Lambda (Python 3.13, arm64)
                                                  -> DynamoDB (config, keys, activity log)
                                                  -> EC2 (start/stop/describe)
                                                  -> SSM (update via RunCommand)
                                                  -> STS AssumeRole -> EC2/SSM (cuenta remota)
                                                  -> EventBridge Scheduler (cron start/stop)
                                                  -> SMTP / Telegram / Teams (notificaciones)
```

## Roles y Permisos

| Accion | Superadmin | Admin | Operador |
|--------|:---:|:---:|:---:|
| Start/Stop instancias | ✅ | ✅ | ✅ |
| Update instancia (SSM) | ✅ | ✅ | ✅ |
| Ver costos | ✅ | ✅ | ❌ |
| Crear API Keys operadores | ✅ | ✅ | ❌ |
| Eliminar operadores | ✅ | ✅ | ❌ |
| Programacion (scheduler) | ✅ | ❌ | segun config |
| Notificaciones | ✅ | ❌ | ❌ |
| CRUD cuentas/instancias/grupos | ✅ | ❌ | ❌ |
| Crear admins | ✅ | ❌ | ❌ |
| Exportar/Importar config | ✅ | ❌ | ❌ |

## Inicio rapido

### Prerequisitos

- AWS CLI configurado con una cuenta (IAM user o SSO con permisos de admin)
- Python 3.13+
- pip

### 1. Clonar el repositorio

```bash
git clone https://github.com/<tu-usuario>/cloud-control-panel.git
cd cloud-control-panel
```

### 2. Configurar cuentas e instancias

**Multi-cuenta** (varias cuentas AWS con roles cross-account):
```bash
copy config\accounts.example.json config\accounts.json
```

**Mono-cuenta** (una sola cuenta AWS):
```bash
copy config\accountsMono.example.json config\accounts.json
```

Edita `config/accounts.json` con tus datos reales:
- Cambia los `CHANGE_ME_*` de apiKeys por valores seguros (UUIDs recomendado)
- Pon tus Instance IDs reales (`i-0xxxx`)
- Pon tu AWS Account ID de 12 digitos
- Si es multi-cuenta, pon el ARN del rol cross-account

> **Importante:** Este archivo contiene datos sensibles (API keys, IDs). Está en `.gitignore` y NUNCA se commitea.

### 3. (Solo multi-cuenta) Crear roles remotos

Crea el rol `CloudControlRemoteAccess` en cada cuenta remota.
Ver [docs/cross-account-setup.md](docs/cross-account-setup.md).

### 4. Desplegar

**PowerShell (Windows):**
```powershell
.\deploy.ps1 -StackTag "ccp-main"
```

**Bash (Linux/macOS/CI):**
```bash
chmod +x deploy.sh
./deploy.sh --stack-tag ccp-main
```

El script hace todo automaticamente:
1. Crea bucket S3 de deploy si no existe
2. Instala dependencias Python para Lambda (Linux arm64)
3. Copia tu `config/accounts.json` al bundle de Lambda (temporal)
4. Empaqueta y despliega CloudFormation
5. Sube el frontend a S3 + invalida cache CloudFront
6. Limpia archivos temporales del directorio backend/

### 5. Usar

Ingresa al URL que devuelve el deploy con tu API key configurada.
En el primer request, la Lambda migra automaticamente el JSON a DynamoDB.
A partir de ahi, todos los cambios se hacen desde el panel sin necesidad de re-deploy.

> **Nota:** `config/accounts.json` solo se usa en el PRIMER deploy. Despues de la migracion
> a DynamoDB, toda la config se gestiona desde el panel. Si necesitas re-migrar,
> usa el endpoint `POST /api/migrate` con una key de superadmin.

### 6. (Opcional) Deploy de staging para probar

Si quieres probar antes de ir a produccion, despliega con otro StackTag:

```powershell
.\deploy.ps1 -StackTag "ccp-staging"
```

Esto crea un stack completamente aislado. Para eliminarlo cuando ya no lo necesites:

```powershell
# Vaciar bucket S3 del staging
aws s3 rm s3://cloud-control-ccp-staging-<tu-account-id> --recursive
# Eliminar stack
aws cloudformation delete-stack --stack-name cloud-control-ccp-staging --region us-east-1
```

## Desarrollo local (Mock)

```bash
python mock/server.py
# Abre http://localhost:8080
```

El mock server simula todas las respuestas de la Lambda incluyendo scheduler, notificaciones y costos con datos aleatorios.

### API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Admin | Ve todo, edita todo |
| `sanidad-key` | Operador | Solo cuenta Sanidad, ve scheduler (no edita) |
| `nuvu-key` | Operador | Solo cuenta Nuvu, sin acceso a scheduler |

## Estructura del proyecto

```
cloud-control-panel/
├── .github/
│   └── workflows/
│       ├── ci.yml                      <- Pipeline: lint → test → deploy
│       └── release.yml                 <- Release automatico en tags v*.*.*
├── config/
│   ├── accounts.example.json           <- Plantilla multi-cuenta
│   ├── accountsMono.example.json       <- Plantilla mono-cuenta
│   └── accounts.json                   <- Config real (NO se commitea)
├── backend/
│   ├── app.py                          <- Lambda handler + router
│   ├── auth.py                         <- Autenticacion bcrypt + RBAC
│   ├── ec2_ops.py                      <- Operaciones EC2/SSM + cross-account
│   ├── scheduler.py                    <- EventBridge Scheduler CRUD + activity log
│   ├── notifications.py                <- Email + Telegram + Teams
│   ├── admin.py                        <- CRUD cuentas/instancias/grupos/keys + costos
│   ├── utils.py                        <- DynamoDB helpers, migraciones, pricing
│   ├── validators.py                   <- Modelos Pydantic para validacion
│   ├── requirements.txt                <- Dependencias Lambda
│   └── ruff.toml                       <- Config linter
├── frontend/
│   ├── index.html                      <- SPA del panel
│   ├── app.js                          <- Entry point (ES6 modules)
│   ├── style.css                       <- Estilos (dark theme)
│   └── js/
│       ├── utils.js                    <- Estado compartido + API helper
│       ├── auth.js                     <- Login/logout
│       ├── navigation.js               <- Navegacion entre pantallas
│       ├── accounts.js                 <- Gestion de cuentas
│       ├── instances.js                <- Instancias + detalle + acciones
│       ├── groups.js                   <- Grupos (encendido/apagado ordenado)
│       ├── scheduler.js                <- Programacion visual
│       ├── notifications.js            <- Canales de notificacion
│       ├── costs.js                    <- Estimacion de costos
│       ├── keys.js                     <- Gestion de API Keys
│       ├── admin.js                    <- CRUD instancias + asignacion operadores
│       └── settings.js                 <- Panel settings + export/import
├── mock/
│   └── server.py                       <- Servidor mock para desarrollo local
├── tests/
│   ├── conftest.py                     <- Fixtures (moto + DynamoDB mock)
│   ├── test_auth.py                    <- Tests de autenticacion
│   ├── test_ec2_ops.py                 <- Tests de operaciones EC2
│   ├── test_admin.py                   <- Tests CRUD admin
│   ├── test_scheduler.py              <- Tests scheduler
│   ├── test_notifications.py           <- Tests notificaciones
│   ├── test_lambda_handler.py          <- Tests del handler principal
│   └── test_integration.py            <- Tests E2E contra mock server
├── docs/                               <- Documentacion del proyecto
├── template.yaml                       <- CloudFormation (infraestructura completa)
├── deploy.ps1                          <- Script deploy (PowerShell/Windows)
├── deploy.sh                           <- Script deploy (Bash/Linux/CI)
├── samconfig.toml                      <- Configuracion SAM
├── pyproject.toml                      <- Configuracion pytest
├── requirements-dev.txt                <- Dependencias desarrollo (pytest, moto, ruff, mypy)
└── Makefile                            <- Comandos rapidos (install, lint, test, deploy, mock)
```

## Servicios AWS utilizados

| Servicio | Uso | Costo estimado |
|----------|-----|----------------|
| Lambda (Python 3.13, arm64) | Backend API | Free tier (1M requests/mes) |
| API Gateway HTTP v2 | HTTP API con CORS y throttling | Free tier (1M requests/mes) |
| DynamoDB (PAY_PER_REQUEST) | Config + keys + activity log (single-table) | Free tier (25GB) |
| S3 | Hosting frontend estatico | ~$0.01/mes |
| CloudFront | CDN + HTTPS + routing (S3 + API) | ~$0.01/mes |
| EventBridge Scheduler | Cron automatico start/stop | Sin costo por regla |
| SSM (Systems Manager) | Update remoto via RunCommand | Sin costo adicional |
| STS | AssumeRole para cross-account | Sin costo |
| IAM | Roles Lambda + Scheduler + Cross-account | Sin costo |
| CloudFormation | IaC (template.yaml) | Sin costo |
| **Total** | | **~$0/mes** (free tier) |

## CI/CD

El pipeline esta en `.github/workflows/`:

### En Pull Requests (staging efímero):
1. **Lint** → `ruff check` + `ruff format --check`
2. **Test** → `pytest` con coverage
3. **Deploy Staging** → Despliega un stack aislado (`ccp-staging-prN`) y comenta la URL en el PR
4. **Destroy Staging** → Al cerrar/mergear el PR, elimina el stack automaticamente

### En push a main (producción):
1. **Lint** → `ruff check`
2. **Test** → `pytest` con coverage
3. **Deploy Production** → Despliega al stack `ccp-main`

### En tags `v*.*.*`:
- Crea GitHub Release con release notes automaticas

### Comandos locales (Makefile)

```bash
make install          # Instalar dependencias
make lint             # Lint con ruff
make test             # Tests
make test-cov         # Tests con coverage
make mock             # Servidor mock local
make deploy           # Deploy a AWS
make validate-template # Validar template CloudFormation
make clean            # Limpiar artifacts
```

## Seguridad

- **API Keys con bcrypt**: Almacenadas como hash en DynamoDB, nunca en texto plano
- **Migracion automatica**: Keys legacy (plaintext) se migran a bcrypt en el primer request
- **UUID como key_id**: El identificador interno es un UUID separado del valor de la key
- **Validacion Pydantic**: Todos los endpoints POST/PUT validan body con modelos estrictos
- **Validacion de path params**: Regex para prevenir inyeccion en parametros de ruta
- **Roles diferenciados**: superadmin > admin > operator con permisos granulares
- **Proteccion contra auto-eliminacion**: No puedes eliminar tu propia key
- **Proteccion contra escalacion**: Admins solo crean operadores, superadmin no se crea desde panel
- **Cross-account con minimo privilegio**: Rol `CloudControlRemoteAccess` solo con permisos EC2/SSM
- **HTTPS forzado**: CloudFront redirige HTTP a HTTPS
- **S3 privado**: Bucket sin acceso publico, solo via OAC de CloudFront
- **CORS restrictivo**: Solo permite origenes del CloudFront + localhost
- **Throttling**: API Gateway con burst 200 / rate 100 requests/s
- **Errores genericos**: Mensajes de error sanitizados, sin exponer detalles internos
- **Keys no expuestas**: El listado solo muestra preview (primeros 8 chars del UUID)

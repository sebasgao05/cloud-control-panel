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

## Inicio rapido — Guia paso a paso

Este proyecto es para que cada persona lo clone y despliegue su propia instancia en su cuenta AWS.
No es una plataforma compartida — cada uno tiene su propio panel independiente.

### Prerequisitos

- Una cuenta AWS activa
- AWS CLI instalado y configurado (`aws configure`)
- Python 3.13+ con pip
- Permisos IAM: CloudFormation, Lambda, S3, CloudFront, DynamoDB, API Gateway, IAM, EventBridge, EC2, SSM, STS

---

### Paso 1: Clonar el repositorio

```bash
git clone https://github.com/sebasgao05/cloud-control-panel.git
cd cloud-control-panel
```

---

### Paso 2: Crear tu archivo de configuracion

Copia la plantilla que se ajuste a tu caso:

**Si tienes varias cuentas AWS:**
```bash
# Windows
copy config\accounts.example.json config\accounts.json

# Linux/macOS
cp config/accounts.example.json config/accounts.json
```

**Si tienes una sola cuenta AWS:**
```bash
# Windows
copy config\accountsMono.example.json config\accounts.json

# Linux/macOS
cp config/accountsMono.example.json config/accounts.json
```

---

### Paso 3: Editar tu configuracion

Abre `config/accounts.json` y reemplaza los valores de ejemplo con tus datos reales:

#### 3.1 — API Keys (seccion `apiKeys`)

```json
"apiKeys": {
  "mi-clave-secreta-uuid-aqui": {
    "name": "Tu Nombre",
    "role": "superadmin",
    "accounts": ["*"]
  }
}
```

- La key (ej: `mi-clave-secreta-uuid-aqui`) es lo que usaras para ingresar al panel
- Usa un UUID seguro. Puedes generar uno con: `python -c "import uuid; print(uuid.uuid4())"`
- El primer superadmin DEBE crearse aqui. Despues se pueden crear admins/operadores desde el panel

#### 3.2 — Cuentas AWS (seccion `accounts`)

```json
"accounts": [
  {
    "id": "mi-proyecto",
    "name": "Produccion - Mi Proyecto",
    "awsAccountId": "123456789012",
    "region": "us-east-1",
    "crossAccountRoleArn": null,
    "features": {
      "scheduler": true,
      "notifications": true,
      "costEstimate": true
    }
  }
]
```

- `id`: identificador unico (sin espacios, solo letras/numeros/guiones)
- `awsAccountId`: tu Account ID de 12 digitos (lo ves en la consola AWS arriba a la derecha)
- `crossAccountRoleArn`: dejalo en `null` si es la misma cuenta donde despliegas. Solo se usa para multi-cuenta
- `features`: activa/desactiva scheduler, notificaciones y costos por cuenta

#### 3.3 — Instancias EC2

```json
"instances": [
  {
    "id": "mi-server",
    "name": "Servidor Principal",
    "instanceId": "i-0abc123def456789",
    "description": "Backend de produccion",
    "dashboardPort": null,
    "group": null
  }
]
```

- `instanceId`: el ID real de tu instancia EC2 (lo ves en la consola EC2, empieza con `i-`)
- `dashboardPort`: si la instancia tiene un servicio web, pon el puerto. Si no, dejalo en `null`
- `group`: si quieres agrupar instancias, pon el ID del grupo. Si no, dejalo en `null`

> ⚠️ **IMPORTANTE:** Este archivo contiene tus API keys y datos de infraestructura.
> Esta en `.gitignore` y NUNCA se debe commitear al repositorio.

---

### Paso 4: (Solo multi-cuenta) Crear rol en cuentas remotas

Si vas a gestionar instancias en OTRAS cuentas AWS, necesitas crear un rol IAM en cada cuenta remota.
Ver [docs/cross-account-setup.md](docs/cross-account-setup.md) para instrucciones detalladas.

Si solo usas una cuenta, salta este paso.

---

### Paso 5: Desplegar

**Windows (PowerShell):**
```powershell
.\deploy.ps1 -StackTag "ccp-main"
```

**Linux/macOS/WSL:**
```bash
chmod +x deploy.sh
./deploy.sh --stack-tag ccp-main
```

El script automaticamente:
1. Crea un bucket S3 para el deploy (si no existe)
2. Instala las dependencias Python para Lambda (Linux arm64)
3. Empaqueta tu codigo + config con CloudFormation
4. Despliega toda la infraestructura (Lambda, API Gateway, DynamoDB, S3, CloudFront)
5. Sube el frontend a S3 e invalida el cache de CloudFront
6. Limpia archivos temporales

Al finalizar te muestra la URL de tu panel:
```
========================================
 DEPLOY COMPLETE!
========================================

 Panel URL: https://xxxxxx.cloudfront.net
```

---

### Paso 6: Ingresar al panel

1. Abre la URL que te dio el deploy
2. Ingresa la API Key que configuraste en el paso 3.1
3. La primera vez, la Lambda migra automaticamente tu `accounts.json` a DynamoDB
4. A partir de ahi, todos los cambios se hacen desde el panel (sin necesidad de re-deploy)

> **Nota:** Despues del primer deploy, tu `config/accounts.json` ya no se necesita.
> Todo se gestiona desde el panel web (crear cuentas, instancias, keys, etc.).
> Si necesitas re-migrar, usa el endpoint `POST /api/migrate` con una key de superadmin.

---

### Paso 7: (Opcional) Configurar CI/CD con GitHub Actions

Si quieres que los cambios se desplieguen automaticamente:

1. Ve a tu repo en GitHub → **Settings → Secrets and variables → Actions**
2. Agrega estos **Repository secrets**:

| Secret | Valor |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | Tu Access Key de AWS |
| `AWS_SECRET_ACCESS_KEY` | Tu Secret Key de AWS |
| `ACCOUNTS_JSON` | El contenido completo de tu `config/accounts.json` |

3. (Opcional) Crea estos **Environments** en Settings → Environments:
   - `staging` — sin protecciones
   - `staging-approve` — con **Required reviewers** (tu usuario)
   - `production` — con **Required reviewers** (opcional)

Con esto configurado:
- Cada **Pull Request** despliega un staging efimero para probar
- Al **mergear a main** se despliega automaticamente a produccion
- Los **tags** (`v1.0.0`) crean un GitHub Release

---

### Paso 8: (Opcional) Probar en staging antes de produccion

Si prefieres probar en un ambiente aislado antes del deploy definitivo:

```powershell
# Desplegar staging (stack completamente separado de produccion)
.\deploy.ps1 -StackTag "ccp-staging"

# Cuando termines de probar, eliminar staging:
aws s3 rm s3://cloud-control-ccp-staging-<tu-account-id> --recursive
aws cloudformation delete-stack --stack-name cloud-control-ccp-staging --region us-east-1
```

---

### Resumen del flujo

```
1. Clonar repo
2. Crear config/accounts.json con tus datos reales
3. Ejecutar deploy.ps1 o deploy.sh
4. Abrir la URL → ingresar con tu API key
5. (Opcional) Configurar CI/CD en GitHub con los 3 secrets
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

### Configuracion requerida (GitHub Secrets)

Para que el CI/CD funcione, configura estos secrets en tu repo:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Descripcion |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | Access Key de IAM con permisos de deploy |
| `AWS_SECRET_ACCESS_KEY` | Secret Key del mismo IAM user |
| `ACCOUNTS_JSON` | Contenido completo de tu `config/accounts.json` |

El secret `ACCOUNTS_JSON` es el mismo archivo que creas localmente para tu primer deploy.
El CI lo reconstruye en runtime para no commitear datos sensibles al repo.

### En Pull Requests (staging efímero):
1. **Lint** → `ruff check` + `ruff format --check`
2. **Test** → `pytest` con coverage
3. **Deploy Staging** → Despliega un stack aislado (`ccp-staging-prN`) con tu config real
4. **Approve Staging** → Espera aprobación manual (environment `staging-approve`)
5. **Destroy Staging** → Al aprobar, elimina el stack automaticamente

### En push a main (producción):
1. **Lint** → `ruff check`
2. **Test** → `pytest` con coverage
3. **Deploy Production** → Despliega al stack `ccp-main`

### En tags `v*.*.*`:
- Crea GitHub Release con release notes automaticas

### Environments de GitHub (opcional pero recomendado)

Crea estos environments en **Settings → Environments**:
- `staging` — sin protecciones
- `staging-approve` — con **Required reviewers** (tu usuario)
- `production` — con **Required reviewers** (opcional)

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

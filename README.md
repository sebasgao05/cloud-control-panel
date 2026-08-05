# Cloud Control Panel

Panel de control serverless para gestionar instancias EC2 en una o multiples cuentas AWS.

## Caracteristicas

- Multi-cuenta: Gestiona instancias en diferentes cuentas AWS desde un solo panel
- Multi-instancia: Controla N instancias por cuenta
- Grupos: Agrupa instancias para encender/apagar juntas con orden definido y colores personalizados
- Scheduler: Programacion automatica de encendido/apagado con selector visual de dias y horas
- Notificaciones: Alertas por Email (SMTP), Telegram y Microsoft Teams
- Estimacion de costos: Seguimiento de uptime y costo estimado por instancia
- API Keys con permisos: Cada key ve solo las cuentas asignadas, con permisos granulares
- Estado en tiempo real: Visualizacion del estado de cada instancia
- Cross-account: Usa roles IAM para operar instancias en cuentas remotas
- Serverless: Lambda + API Gateway + CloudFront + S3

## Arquitectura

```
Usuario -> CloudFront -> S3 (frontend)
                      -> API Gateway -> Lambda -> EC2 (misma cuenta)
                                               -> STS AssumeRole -> EC2 (cuenta remota)
                                               -> EventBridge Scheduler (programacion)
```

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

Edita `config/accounts.json` con tus datos reales (instance IDs, account IDs, ARNs, API keys).

### 2. (Solo multi-cuenta) Crear roles remotos

Crea el rol `CloudControlRemoteAccess` en cada cuenta remota.
Ver [docs/cross-account-setup.md](docs/cross-account-setup.md).

### 3. Desplegar

```powershell
.\deploy.ps1 -StackTag "ccp-main"
```

### 4. Usar

Ingresa al URL que devuelve el deploy con tu API key configurada.

> **Nota:** `config/accounts.json` está en `.gitignore` y NO se commitea. Solo los archivos `.example` se versionan como referencia.

## Desarrollo local (Mock)

```bash
python mock/server.py
# Abre http://localhost:8080
```

### API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Admin | Ve todo, edita scheduler, notificaciones y costos |
| `sanidad-key` | Operador | Solo cuenta Sanidad, ve scheduler (no edita) |
| `nuvu-key` | Operador | Solo cuenta Nuvu, sin acceso a scheduler |

## Estructura

```
config/
  accounts.example.json            <- Plantilla multi-cuenta (referencia)
  accountsMono.example.json        <- Plantilla mono-cuenta (referencia)
  accounts.json                    <- Config real de cuentas (NO se commitea)
backend/
  app.py                           <- Lambda handler (multi-account)
frontend/
  index.html                       <- SPA del panel de control
  app.js                           <- Logica frontend
  style.css                        <- Estilos
mock/
  server.py                        <- Servidor mock para desarrollo local
docs/
  architecture.md                  <- Arquitectura del sistema
  admin-guide.md                   <- Guia para administradores
  user-guide.md                    <- Guia para usuarios
  configuration.md                 <- Referencia de configuracion
  cross-account-setup.md           <- Setup cross-account
  ROADMAP.md                       <- Propuestas futuras
  architecture-diagram.drawio      <- Diagrama visual
template.yaml                      <- CloudFormation/SAM template
deploy.ps1                         <- Script de despliegue
```

## Features configurables

El admin habilita features por cuenta en `accounts.json`:

```json
"features": {
  "scheduler": true,
  "notifications": true,
  "costEstimate": true
}
```

| Feature | Descripcion |
|---------|-------------|
| `scheduler` | Programacion automatica de encendido/apagado |
| `notifications` | Alertas por email, Telegram o Teams |
| `costEstimate` | Estimacion de costos basada en uptime real |

## Agregar una cuenta o instancia

1. Editar `config/accounts.json`
2. Ejecutar `.\deploy.ps1`
3. Listo

## Seguridad

- API keys definidas en config (no en UI)
- Cada key tiene acceso solo a cuentas especificas
- Permisos granulares por key (scheduler view/edit)
- Cross-account con roles IAM de minimo privilegio
- Frontend servido via CloudFront (HTTPS)
- No hay base de datos - todo es config-as-code

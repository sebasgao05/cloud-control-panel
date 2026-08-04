# Cloud Control Panel

Panel de control serverless para gestionar instancias EC2 en una o multiples cuentas AWS.

## Caracteristicas

- Multi-cuenta: Gestiona instancias en diferentes cuentas AWS desde un solo panel
- Multi-instancia: Controla N instancias por cuenta
- Grupos: Agrupa instancias para encender/apagar juntas con orden definido
- API Keys con permisos: Cada key ve solo las cuentas asignadas
- Estado en tiempo real: Visualizacion del estado de cada instancia
- Cross-account: Usa roles IAM para operar instancias en cuentas remotas
- Serverless: Lambda + API Gateway + CloudFront + S3

## Arquitectura

```
Usuario -> CloudFront -> S3 (frontend)
                      -> API Gateway -> Lambda -> EC2 (misma cuenta)
                                               -> STS AssumeRole -> EC2 (cuenta remota)
```

## Inicio rapido

### 1. Configurar

Edita `config/accounts.json` con tus cuentas, instancias y API keys.
Ver [docs/configuration.md](docs/configuration.md) para detalles.

### 2. (Solo multi-cuenta) Crear roles remotos

Crea el rol `CloudControlRemoteAccess` en cada cuenta remota.
Ver [docs/cross-account-setup.md](docs/cross-account-setup.md).

### 3. Desplegar

```powershell
.\deploy.ps1 -StackTag "ccp-main"
```

### 4. Usar

Ingresa al URL que devuelve el deploy con tu API key configurada.

## Desarrollo local (Mock)

```bash
python mock/server.py
# Abre http://localhost:8080
# API Key: demo
```

## Estructura

```
config/
  accounts.json          <- Configuracion de cuentas, instancias, keys (admin edita aqui)
backend/
  app.py                 <- Lambda handler (multi-account)
frontend/
  index.html             <- SPA del panel de control
  app.js                 <- Logica frontend
  style.css              <- Estilos
mock/
  server.py              <- Servidor mock para desarrollo local
docs/
  architecture.md        <- Arquitectura del sistema
  admin-guide.md         <- Guia para administradores
  user-guide.md          <- Guia para usuarios
  configuration.md       <- Referencia de configuracion
  cross-account-setup.md <- Setup cross-account
  architecture-diagram.drawio <- Diagrama visual
template.yaml            <- CloudFormation/SAM template
deploy.ps1               <- Script de despliegue
```

## Agregar una cuenta o instancia

1. Editar `config/accounts.json`
2. Ejecutar `.\deploy.ps1`
3. Listo

## Seguridad

- API keys definidas en config (no en UI)
- Cada key tiene acceso solo a cuentas especificas
- Cross-account con roles IAM de minimo privilegio
- Frontend servido via CloudFront (HTTPS)
- No hay base de datos - todo es config-as-code

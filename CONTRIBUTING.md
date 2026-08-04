# Contribuir a Cloud Control Panel

Gracias por tu interes en contribuir. Aqui tienes las guias para hacerlo de forma ordenada.

## Requisitos previos

- AWS CLI configurado con credenciales validas
- Python 3.13+
- PowerShell (para el script de deploy)
- Una cuenta AWS para pruebas

## Setup local

1. Clona el repositorio:
```bash
git clone https://github.com/sebasgao05/cloud-control-panel.git
cd cloud-control-panel
```

2. Copia la configuracion de ejemplo:
```bash
copy config\accounts.example.json config\accounts.json
```

3. Edita `config/accounts.json` con tus datos reales.

4. Para desarrollo local sin AWS:
```bash
python mock/server.py
# Abre http://localhost:8080
# API Key: demo
```

## Flujo de trabajo

1. Crea un branch desde `main`:
```bash
git checkout -b feature/mi-nueva-funcionalidad
```

2. Haz tus cambios siguiendo las convenciones del proyecto.

3. Prueba localmente con el mock server o desplegando en una cuenta de prueba.

4. Haz commit siguiendo el formato de mensajes (ver abajo).

5. Abre un Pull Request contra `main`.

## Convenciones de commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: agregar soporte para reboot de instancias
fix: corregir navegacion con una sola cuenta
docs: actualizar guia de configuracion
style: ajustar colores del panel
refactor: extraer logica de autenticacion
```

## Estructura del proyecto

```
backend/     <- Lambda handler (Python)
frontend/    <- SPA vanilla JS/HTML/CSS
config/      <- Archivos de configuracion (.example se versionan)
mock/        <- Servidor local para desarrollo
docs/        <- Documentacion
```

## Reglas importantes

- **NUNCA** commitear `config/accounts.json` ni archivos con API keys reales
- Los archivos `.example` son los que se versionan como referencia
- El frontend es vanilla JS — no agregar frameworks ni build tools
- El backend es Python puro con boto3 — no agregar dependencias innecesarias
- Mantener el panel ligero y simple

## Reporte de bugs

Abre un Issue con:
- Descripcion clara del problema
- Pasos para reproducir
- Screenshots si aplica
- Logs de CloudWatch si es un error del backend

## Sugerencias de features

Abre un Issue con la etiqueta `enhancement` describiendo:
- Que quieres lograr
- Por que es util
- Propuesta de implementacion (opcional)

# Mock Server - Cloud Control Panel

Servidor local que simula las respuestas de la Lambda para desarrollo sin necesidad de desplegar a AWS.

## Uso

```bash
python mock/server.py
# Abre http://localhost:8080

python mock/server.py --port 3000
# Puerto custom
```

## API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Admin | Ve todo: cuentas, scheduler (edita), notificaciones, costos |
| `sanidad-key` | Operador | Solo cuenta Sanidad, ve scheduler (solo lectura) |
| `nuvu-key` | Operador | Solo cuenta Nuvu, sin acceso a scheduler |

## Features simulados

- **Scheduler**: Reglas de programacion precargadas, se pueden crear/editar/eliminar
- **Notificaciones**: Canales de email y Telegram precargados, al hacer start/stop se imprime `[NOTIFY]` en consola
- **Costos**: Historial de actividad simulado del mes, calcula uptime y costo por instancia
- **Grupos**: Con colores configurados, clickeables para ver instancias internas

## Cuentas de prueba

### Sanidad (sanidad)
- 3 instancias: App Server (t3.medium), Database Server (r5.large), Worker Server (t3.small)
- 1 grupo: Core Sanidad (App + DB)
- Scheduler: 2 reglas (una activa, una inactiva)
- Notificaciones: Email + Telegram

### Nuvu (nuvu-10)
- 2 instancias: Main Server (t3.large), Staging Server (t3.medium)
- Sin grupos
- Scheduler: 1 regla activa
- Notificaciones: Teams (desactivado)

## Comportamiento

- Las instancias inician con estado aleatorio (running/stopped)
- Start/Stop cambia el estado inmediatamente
- Las notificaciones se simulan con prints en consola: `[NOTIFY] [TIPO] canal -> evento: instancia`
- El historial de costos se genera aleatoriamente al iniciar y se actualiza con cada start/stop
- Latencia simulada de red: 100-300ms por request

## Endpoints soportados

| Metodo | Path | Descripcion |
|--------|------|-------------|
| GET | /api/accounts | Lista cuentas del usuario |
| GET | /api/accounts/{id}/instances | Lista instancias y grupos |
| GET | /api/accounts/{id}/instances/{iid}/status | Estado de instancia |
| POST | /api/accounts/{id}/instances/{iid}/start | Encender instancia |
| POST | /api/accounts/{id}/instances/{iid}/stop | Apagar instancia |
| POST | /api/accounts/{id}/instances/{iid}/update | Trigger update via SSM |
| GET | /api/accounts/{id}/instances/{iid}/dashboard-url | URL del dashboard |
| GET | /api/accounts/{id}/groups/{gid}/status | Estado del grupo |
| POST | /api/accounts/{id}/groups/{gid}/start | Encender grupo |
| POST | /api/accounts/{id}/groups/{gid}/stop | Apagar grupo |
| GET | /api/accounts/{id}/schedule | Obtener programacion |
| PUT | /api/accounts/{id}/schedule | Actualizar programacion |
| GET | /api/accounts/{id}/notifications | Obtener canales |
| PUT | /api/accounts/{id}/notifications | Actualizar canales |
| POST | /api/accounts/{id}/notifications/test | Enviar notificacion de prueba |
| GET | /api/accounts/{id}/costs | Obtener estimacion de costos |

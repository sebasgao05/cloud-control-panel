# Mock Server - Cloud Control Panel

Servidor local que simula toda la API para desarrollo y pruebas sin necesidad de AWS.

## Uso

```bash
# Desde la raiz del proyecto
python mock/server.py

# Puerto custom
python mock/server.py --port 3000
```

Abre http://localhost:8080 en tu navegador.

## API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Admin | Todas las cuentas |
| `sanidad-key` | Operator | Solo cuenta Sanidad |
| `nuvu-key` | Operator | Solo cuenta Nuvu |

## Que simula?

- Login con multiples API keys y permisos
- 2 cuentas: Sanidad (3 instancias, 1 grupo) y Nuvu (2 instancias)
- Estados de instancias (running/stopped) que cambian con start/stop
- IPs publicas generadas al encender
- Uptime calculado desde el momento de encendido
- Latencia simulada (100-300ms por request)
- Grupos con encendido/apagado en bloque
- Dashboard URLs
- Access control por cuenta

## Notas

- Los estados son en memoria - se reinician al parar el server
- Los estados iniciales son aleatorios (algunas running, algunas stopped)
- No necesita ninguna dependencia externa, solo Python 3

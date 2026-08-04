# Mock & Testing - Cloud Control Panel

## 1. Mock Server (desarrollo local sin AWS)

Servidor local que simula toda la API para desarrollo y pruebas sin necesidad de AWS.

### Uso

```bash
# Desde la raiz del proyecto
python mock/server.py

# Puerto custom
python mock/server.py --port 3000
```

Abre http://localhost:8080 en tu navegador.

### API Keys de prueba

| Key | Rol | Acceso |
|-----|-----|--------|
| `demo` | Admin | Todas las cuentas |
| `sanidad-key` | Operator | Solo cuenta Sanidad |
| `nuvu-key` | Operator | Solo cuenta Nuvu |

### Que simula?

- Login con multiples API keys y permisos
- 2 cuentas: Sanidad (3 instancias, 1 grupo) y Nuvu (2 instancias)
- Estados de instancias (running/stopped) que cambian con start/stop
- IPs publicas generadas al encender
- Uptime calculado desde el momento de encendido
- Latencia simulada (100-300ms por request)
- Grupos con encendido/apagado en bloque
- Dashboard URLs
- Access control por cuenta

### Notas

- Los estados son en memoria - se reinician al parar el server
- Los estados iniciales son aleatorios (algunas running, algunas stopped)
- No necesita ninguna dependencia externa, solo Python 3

---

## 2. Test Cross-Account (validar AssumeRole con AWS real)

Script que crea un rol IAM en tu misma cuenta para simular el flujo multi-cuenta
sin necesitar una segunda cuenta AWS.

### Que valida?

El flujo real de cross-account:
1. Lambda recibe request
2. Lambda hace `STS AssumeRole` al rol `CloudControlRemoteAccess`
3. Lambda obtiene credenciales temporales
4. Lambda usa esas credenciales para llamar `ec2:DescribeInstances`

Es exactamente el mismo flujo que con una cuenta remota real. La unica diferencia
es que el rol está en la misma cuenta (para fines de prueba).

### Uso

```powershell
# Crear el rol de prueba
.\mock\setup-cross-account-test.ps1

# Seguir las instrucciones que imprime (agregar cuenta en config/accounts.json)
# Luego desplegar
.\deploy.ps1 -StackTag "ccp-main"

# Validar en el panel: deben aparecer 2 cuentas
# - "Principal" (acceso directo)
# - "Cross-Account Test" (acceso via AssumeRole)

# Limpiar cuando termines
.\mock\setup-cross-account-test.ps1 -Cleanup
```

### Que significa "funciona"?

Si en el panel puedes entrar a la cuenta "Cross-Account Test" y ver el estado
de la instancia (running/stopped/IP), entonces el flujo multi-cuenta completo
funciona correctamente. La Lambda logró:

- Asumir el rol remoto via STS
- Obtener credenciales temporales
- Usar esas credenciales para operar EC2

### Diferencia con multi-cuenta real

| Aspecto | Test (misma cuenta) | Real (otra cuenta) |
|---------|--------------------|--------------------|
| Rol | En la misma cuenta (009245113723) | En otra cuenta (222222222222) |
| Trust policy | Confía en la Lambda de esta cuenta | Confía en la Lambda de la cuenta principal |
| Instancias | Accede a las mismas instancias | Accede a instancias de la otra cuenta |
| Flujo STS | Identico | Identico |
| Permisos EC2 | Identico | Identico |

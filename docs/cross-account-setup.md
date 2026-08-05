# Cross-Account Setup - Cloud Control Panel

## Resumen

Para que Cloud Control Panel pueda gestionar instancias en cuentas AWS remotas,
necesitas crear un rol IAM en cada cuenta remota que la Lambda pueda asumir.

## Arquitectura

```
Cuenta Principal (donde se despliega Cloud Control Panel)
  +-- Lambda -> sts:AssumeRole -> Cuenta Remota
                                   +-- Rol: CloudControlRemoteAccess
                                        +-- Permisos: EC2, SSM
```

## Paso 1: Crear el rol en la cuenta remota

En cada cuenta remota donde quieras gestionar instancias, crea este rol:

### Nombre del rol
`CloudControlRemoteAccess` (o el que definas en accounts.json)

### Trust Policy (quien puede asumir el rol)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::CUENTA_PRINCIPAL_ID:role/cloud-control-lambda-ccp-main"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Reemplaza `CUENTA_PRINCIPAL_ID` con el ID de la cuenta donde esta desplegado el panel.

### Permissions Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:SendCommand",
        "ssm:GetCommandInvocation"
      ],
      "Resource": "*"
    }
  ]
}
```

Para restringir a instancias especificas, cambia `Resource: "*"` por los ARNs de las instancias.

## Paso 2: Configurar accounts.json

```json
{
  "id": "mi-cuenta-remota",
  "name": "Nombre descriptivo",
  "awsAccountId": "123456789012",
  "region": "us-east-1",
  "crossAccountRoleArn": "arn:aws:iam::123456789012:role/CloudControlRemoteAccess",
  "instances": [...]
}
```

## Paso 3: Mono-cuenta (sin cross-account)

Si la instancia esta en la misma cuenta donde se despliega la Lambda,
pon `crossAccountRoleArn` como `null` o no lo incluyas:

```json
{
  "id": "mi-cuenta-local",
  "name": "Cuenta Principal",
  "awsAccountId": "999888777666",
  "region": "us-east-1",
  "crossAccountRoleArn": null,
  "instances": [...]
}
```

La Lambda usara sus permisos directos sin asumir otro rol.

## Notas

- El nombre del rol puede ser diferente por cuenta, solo asegurate de que el ARN
  en `crossAccountRoleArn` coincida con el rol creado.
- Para Permission Sets de SSO (PS-SupportEngineerAccess, etc.), estos son para
  acceso humano al portal. La Lambda usa roles IAM clasicos, no SSO.
- El deploy inicial migra el JSON a DynamoDB automaticamente. Despues de eso,
  puedes agregar cuentas remotas desde el panel (solo superadmin) sin re-deploy.
- EventBridge Scheduler tambien necesita los permisos cross-account si las instancias
  programadas estan en cuentas remotas.

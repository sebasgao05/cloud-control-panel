# Politica de Seguridad

## Reportar vulnerabilidades

Si encuentras una vulnerabilidad de seguridad, **NO** abras un Issue publico.

En su lugar, contacta directamente a traves de GitHub Security Advisories o envia un correo describiendo:
- Descripcion de la vulnerabilidad
- Pasos para reproducirla
- Impacto potencial

## Practicas de seguridad del proyecto

- Las API keys se almacenan en `config/accounts.json` (no versionado)
- Los archivos sensibles estan en `.gitignore`
- Cross-account access usa roles IAM con minimo privilegio
- El frontend se sirve via HTTPS (CloudFront)
- No se almacenan credenciales AWS en el codigo

## Versiones soportadas

| Version | Soportada |
|---------|-----------|
| main    | Si        |

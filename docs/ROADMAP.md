# Roadmap - Cloud Control Panel

Propuestas de mejora ordenadas de mas probable a menos probable de implementar.

---

## ✅ Propuesta 1 — Programador de instancias (Scheduler) [IMPLEMENTADA]

Programacion automatica de encendido/apagado con selector visual de dias y horas.
Implementado con EventBridge Scheduler. Permisos configurables por API Key (view/edit).
El admin habilita con `features.scheduler: true` por cuenta.

---

## ✅ Propuesta 2 — Notificaciones configurables [IMPLEMENTADA]

Canales de notificacion por cuenta: Email (SMTP), Telegram y Teams.
Sin costo adicional (SMTP directo, APIs gratuitas de Telegram y Teams).
Solo el admin ve y gestiona los canales desde el panel lateral.

---

## ✅ Propuesta 3 — Estimacion de costos basada en actividad real [IMPLEMENTADA]

Calculo de costo acumulado por instancia basado en historial de start/stop.
Muestra uptime, costo/hora, total acumulado y proyeccion mensual.
En produccion se almacena en DynamoDB. Habilitado con `features.costEstimate: true`.

---

## Propuesta 4 — Permisos granulares por accion (Feature flags por API Key)

Extender el modelo de permisos para controlar que acciones puede realizar cada usuario:

```json
"apiKeys": {
  "junior_key": {
    "name": "Operador Junior",
    "role": "operator",
    "accounts": ["paridad"],
    "permissions": {
      "start": true,
      "stop": false,
      "update": false,
      "dashboard": true,
      "viewCosts": true
    }
  }
}
```

- El backend valida permisos antes de ejecutar cada accion
- El frontend oculta/deshabilita botones segun permisos
- Admin siempre tiene todo habilitado

---

## Propuesta 5 — Audit log persistente

Registrar todas las acciones en DynamoDB:

- Quien hizo que, cuando, sobre cual instancia/cuenta
- Incluye acciones manuales y del scheduler
- Vista en el panel para admins con filtros
- Exportar a CSV
- Retencion configurable (30, 60, 90 dias)

```json
"settings": {
  "auditLog": {
    "enabled": true,
    "retentionDays": 90
  }
}
```

---

## Propuesta 6 — Multi-servicio (RDS, ECS, Lightsail)

Extender el panel para gestionar recursos mas alla de EC2:

```json
{
  "id": "prod-db",
  "name": "Database Cluster",
  "type": "rds",
  "resourceId": "my-aurora-cluster",
  "group": "core-servers"
}
```

- **RDS/Aurora**: Start/Stop de clusters
- **ECS/Fargate**: Scale to 0 / scale up
- **Lightsail**: Start/Stop de instancias

---

## Propuesta 7 — Dashboard mejorado

- Graficas de uptime por instancia (ultimos 7/30 dias)
- Metricas basicas de CPU y memoria (CloudWatch)
- Vista en tarjetas o tabla (toggle)
- Status page publica opcional

---

## Propuesta 8 — Multi-region mejorado

- Selector de region en el frontend
- Vista global agrupada por region

---

## Propuesta 9 — Infraestructura como codigo mejorada

- GitHub Actions para deploy automatico
- Rollback automatico si el deploy falla
- Environments separados (dev/staging/prod)
- Terraform como alternativa a SAM

---

## Propuesta 10 — API publica y automatizacion

- CLI companion para operar desde terminal
- API tokens con expiracion para CI/CD
- Webhooks de entrada para trigger desde pipelines

---

## Propuesta 11 — Seguridad avanzada

- 2FA/MFA con TOTP
- IP Allowlist por key
- Session timeout configurable
- Rate limiting contra brute-force

---

## Propuesta 12 — UX / Frontend avanzado

- Dark/Light mode toggle
- PWA con push notifications
- Favoritos
- Busqueda global
- Confirmacion en dos pasos para produccion

---

## Resumen

| # | Propuesta | Estado | Impacto | Esfuerzo |
|---|-----------|--------|---------|----------|
| 1 | Scheduler | ✅ Implementada | Alto | Medio |
| 2 | Notificaciones | ✅ Implementada | Alto | Medio |
| 3 | Estimacion de costos | ✅ Implementada | Alto | Medio |
| 4 | Permisos por accion | Pendiente | Medio | Bajo |
| 5 | Audit log | Pendiente | Medio | Medio |
| 6 | Multi-servicio | Pendiente | Alto | Alto |
| 7 | Dashboard mejorado | Pendiente | Medio | Medio |
| 8 | Multi-region | Pendiente | Bajo | Medio |
| 9 | IaC mejorada | Pendiente | Medio | Alto |
| 10 | API/CLI | Pendiente | Medio | Medio |
| 11 | Seguridad avanzada | Pendiente | Alto | Alto |
| 12 | UX avanzado | Pendiente | Medio | Medio |

# Configurar Notificaciones por Microsoft Teams

Guia para configurar el canal de notificaciones via Microsoft Teams Webhooks.

---

## Costo

Gratis. Los Incoming Webhooks de Teams no tienen costo adicional.

---

## Paso 1: Crear un Incoming Webhook en Teams

### Metodo actual (Workflows / Power Automate)

Microsoft esta migrando de los Incoming Webhooks clasicos a Workflows. Dependiendo de tu version:

#### Si tienes Workflows (nuevo):

1. Abre Microsoft Teams
2. Ve al canal donde quieres recibir notificaciones
3. Click en los tres puntos (...) del canal > "Manage channel"
4. Click en "Connectors" o "Workflows"
5. Busca "Post to a channel when a webhook request is received"
6. Sigue el wizard — al final te dara una URL
7. Copia la URL completa

#### Si tienes Incoming Webhooks (clasico):

1. Abre Microsoft Teams
2. Ve al canal donde quieres recibir notificaciones
3. Click en los tres puntos (...) del canal > "Connectors"
4. Busca "Incoming Webhook" y click en "Configure"
5. Ponle un nombre (ej: "Cloud Control Panel")
6. Opcionalmente sube un icono
7. Click en "Create"
8. Copia la URL del webhook que aparece

---

## Paso 2: Configurar en Cloud Control Panel

### Desde el panel (⚙️ > Notificaciones > + Agregar canal)

| Campo | Valor |
|-------|-------|
| Tipo | Teams |
| Nombre | Ej: "Teams - Infraestructura" |
| Webhook URL | La URL copiada en el paso anterior |

### En el JSON

```json
{
  "type": "teams",
  "name": "Teams - Infraestructura",
  "config": {
    "webhookUrl": "https://outlook.office.com/webhook/XXXXXXXX/IncomingWebhook/YYYYYYY/ZZZZZZZ"
  },
  "events": ["started", "stopped", "error"],
  "enabled": true
}
```

---

## Verificar que funciona

1. En el panel, click en el boton de avioncito (enviar prueba)
2. Deberia aparecer un mensaje en el canal de Teams configurado

---

## Formato del mensaje

Los mensajes se envian como texto plano usando el formato:

```
started: KiroCrew Server (SebasGao05)
```

Para un formato mas rico (tarjetas adaptivas), se puede implementar en el futuro.

---

## Troubleshooting

### "No llega el mensaje a Teams"
- Verifica que la URL del webhook sea correcta y completa
- Verifica que el conector/workflow este activo en el canal
- Prueba la URL manualmente con curl:
  ```bash
  curl -X POST -H "Content-Type: application/json" -d "{\"text\": \"Test\"}" "TU_WEBHOOK_URL"
  ```

### "Error 400: Bad Request"
- La URL puede haber expirado o el webhook fue eliminado
- Recrea el webhook en Teams

### "Error 403: Forbidden"
- Tu organizacion puede tener restricciones en webhooks externos
- Contacta al administrador de Teams de tu empresa

### Webhook URLs nuevas (Workflows)
- Las URLs nuevas de Workflows lucen diferente: `https://prod-XX.westus.logic.azure.com:443/workflows/...`
- Funcionan igual — solo copia la URL completa

---

## Notas

- Los webhooks de Teams tienen un rate limit de ~4 mensajes por segundo
- Si se eliminan muchos mensajes rapidamente, pueden perderse algunos
- La URL del webhook es un secreto — no la compartas publicamente
- Si rotas el webhook, actualiza la URL en el config y redespliega

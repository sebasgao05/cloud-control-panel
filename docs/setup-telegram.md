# Configurar Notificaciones por Telegram

Guia para configurar el canal de notificaciones via Telegram Bot.

---

## Costo

Gratis. La API de Telegram no tiene costo por enviar mensajes.

---

## Paso 1: Crear un Bot

1. Abre Telegram y busca `@BotFather`
2. Envia el comando `/newbot`
3. BotFather te pedira un nombre para el bot (ej: "Cloud Control Alertas")
4. Luego un username que termine en `bot` (ej: `cloud_control_alertas_bot`)
5. BotFather te dara el **Bot Token** — copialo

Ejemplo de token: `6123456789:AAHx1234567890abcdefghijklmnopqrst`

---

## Paso 2: Obtener el Chat ID

### Opcion A: Notificaciones a un chat privado (tu cuenta personal)

1. Abre una conversacion con tu nuevo bot en Telegram
2. Envialo cualquier mensaje (ej: "hola")
3. Abre en tu navegador: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
4. Busca `"chat":{"id": NUMERO}` — ese NUMERO es tu Chat ID

### Opcion B: Notificaciones a un grupo

1. Crea un grupo en Telegram (o usa uno existente)
2. Agrega tu bot al grupo
3. Envia un mensaje en el grupo
4. Abre: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
5. El Chat ID del grupo sera un numero **negativo** (ej: `-1001234567890`)

### Opcion C: Notificaciones a un canal

1. Crea un canal o usa uno existente
2. Agrega el bot como administrador del canal
3. El Chat ID del canal es `@nombre_del_canal` o el ID numerico negativo

---

## Paso 3: Configurar en Cloud Control Panel

### Desde el panel (⚙️ > Notificaciones > + Agregar canal)

| Campo | Valor |
|-------|-------|
| Tipo | Telegram |
| Nombre | Ej: "Alertas Telegram" |
| Bot Token | El token de BotFather |
| Chat ID | El numero obtenido en paso 2 |

### En el JSON

```json
{
  "type": "telegram",
  "name": "Alertas Telegram",
  "config": {
    "botToken": "6123456789:AAHx1234567890abcdefghijklmnopqrst",
    "chatId": "-1001234567890"
  },
  "events": ["started", "stopped", "error", "scheduler_executed"],
  "enabled": true
}
```

---

## Verificar que funciona

1. En el panel, click en el boton de avioncito (enviar prueba) del canal de Telegram
2. Deberia llegar un mensaje al chat/grupo/canal configurado

---

## Troubleshooting

### "No llega el mensaje"
- Verifica que el bot este en el grupo/canal
- Verifica que el Chat ID sea correcto (los grupos son negativos)
- Verifica que el Bot Token no tenga espacios extra

### "Error 403: Forbidden"
- El bot no tiene permisos para enviar en ese chat
- Si es un canal, el bot debe ser administrador
- Si es un grupo, asegurate de haber enviado al menos un mensaje despues de agregar el bot

### "Error 401: Unauthorized"
- El Bot Token es invalido. Genera uno nuevo con BotFather (`/token`)

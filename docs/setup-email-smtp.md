# Configurar Notificaciones por Email (SMTP)

Guia para configurar el canal de notificaciones por correo electronico usando SMTP.

---

## Opcion 1: Gmail (recomendado para pruebas)

### Prerequisitos

1. Una cuenta de Gmail
2. Verificacion en dos pasos activada en la cuenta

### Pasos

1. Ve a [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. En "Seleccionar aplicacion", elige "Otra (nombre personalizado)"
3. Escribe "Cloud Control Panel" y click en "Generar"
4. Copia la contrasena de 16 caracteres que aparece (ej: `abcd efgh ijkl mnop`)

### Configuracion en el panel

| Campo | Valor |
|-------|-------|
| Destinatario | tu-email@gmail.com (o cualquier email donde recibir alertas) |
| SMTP Host | `smtp.gmail.com` |
| SMTP Puerto | `587` |
| SMTP Usuario | tu-email@gmail.com |

En el JSON, agregar `smtpPass` con la contrasena de aplicacion:

```json
{
  "type": "email",
  "name": "Gmail Alertas",
  "config": {
    "to": "admin@empresa.com",
    "smtpHost": "smtp.gmail.com",
    "smtpPort": 587,
    "smtpUser": "tu-email@gmail.com",
    "smtpPass": "abcdefghijklmnop"
  },
  "events": ["started", "stopped", "error"],
  "enabled": true
}
```

---

## Opcion 2: Outlook / Office 365

### Configuracion

| Campo | Valor |
|-------|-------|
| SMTP Host | `smtp.office365.com` |
| SMTP Puerto | `587` |
| SMTP Usuario | tu-email@outlook.com |
| smtpPass | Tu contrasena o app password |

---

## Opcion 3: SMTP propio (Mailgun, SendGrid free tier, servidor propio)

### Mailgun (gratis hasta 100 emails/dia)

1. Crea cuenta en [https://www.mailgun.com](https://www.mailgun.com)
2. Verifica un dominio o usa el sandbox
3. Obtiene las credenciales SMTP desde el dashboard

| Campo | Valor |
|-------|-------|
| SMTP Host | `smtp.mailgun.org` |
| SMTP Puerto | `587` |
| SMTP Usuario | `postmaster@tu-dominio.mailgun.org` |
| smtpPass | La password del dashboard |

### SendGrid (gratis hasta 100 emails/dia)

1. Crea cuenta en [https://sendgrid.com](https://sendgrid.com)
2. Ve a Settings > API Keys > Create API Key
3. Usa la API key como password

| Campo | Valor |
|-------|-------|
| SMTP Host | `smtp.sendgrid.net` |
| SMTP Puerto | `587` |
| SMTP Usuario | `apikey` (literalmente la palabra "apikey") |
| smtpPass | Tu API key |

---

## Notas importantes

- La contrasena SMTP (`smtpPass`) se configura directamente en el JSON y viaja con el deploy. No se expone en la UI del panel.
- Si usas Gmail, **debes** usar una App Password. La contrasena normal no funciona con SMTP.
- El email se envia directamente desde la Lambda usando `smtplib` de Python (sin SES ni costos AWS).
- Si el SMTP falla (credenciales invalidas, timeout), la accion principal (start/stop) no se ve afectada — la notificacion falla silenciosamente y se registra en los logs de CloudWatch.

---

## Verificar que funciona

1. Configura el canal en el panel (⚙️ > Notificaciones > + Agregar canal)
2. Click en el boton de avioncito (enviar prueba)
3. Revisa tu bandeja de entrada (y spam)

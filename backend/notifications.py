"""
Cloud Control Panel - Notification handlers.
Email, Telegram, and Teams sending.
"""

import json
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from urllib import request as urllib_request

from pydantic import ValidationError

from auth import is_superadmin
from utils import db_delete, db_put, db_query, logger, response
from validators import TestNotificationRequest, UpdateNotificationsRequest, format_validation_errors


def handle_get_notifications(account, user_info):
    """Get notification channels for an account."""
    features = account.get("features", {})
    if not features.get("notifications", False):
        return response(200, {"enabled": False, "canEdit": False, "channels": []})
    if not is_superadmin(user_info):
        return response(200, {"enabled": True, "canEdit": False, "channels": []})
    channels = account.get("notifications", {}).get("channels", [])
    return response(200, {"enabled": True, "canEdit": True, "channels": channels})


def handle_update_notifications(account, account_id, user_info, body):
    """Update notification channels for an account."""
    if not is_superadmin(user_info):
        return response(200, {"error": "Solo superadmin", "denied": True})

    try:
        UpdateNotificationsRequest.model_validate(body)
    except ValidationError as e:
        return response(400, {"error": "Validation error", "details": format_validation_errors(e)})

    existing = db_query(f"ACCOUNT#{account_id}", "CHANNEL#")
    for item in existing:
        db_delete(item["PK"], item["SK"])
    for ch in body.get("channels", []):
        if not ch.get("id"):
            ch["id"] = f"ch-{int(datetime.now(timezone.utc).timestamp())}"
        db_put({"PK": f"ACCOUNT#{account_id}", "SK": f"CHANNEL#{ch['id']}", "data": ch})
    return response(200, {"message": "Notificaciones actualizadas"})


def handle_test_notification(account, user_info, body):
    """Send a test notification to a specific channel."""
    if not is_superadmin(user_info):
        return response(200, {"error": "Solo superadmin", "denied": True})

    try:
        validated = TestNotificationRequest.model_validate(body)
    except ValidationError as e:
        return response(400, {"error": "Validation error", "details": format_validation_errors(e)})

    channel_id = validated.channelId
    channels = account.get("notifications", {}).get("channels", [])
    channel = next((ch for ch in channels if ch["id"] == channel_id), None)
    if not channel:
        return response(200, {"error": "Canal no encontrado"})
    success = send_single_notification(channel, "test", "Notificacion de prueba - Cloud Control Panel", "Cloud Control Panel - Test")
    if success:
        return response(200, {"message": f"Prueba enviada a {channel.get('name')}"})
    return response(200, {"error": f"Error enviando a {channel.get('name')}"})


def send_notifications(account, event, instance_name, user_info=None):
    """Send notifications to all enabled channels for an event."""
    features = account.get("features", {})
    if not features.get("notifications", False):
        return
    user_name = user_info.get("name", "Sistema") if user_info else "Sistema"
    user_role = user_info.get("role", "unknown") if user_info else "scheduler"
    account_name = account.get("name", account.get("id", ""))

    event_labels = {"started": "ENCENDIDO", "stopped": "APAGADO", "error": "ERROR", "scheduler_executed": "SCHEDULER"}
    event_label = event_labels.get(event, event.upper())

    subject = f"[Cloud Control] {event_label}: {instance_name}"
    body = (
        f"\U0001f514 {event_label}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Recurso: {instance_name}\n"
        f"Cuenta: {account_name}\n"
        f"Ejecutado por: {user_name} ({user_role})\n"
        f"Fecha: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Cloud Control Panel"
    )

    for ch in account.get("notifications", {}).get("channels", []):
        if not ch.get("enabled"):
            continue
        if event not in ch.get("events", []):
            continue
        try:
            send_single_notification(ch, event, body, subject)
        except Exception as e:
            logger.error(f"[NOTIFY ERROR] {ch.get('type')} {ch.get('name')}: {e}")


def send_single_notification(channel, event, message, subject=None):
    """Send a single notification to a channel."""
    ch_type = channel.get("type")
    config = channel.get("config", {})
    try:
        if ch_type == "email":
            return send_email(config, message, subject)
        elif ch_type == "telegram":
            return send_telegram(config, message)
        elif ch_type == "teams":
            return send_teams(config, message)
    except Exception as e:
        logger.error(f"[NOTIFY] {ch_type} failed: {e}")
    return False


def send_email(config, message, subject=None):
    """Send an email notification."""
    to_addr = config.get("to")
    if not to_addr:
        return False
    msg = MIMEText(message)
    msg["Subject"] = subject or "Cloud Control Panel - Alerta"
    msg["From"] = config.get("smtpUser", "noreply@cloudcontrol.local")
    msg["To"] = to_addr
    with smtplib.SMTP(config.get("smtpHost", "smtp.gmail.com"), int(config.get("smtpPort", 587)), timeout=10) as s:
        s.starttls()
        if config.get("smtpUser") and config.get("smtpPass"):
            s.login(config["smtpUser"], config["smtpPass"])
        s.sendmail(msg["From"], [to_addr], msg.as_string())
    return True


def send_telegram(config, message):
    """Send a Telegram notification."""
    bot_token = config.get("botToken")
    chat_id = config.get("chatId")
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message}).encode()
    req = urllib_request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib_request.urlopen(req, timeout=10)
    return True


def send_teams(config, message):
    """Send a Microsoft Teams notification."""
    webhook_url = config.get("webhookUrl")
    if not webhook_url:
        return False
    data = json.dumps({"text": message}).encode()
    req = urllib_request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
    urllib_request.urlopen(req, timeout=10)
    return True

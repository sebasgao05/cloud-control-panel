"""
Cloud Control Panel - Mock Server para desarrollo local.

Simula las respuestas de la Lambda para que puedas ver el frontend
funcionando sin desplegar a AWS.

USO:
    python mock/server.py          -> Inicia en http://localhost:8080
    python mock/server.py --port 3000  -> Puerto custom

Las instancias simuladas cambian de estado cuando les das start/stop.
"""

import json
import os
import sys
import time
import random
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

# ─── Configuracion Mock ─────────────────────────────────────────────────

MOCK_CONFIG = {
    "settings": {
        "defaultRegion": "us-east-1",
        "pollIntervalSeconds": 30,
        "timezone": "America/Bogota"
    },
    "apiKeys": {
        "demo": {
            "name": "Demo User (Admin)",
            "role": "admin",
            "accounts": ["*"]
        },
        "sanidad-key": {
            "name": "Equipo Sanidad",
            "role": "operator",
            "accounts": ["sanidad"],
            "scheduler": {
                "view": True,
                "edit": False
            }
        },
        "nuvu-key": {
            "name": "Equipo Nuvu",
            "role": "operator",
            "accounts": ["nuvu-10"],
            "scheduler": {
                "view": False,
                "edit": False
            }
        }
    },
    "accounts": [
        {
            "id": "sanidad",
            "name": "SAN - TEST - Sanidad Wisse",
            "awsAccountId": "111111111111",
            "region": "us-east-1",
            "features": {
                "scheduler": True,
                "notifications": True,
                "costEstimate": True
            },
            "notifications": {
                "channels": [
                    {
                        "id": "ch-1",
                        "type": "email",
                        "name": "Admin Email",
                        "config": {
                            "to": "admin@empresa.com",
                            "smtpHost": "smtp.gmail.com",
                            "smtpPort": 587,
                            "smtpUser": "alerts@empresa.com"
                        },
                        "events": ["started", "stopped", "error"],
                        "enabled": True
                    },
                    {
                        "id": "ch-2",
                        "type": "telegram",
                        "name": "Canal DevOps",
                        "config": {
                            "chatId": "-1001234567890"
                        },
                        "events": ["started", "stopped", "scheduler_executed"],
                        "enabled": True
                    }
                ]
            },
            "schedule": {
                "timezone": "America/Bogota",
                "rules": [
                    {
                        "id": "rule-1",
                        "instances": ["san-app", "san-db"],
                        "startCron": "0 7 * * 1-5",
                        "stopCron": "0 20 * * 1-5",
                        "description": "L-V 7am a 8pm",
                        "enabled": True
                    },
                    {
                        "id": "rule-2",
                        "instances": ["san-worker"],
                        "startCron": "0 6 * * 1-6",
                        "stopCron": "0 22 * * 1-6",
                        "description": "L-S 6am a 10pm",
                        "enabled": False
                    }
                ]
            },
            "instances": [
                {
                    "id": "san-app",
                    "name": "App Server",
                    "instanceId": "i-0a1b2c3d4e5f6a7b8",
                    "instanceType": "t3.medium",
                    "description": "Servidor principal de aplicacion Sanidad",
                    "dashboardPort": 5476,
                    "group": "sanidad-core"
                },
                {
                    "id": "san-db",
                    "name": "Database Server",
                    "instanceId": "i-0b2c3d4e5f6a7b8c9",
                    "instanceType": "r5.large",
                    "description": "PostgreSQL + Redis para Sanidad",
                    "dashboardPort": None,
                    "group": "sanidad-core"
                },
                {
                    "id": "san-worker",
                    "name": "Worker Server",
                    "instanceId": "i-0c3d4e5f6a7b8c9d0",
                    "instanceType": "t3.small",
                    "description": "Procesamiento background jobs",
                    "dashboardPort": 9090,
                    "group": None
                }
            ],
            "groups": [
                {
                    "id": "sanidad-core",
                    "name": "Core Sanidad",
                    "description": "App + DB - se encienden/apagan juntas",
                    "color": "#6366f1",
                    "startOrder": ["san-db", "san-app"],
                    "stopOrder": ["san-app", "san-db"]
                }
            ]
        },
        {
            "id": "nuvu-10",
            "name": "NUV - PROD - Nuvu Account 10",
            "awsAccountId": "222222222222",
            "region": "us-east-1",
            "features": {
                "scheduler": True,
                "notifications": True,
                "costEstimate": True
            },
            "notifications": {
                "channels": [
                    {
                        "id": "ch-3",
                        "type": "teams",
                        "name": "Teams - Infraestructura",
                        "config": {
                            "webhookUrl": "https://outlook.office.com/webhook/example"
                        },
                        "events": ["started", "stopped", "error"],
                        "enabled": False
                    }
                ]
            },
            "schedule": {
                "timezone": "America/Bogota",
                "rules": [
                    {
                        "id": "rule-3",
                        "instances": ["nuvu-main"],
                        "startCron": "0 8 * * 1-5",
                        "stopCron": "0 18 * * 1-5",
                        "description": "L-V 8am a 6pm",
                        "enabled": True
                    }
                ]
            },
            "instances": [
                {
                    "id": "nuvu-main",
                    "name": "Main Server",
                    "instanceId": "i-0d4e5f6a7b8c9d0e1",
                    "instanceType": "t3.large",
                    "description": "Servidor principal Nuvu produccion",
                    "dashboardPort": 5476,
                    "group": None
                },
                {
                    "id": "nuvu-staging",
                    "name": "Staging Server",
                    "instanceId": "i-0e5f6a7b8c9d0e1f2",
                    "instanceType": "t3.medium",
                    "description": "Entorno de pruebas Nuvu",
                    "dashboardPort": 5476,
                    "group": None
                }
            ],
            "groups": []
        }
    ]
}

# ─── Estado simulado de instancias ──────────────────────────────────────

instance_states = {}


def init_states():
    """Inicializar estados aleatorios para las instancias mock."""
    for acc in MOCK_CONFIG["accounts"]:
        for inst in acc["instances"]:
            # Algunas encendidas, algunas apagadas
            is_running = random.choice([True, False])
            instance_states[inst["instanceId"]] = {
                "state": "running" if is_running else "stopped",
                "publicIp": f"54.{random.randint(100,250)}.{random.randint(1,250)}.{random.randint(1,250)}" if is_running else None,
                "launchTime": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 72))) if is_running else None,
            }


init_states()


# ─── API Logic ──────────────────────────────────────────────────────────

def authenticate(headers):
    """Validar API key."""
    key = headers.get("x-api-key", headers.get("X-Api-Key", ""))
    user_info = MOCK_CONFIG["apiKeys"].get(key)
    return user_info


def get_allowed_accounts(user_info):
    """Filtrar cuentas por permisos del usuario."""
    allowed = user_info.get("accounts", [])
    if "*" in allowed:
        return MOCK_CONFIG["accounts"]
    return [acc for acc in MOCK_CONFIG["accounts"] if acc["id"] in allowed]


def find_account(account_id):
    for acc in MOCK_CONFIG["accounts"]:
        if acc["id"] == account_id:
            return acc
    return None


def find_instance(account, instance_id):
    for inst in account.get("instances", []):
        if inst["id"] == instance_id:
            return inst
    return None


def find_group(account, group_id):
    for grp in account.get("groups", []):
        if grp["id"] == group_id:
            return grp
    return None


def handle_api(method, path, headers, body):
    """Procesar request de API mock."""
    user_info = authenticate(headers)
    if not user_info:
        return 401, {"error": "Unauthorized"}

    parts = path.strip("/").split("/")

    # GET /api/accounts
    if method == "GET" and parts == ["api", "accounts"]:
        accounts = get_allowed_accounts(user_info)
        result = []
        for acc in accounts:
            result.append({
                "id": acc["id"],
                "name": acc["name"],
                "awsAccountId": acc["awsAccountId"],
                "region": acc.get("region", "us-east-1"),
                "instanceCount": len(acc.get("instances", [])),
                "groupCount": len(acc.get("groups", [])),
            })
        return 200, {"accounts": result, "user": user_info.get("name", "")}

    # /api/accounts/{accountId}/...
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "accounts":
        account_id = parts[2]
        allowed = get_allowed_accounts(user_info)
        account = None
        for acc in allowed:
            if acc["id"] == account_id:
                account = acc
                break
        if not account:
            return 403, {"error": "Access denied"}

        # GET /api/accounts/{id}/instances
        if len(parts) == 4 and parts[3] == "instances" and method == "GET":
            return handle_list_instances(account)

        # /api/accounts/{id}/instances/{instanceId}/...
        if len(parts) >= 5 and parts[3] == "instances":
            instance_id = parts[4]
            instance = find_instance(account, instance_id)
            if not instance:
                return 404, {"error": "Instance not found"}

            if len(parts) == 6:
                action = parts[5]
                if method == "GET" and action == "status":
                    return handle_instance_status(instance)
                if method == "POST" and action == "start":
                    return handle_instance_start(instance, account)
                if method == "POST" and action == "stop":
                    return handle_instance_stop(instance, account)
                if method == "POST" and action == "update":
                    return handle_instance_update(instance)
                if method == "GET" and action == "dashboard-url":
                    return handle_dashboard_url(instance)

        # /api/accounts/{id}/groups/{groupId}/...
        if len(parts) >= 5 and parts[3] == "groups":
            group_id = parts[4]
            group = find_group(account, group_id)
            if not group:
                return 404, {"error": "Group not found"}

            if len(parts) == 6:
                action = parts[5]
                if method == "GET" and action == "status":
                    return handle_group_status(account, group)
                if method == "POST" and action == "start":
                    return handle_group_start(account, group)
                if method == "POST" and action == "stop":
                    return handle_group_stop(account, group)

        # GET /api/accounts/{id}/schedule
        if len(parts) == 4 and parts[3] == "schedule" and method == "GET":
            return handle_get_schedule(account, user_info)

        # PUT /api/accounts/{id}/schedule
        if len(parts) == 4 and parts[3] == "schedule" and method == "PUT":
            return handle_update_schedule(account, user_info, body)

        # GET /api/accounts/{id}/notifications
        if len(parts) == 4 and parts[3] == "notifications" and method == "GET":
            return handle_get_notifications(account, user_info)

        # PUT /api/accounts/{id}/notifications
        if len(parts) == 4 and parts[3] == "notifications" and method == "PUT":
            return handle_update_notifications(account, user_info, body)

        # POST /api/accounts/{id}/notifications/test
        if len(parts) == 5 and parts[3] == "notifications" and parts[4] == "test" and method == "POST":
            return handle_test_notification(account, user_info, body)

        # GET /api/accounts/{id}/costs
        if len(parts) == 4 and parts[3] == "costs" and method == "GET":
            return handle_get_costs(account, user_info)

    return 404, {"error": "Not found"}


def handle_list_instances(account):
    instances = account.get("instances", [])
    result_instances = []

    for inst in instances:
        state_data = instance_states.get(inst["instanceId"], {"state": "stopped", "publicIp": None, "launchTime": None})
        state = state_data["state"]
        launch_time = state_data["launchTime"]

        uptime = None
        if state == "running" and launch_time:
            delta = datetime.now(timezone.utc) - launch_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes = remainder // 60
            uptime = f"{hours}h {minutes}m"

        result_instances.append({
            "id": inst["id"],
            "name": inst["name"],
            "instanceId": inst["instanceId"],
            "description": inst.get("description", ""),
            "dashboardPort": inst.get("dashboardPort"),
            "group": inst.get("group"),
            "state": state,
            "publicIp": state_data.get("publicIp"),
            "uptime": uptime,
        })

    groups = account.get("groups", [])
    result_groups = []
    for grp in groups:
        member_ids = grp.get("startOrder", [])
        member_states = []
        for mid in member_ids:
            for ri in result_instances:
                if ri["id"] == mid:
                    member_states.append(ri["state"])
                    break

        if all(s == "running" for s in member_states):
            group_state = "running"
        elif all(s == "stopped" for s in member_states):
            group_state = "stopped"
        else:
            group_state = "partial"

        result_groups.append({
            "id": grp["id"],
            "name": grp["name"],
            "description": grp.get("description", ""),
            "color": grp.get("color", "#6366f1"),
            "members": member_ids,
            "state": group_state,
        })

    return 200, {
        "accountId": account["id"],
        "accountName": account["name"],
        "instances": result_instances,
        "groups": result_groups,
    }


def handle_instance_status(instance):
    state_data = instance_states.get(instance["instanceId"], {"state": "stopped", "publicIp": None, "launchTime": None})
    state = state_data["state"]
    launch_time = state_data["launchTime"]

    uptime = None
    if state == "running" and launch_time:
        delta = datetime.now(timezone.utc) - launch_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        uptime = f"{hours}h {minutes}m"

    return 200, {
        "id": instance["id"],
        "name": instance["name"],
        "instanceId": instance["instanceId"],
        "state": state,
        "publicIp": state_data.get("publicIp"),
        "uptime": uptime,
        "dashboardPort": instance.get("dashboardPort"),
        "description": instance.get("description", ""),
        "group": instance.get("group"),
    }


def handle_instance_start(instance, account=None):
    iid = instance["instanceId"]
    instance_states[iid] = {
        "state": "running",
        "publicIp": f"54.{random.randint(100,250)}.{random.randint(1,250)}.{random.randint(1,250)}",
        "launchTime": datetime.now(timezone.utc),
    }
    if account:
        mock_send_notifications(account, "started", instance["name"])
        # Register in activity log for cost tracking
        activity_log.append({
            "accountId": account["id"],
            "instanceId": instance["id"],
            "action": "start",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    return 200, {"message": "Instance starting", "instanceId": iid, "name": instance["name"]}


def handle_instance_stop(instance, account=None):
    iid = instance["instanceId"]
    instance_states[iid] = {
        "state": "stopped",
        "publicIp": None,
        "launchTime": None,
    }
    if account:
        mock_send_notifications(account, "stopped", instance["name"])
        # Register in activity log for cost tracking
        activity_log.append({
            "accountId": account["id"],
            "instanceId": instance["id"],
            "action": "stop",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    return 200, {"message": "Instance stopping", "instanceId": iid, "name": instance["name"]}


def handle_instance_update(instance):
    cmd_id = f"cmd-{random.randint(100000, 999999)}"
    return 200, {"message": "Update started", "commandId": cmd_id, "instanceId": instance["instanceId"]}


def handle_dashboard_url(instance):
    port = instance.get("dashboardPort")
    if not port:
        return 200, {"url": None, "reason": "No dashboard configured"}

    state_data = instance_states.get(instance["instanceId"], {})
    public_ip = state_data.get("publicIp")

    if not public_ip:
        return 200, {"url": None, "reason": "Instance is not running"}

    return 200, {"url": f"http://{public_ip}:{port}"}


def handle_group_status(account, group):
    member_ids = group.get("startOrder", [])
    members = []
    for mid in member_ids:
        inst = find_instance(account, mid)
        if inst:
            state_data = instance_states.get(inst["instanceId"], {"state": "stopped", "publicIp": None})
            members.append({
                "id": inst["id"],
                "name": inst["name"],
                "instanceId": inst["instanceId"],
                "state": state_data["state"],
                "publicIp": state_data.get("publicIp"),
            })

    states = [m["state"] for m in members]
    if all(s == "running" for s in states):
        group_state = "running"
    elif all(s == "stopped" for s in states):
        group_state = "stopped"
    else:
        group_state = "partial"

    return 200, {"group": group["id"], "name": group["name"], "state": group_state, "members": members}


def handle_group_start(account, group):
    started = []
    for member_id in group.get("startOrder", []):
        inst = find_instance(account, member_id)
        if inst:
            handle_instance_start(inst, account)
            started.append({"id": inst["id"], "name": inst["name"]})
    return 200, {"message": "Group starting", "group": group["id"], "started": started}


def handle_group_stop(account, group):
    stopped = []
    for member_id in group.get("stopOrder", []):
        inst = find_instance(account, member_id)
        if inst:
            handle_instance_stop(inst, account)
            stopped.append({"id": inst["id"], "name": inst["name"]})
    return 200, {"message": "Group stopping", "group": group["id"], "stopped": stopped}


# ─── Scheduler Handlers ─────────────────────────────────────────────────

def get_scheduler_permissions(user_info):
    """Determinar permisos de scheduler para el usuario."""
    role = user_info.get("role", "operator")
    if role == "admin":
        return {"view": True, "edit": True}

    scheduler_config = user_info.get("scheduler", {})
    can_edit = scheduler_config.get("edit", False)
    # edit implica view
    can_view = can_edit or scheduler_config.get("view", False)
    return {"view": can_view, "edit": can_edit}


def handle_get_schedule(account, user_info):
    """Get schedule rules for an account."""
    permissions = get_scheduler_permissions(user_info)

    # Check if scheduler feature is enabled for this account
    features = account.get("features", {})
    if not features.get("scheduler", False):
        return 200, {
            "enabled": False,
            "permissions": {"view": False, "edit": False},
            "schedule": None
        }

    if not permissions["view"]:
        return 200, {
            "enabled": True,
            "permissions": {"view": False, "edit": False},
            "schedule": None
        }

    schedule = account.get("schedule", {"timezone": "America/Bogota", "rules": []})
    instances = account.get("instances", [])

    # Include instance names for display
    instance_map = {inst["id"]: inst["name"] for inst in instances}

    return 200, {
        "enabled": True,
        "permissions": permissions,
        "schedule": schedule,
        "instanceMap": instance_map
    }


def handle_update_schedule(account, user_info, body):
    """Update schedule rules for an account."""
    permissions = get_scheduler_permissions(user_info)

    if not permissions["edit"]:
        return 200, {"error": "No tienes permiso para editar el programador", "denied": True}

    features = account.get("features", {})
    if not features.get("scheduler", False):
        return 200, {"error": "Scheduler no esta habilitado para esta cuenta", "denied": True}

    if not body or "rules" not in body:
        return 400, {"error": "Body debe contener 'rules'"}

    # Update rules in memory (mock)
    if "schedule" not in account:
        account["schedule"] = {"timezone": "America/Bogota", "rules": []}

    account["schedule"]["rules"] = body["rules"]
    if "timezone" in body:
        account["schedule"]["timezone"] = body["timezone"]

    return 200, {
        "message": "Programacion actualizada",
        "schedule": account["schedule"]
    }


# ─── Notifications Handlers ──────────────────────────────────────────────

def mock_send_notifications(account, event, instance_name):
    """Simulate sending notifications for an event."""
    features = account.get("features", {})
    if not features.get("notifications", False):
        return

    channels = account.get("notifications", {}).get("channels", [])
    for ch in channels:
        if not ch.get("enabled", False):
            continue
        if event not in ch.get("events", []):
            continue
        print(f"  [NOTIFY] [{ch['type'].upper()}] {ch['name']} -> {event}: {instance_name} ({account['name']})")


def handle_get_notifications(account, user_info):
    """Get notification channels for an account. Only admins can see/edit."""
    role = user_info.get("role", "operator")

    features = account.get("features", {})
    if not features.get("notifications", False):
        return 200, {
            "enabled": False,
            "canEdit": False,
            "channels": []
        }

    if role != "admin":
        return 200, {
            "enabled": True,
            "canEdit": False,
            "channels": []
        }

    notifications = account.get("notifications", {"channels": []})
    return 200, {
        "enabled": True,
        "canEdit": True,
        "channels": notifications.get("channels", [])
    }


def handle_update_notifications(account, user_info, body):
    """Update notification channels. Only admins."""
    role = user_info.get("role", "operator")
    if role != "admin":
        return 200, {"error": "Solo admins pueden editar notificaciones", "denied": True}

    features = account.get("features", {})
    if not features.get("notifications", False):
        return 200, {"error": "Notificaciones no habilitadas", "denied": True}

    if not body or "channels" not in body:
        return 400, {"error": "Body debe contener 'channels'"}

    if "notifications" not in account:
        account["notifications"] = {"channels": []}

    account["notifications"]["channels"] = body["channels"]

    return 200, {
        "message": "Notificaciones actualizadas",
        "channels": account["notifications"]["channels"]
    }


def handle_test_notification(account, user_info, body):
    """Send a test notification. Only admins."""
    role = user_info.get("role", "operator")
    if role != "admin":
        return 200, {"error": "Solo admins pueden probar notificaciones", "denied": True}

    channel_id = body.get("channelId") if body else None
    if not channel_id:
        return 400, {"error": "Falta channelId"}

    channels = account.get("notifications", {}).get("channels", [])
    channel = next((ch for ch in channels if ch["id"] == channel_id), None)
    if not channel:
        return 404, {"error": "Canal no encontrado"}

    # Mock: simulate sending
    ch_type = channel.get("type", "unknown")
    ch_name = channel.get("name", "")
    print(f"  [NOTIFICATION TEST] type={ch_type} name={ch_name} account={account['id']}")

    return 200, {
        "message": f"Notificacion de prueba enviada a {ch_name}",
        "channel": channel["id"],
        "type": ch_type
    }


# ─── Cost Estimation ─────────────────────────────────────────────────────

# Precios por hora On-Demand (us-east-1, Linux) - tabla local simplificada
EC2_PRICING = {
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
}

# Simulated activity log for the current month
# In production, this would be stored in DynamoDB
activity_log = []


def init_activity_log():
    """Generate mock activity history for the current month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    for acc in MOCK_CONFIG["accounts"]:
        for inst in acc["instances"]:
            # Simulate some start/stop cycles this month
            num_cycles = random.randint(8, 20)
            current_time = month_start + timedelta(hours=random.randint(6, 10))

            for _ in range(num_cycles):
                if current_time >= now:
                    break
                # Start event
                activity_log.append({
                    "accountId": acc["id"],
                    "instanceId": inst["id"],
                    "action": "start",
                    "timestamp": current_time.isoformat()
                })
                # Run for 8-14 hours
                run_hours = random.uniform(8, 14)
                stop_time = current_time + timedelta(hours=run_hours)
                if stop_time >= now:
                    break  # Still running
                # Stop event
                activity_log.append({
                    "accountId": acc["id"],
                    "instanceId": inst["id"],
                    "action": "stop",
                    "timestamp": stop_time.isoformat()
                })
                # Off for 8-16 hours
                off_hours = random.uniform(8, 16)
                current_time = stop_time + timedelta(hours=off_hours)


init_activity_log()


def calculate_uptime_hours(instance_id, account_id):
    """Calculate total uptime hours this month for an instance."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    events = [e for e in activity_log
              if e["instanceId"] == instance_id and e["accountId"] == account_id]
    events.sort(key=lambda e: e["timestamp"])

    total_seconds = 0
    last_start = None

    for event in events:
        ts = datetime.fromisoformat(event["timestamp"])
        if ts < month_start:
            continue
        if event["action"] == "start":
            last_start = ts
        elif event["action"] == "stop" and last_start:
            total_seconds += (ts - last_start).total_seconds()
            last_start = None

    # If currently running, add time since last start
    if last_start:
        total_seconds += (now - last_start).total_seconds()

    return total_seconds / 3600


def handle_get_costs(account, user_info):
    """Get cost estimation for all instances in an account."""
    features = account.get("features", {})
    if not features.get("costEstimate", False):
        return 200, {"enabled": False, "costs": []}

    now = datetime.now(timezone.utc)
    days_in_month = 30
    days_elapsed = now.day

    instances = account.get("instances", [])
    costs = []
    total_cost = 0

    for inst in instances:
        instance_type = inst.get("instanceType", "t3.medium")
        hourly_rate = EC2_PRICING.get(instance_type, 0.0416)
        uptime_hours = calculate_uptime_hours(inst["id"], account["id"])
        cost = uptime_hours * hourly_rate
        total_cost += cost

        # Projection: (cost / days_elapsed) * days_in_month
        projection = (cost / max(days_elapsed, 1)) * days_in_month

        costs.append({
            "id": inst["id"],
            "name": inst["name"],
            "instanceType": instance_type,
            "hourlyRate": hourly_rate,
            "uptimeHours": round(uptime_hours, 1),
            "costThisMonth": round(cost, 2),
            "projection": round(projection, 2),
        })

    total_projection = (total_cost / max(days_elapsed, 1)) * days_in_month

    return 200, {
        "enabled": True,
        "month": now.strftime("%B %Y"),
        "daysElapsed": days_elapsed,
        "costs": costs,
        "totalCost": round(total_cost, 2),
        "totalProjection": round(total_projection, 2),
        "currency": "USD"
    }


# ─── HTTP Server ────────────────────────────────────────────────────────

class MockHandler(SimpleHTTPRequestHandler):
    """Servidor que sirve frontend estatico + API mock."""

    def __init__(self, *args, **kwargs):
        # Servir archivos desde frontend/
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
        super().__init__(*args, directory=frontend_dir, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("GET", parsed.path)
        else:
            # Servir archivos estaticos
            if parsed.path == "/" or not os.path.splitext(parsed.path)[1]:
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("POST", parsed.path)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("PUT", parsed.path)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def _handle_api(self, method, path):
        # Leer body si existe
        content_length = int(self.headers.get("Content-Length", 0))
        body = None
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = None

        # Headers como dict
        headers = {k.lower(): v for k, v in self.headers.items()}

        # Simular latencia de red (~100-300ms)
        time.sleep(random.uniform(0.1, 0.3))

        status, response_body = handle_api(method, path, headers, body)

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response_body, default=str).encode())

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")

    def log_message(self, format, *args):
        """Custom log format."""
        method_path = args[0] if args else ""
        status = args[1] if len(args) > 1 else ""
        if "/api/" in str(method_path):
            print(f"  [{status}] {method_path}")
        # Silenciar logs de archivos estaticos para reducir ruido


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    port = 8080

    # Argumento --port
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    print("")
    print("  +==========================================+")
    print("  |   Cloud Control Panel - Mock Server      |")
    print("  +==========================================+")
    print(f"  |  URL:  http://localhost:{port}            |")
    print("  |                                          |")
    print("  |  API Keys de prueba:                     |")
    print('  |    "demo"         -> Admin (ve todo)     |')
    print('  |    "sanidad-key"  -> Operador (view)     |')
    print('  |    "nuvu-key"     -> Operador (no sched) |')
    print("  |                                          |")
    print("  |  Features: Scheduler, Notificaciones     |")
    print("  |                                          |")
    print("  |  Ctrl+C para detener                     |")
    print("  +==========================================+")
    print("")

    server = HTTPServer(("0.0.0.0", port), MockHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Mock server detenido.")
        server.shutdown()


if __name__ == "__main__":
    main()

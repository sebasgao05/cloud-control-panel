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
            "accounts": ["sanidad"]
        },
        "nuvu-key": {
            "name": "Equipo Nuvu",
            "role": "operator",
            "accounts": ["nuvu-10"]
        }
    },
    "accounts": [
        {
            "id": "sanidad",
            "name": "SAN - TEST - Sanidad Wisse",
            "awsAccountId": "111111111111",
            "region": "us-east-1",
            "instances": [
                {
                    "id": "san-app",
                    "name": "App Server",
                    "instanceId": "i-0a1b2c3d4e5f6a7b8",
                    "description": "Servidor principal de aplicacion Sanidad",
                    "dashboardPort": 5476,
                    "group": "sanidad-core"
                },
                {
                    "id": "san-db",
                    "name": "Database Server",
                    "instanceId": "i-0b2c3d4e5f6a7b8c9",
                    "description": "PostgreSQL + Redis para Sanidad",
                    "dashboardPort": None,
                    "group": "sanidad-core"
                },
                {
                    "id": "san-worker",
                    "name": "Worker Server",
                    "instanceId": "i-0c3d4e5f6a7b8c9d0",
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
            "instances": [
                {
                    "id": "nuvu-main",
                    "name": "Main Server",
                    "instanceId": "i-0d4e5f6a7b8c9d0e1",
                    "description": "Servidor principal Nuvu produccion",
                    "dashboardPort": 5476,
                    "group": None
                },
                {
                    "id": "nuvu-staging",
                    "name": "Staging Server",
                    "instanceId": "i-0e5f6a7b8c9d0e1f2",
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
                    return handle_instance_start(instance)
                if method == "POST" and action == "stop":
                    return handle_instance_stop(instance)
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


def handle_instance_start(instance):
    iid = instance["instanceId"]
    instance_states[iid] = {
        "state": "running",
        "publicIp": f"54.{random.randint(100,250)}.{random.randint(1,250)}.{random.randint(1,250)}",
        "launchTime": datetime.now(timezone.utc),
    }
    return 200, {"message": "Instance starting", "instanceId": iid, "name": instance["name"]}


def handle_instance_stop(instance):
    iid = instance["instanceId"]
    instance_states[iid] = {
        "state": "stopped",
        "publicIp": None,
        "launchTime": None,
    }
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
            handle_instance_start(inst)
            started.append({"id": inst["id"], "name": inst["name"]})
    return 200, {"message": "Group starting", "group": group["id"], "started": started}


def handle_group_stop(account, group):
    stopped = []
    for member_id in group.get("stopOrder", []):
        inst = find_instance(account, member_id)
        if inst:
            handle_instance_stop(inst)
            stopped.append({"id": inst["id"], "name": inst["name"]})
    return 200, {"message": "Group stopping", "group": group["id"], "stopped": stopped}


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
    print('  |    "sanidad-key"  -> Solo cuenta Sanidad |')
    print('  |    "nuvu-key"     -> Solo cuenta Nuvu    |')
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

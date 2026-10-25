import os
import sys
import json
import time
import threading
from datetime import datetime
from flask import Flask, send_from_directory, request, jsonify, redirect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERS_FILE = os.path.join(BASE_DIR, "sales_orders.json")
SECRET_SALT = b"BATTERY_ALARM_SECRET_PRO_KEY_2026"

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# =====================================================================
# CORS SUPPORT FOR ALL API ENDPOINTS
# =====================================================================
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Event-Name, X-Signature"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
    return response

# =====================================================================
# PERSISTENCIA DE PEDIDOS EN JSON
# =====================================================================
def load_orders():
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # Filtrar cualquier orden de prueba previa
                    return [o for o in data if o.get("order_id") != "#4845921" and o.get("customer") != "Cristian Aguilar"]
        except Exception as e:
            print(f"[Server] Error leyendo {ORDERS_FILE}: {e}")
    return []

def save_orders(orders):
    try:
        # Filtrar ordenes de prueba antes de guardar
        clean = [o for o in orders if o.get("order_id") != "#4845921" and o.get("customer") != "Cristian Aguilar"]
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Server] Error guardando {ORDERS_FILE}: {e}")
        return False

# =====================================================================
# RUTAS ESTÁTICAS Y DE NAVEGACIÓN
# =====================================================================
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/admin")
@app.route("/admin.html")
def admin():
    return send_from_directory(BASE_DIR, "admin.html")

@app.route("/privacy")
@app.route("/privacy.html")
def privacy():
    return send_from_directory(BASE_DIR, "privacy.html")

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(BASE_DIR, "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/app_icon.png")
def app_icon():
    return send_from_directory(BASE_DIR, "app_icon.png", mimetype="image/png")

@app.route("/crisdl_software_logo.png")
def logo():
    return send_from_directory(BASE_DIR, "crisdl_software_logo.png", mimetype="image/png")

@app.route("/store")
def store_redirect():
    return redirect("ms-windows-store://pdp/?productid=9N32Z1F7R2VD")

# =====================================================================
# API: CONSULTA DE PEDIDOS Y ESTADO
# =====================================================================
@app.route("/health")
def health():
    uptime = int(time.time() - _SERVER_START_TIME)
    orders = load_orders()
    return jsonify({
        "status": "healthy",
        "service": "CrisDL Software Sales Backend",
        "uptime_seconds": uptime,
        "orders_count": len(orders),
        "timestamp": time.time()
    }), 200

@app.route("/api/orders", methods=["GET", "OPTIONS"])
def api_get_orders():
    if request.method == "OPTIONS":
        return "", 204
    orders = load_orders()
    return jsonify({
        "success": True,
        "count": len(orders),
        "orders": orders
    })

# =====================================================================
# API: WEBHOOK DE LEMON SQUEEZY (RECEPCIÓN AUTOMÁTICA EN VIVO)
# =====================================================================
@app.route("/api/webhook", methods=["POST", "OPTIONS"])
def api_webhook():
    if request.method == "OPTIONS":
        return "", 204

    payload = request.get_json(silent=True) or {}
    meta = payload.get("meta", {})
    event_name = meta.get("event_name") or request.headers.get("X-Event-Name", "order_created")
    data = payload.get("data", {})
    attrs = data.get("attributes", {})

    print(f"[Webhook] Evento recibido: {event_name}")

    if event_name in ["order_created", "subscription_created"]:
        order_num = attrs.get("order_number") or data.get("id") or str(int(time.time()))
        order_id = f"#{order_num}"
        customer = attrs.get("user_name") or "Cliente Lemon Squeezy"
        email = attrs.get("user_email") or "cliente@lemonsqueezy.com"
        amount = attrs.get("total_formatted") or "$80.99 USD / $19.99 USD"
        status = attrs.get("status_formatted") or ("Pagado" if attrs.get("status") == "paid" else "Completado")
        raw_date = attrs.get("created_at")
        
        # Formatear fecha
        formatted_date = time.strftime("%Y-%m-%d %H:%M")
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                formatted_date = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        # Buscar si viene clave de licencia
        first_item = attrs.get("first_order_item", {})
        key = attrs.get("license_key") or f"LEMON-{order_num}"

        orders = load_orders()
        # Evitar duplicados por order_id
        if not any(o.get("order_id") == order_id for o in orders):
            new_order = {
                "order_id": order_id,
                "customer": customer,
                "email": email,
                "amount": amount,
                "key": key,
                "status": f"{status} (En Vivo)",
                "date": formatted_date,
                "device": "PC Windows"
            }
            orders.insert(0, new_order)
            save_orders(orders)
            print(f"[Webhook] ¡Nueva venta registrada en vivo!: {order_id} de {customer} ({amount})")

    return jsonify({"status": "received", "event": event_name}), 200

# =====================================================================
# API: SINCRONIZACIÓN MANUAL DIRECTA CON LA API DE LEMON SQUEEZY
# =====================================================================
@app.route("/api/sync-lemon", methods=["POST", "OPTIONS"])
def api_sync_lemon():
    if request.method == "OPTIONS":
        return "", 204

    req_data = request.get_json(silent=True) or {}
    api_key = req_data.get("api_key") or os.environ.get("LEMON_SQUEEZY_API_KEY")

    if not api_key:
        return jsonify({
            "success": False, 
            "message": "Falta la API Key de Lemon Squeezy. Ingrésala en la pestaña Conexión API."
        }), 400

    try:
        import urllib.request
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CrisDL-Admin/1.0"
        }
        url = "https://api.lemonsqueezy.com/v1/orders?page[size]=50&sort=-createdAt"
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=15) as resp:
            lemon_data = json.loads(resp.read().decode("utf-8"))

        orders_list = load_orders()
        synced_count = 0

        for item in lemon_data.get("data", []):
            attrs = item.get("attributes", {})
            order_num = attrs.get("order_number") or item.get("id")
            order_id = f"#{order_num}"
            
            # Omitir orden de prueba
            if order_id == "#4845921" or attrs.get("user_email") == "criszafiro9403@gmail.com":
                continue

            customer = attrs.get("user_name") or "Cliente Oficial"
            email = attrs.get("user_email") or "cliente@gmail.com"
            amount = attrs.get("total_formatted") or "$80.99 USD / $19.99 USD"
            status = attrs.get("status_formatted") or "Pagado"
            raw_date = attrs.get("created_at")

            formatted_date = time.strftime("%Y-%m-%d %H:%M")
            if raw_date:
                try:
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            if not any(o.get("order_id") == order_id for o in orders_list):
                orders_list.append({
                    "order_id": order_id,
                    "customer": customer,
                    "email": email,
                    "amount": amount,
                    "key": f"LEMON-{order_num}",
                    "status": status,
                    "date": formatted_date,
                    "device": "PC Windows"
                })
                synced_count += 1

        save_orders(orders_list)
        return jsonify({
            "success": True,
            "message": f"Sincronización exitosa. {synced_count} nuevas ventas añadidas.",
            "total_orders": len(orders_list),
            "orders": orders_list
        })

    except Exception as e:
        print(f"[Sync] Error conectando con Lemon Squeezy: {e}")
        return jsonify({
            "success": False,
            "message": f"Error conectando con Lemon Squeezy: {str(e)}"
        }), 500

# =====================================================================
# SISTEMA DE PREVENCIÓN DE SUSPENSIÓN 24/7 PARA RENDER (ANTI-SLEEP)
# =====================================================================
_SERVER_START_TIME = time.time()
_keep_alive_started = False
_keep_alive_lock = threading.Lock()

def _keep_alive_worker():
    time.sleep(45)
    while True:
        try:
            target_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://battery-alarm-pro.onrender.com"
            ping_url = f"{target_url.rstrip('/')}/health"
            req = urllib.request.Request(
                ping_url,
                headers={"User-Agent": "BatteryAlarm-KeepAlive/2.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                print(f"[AntiSleep] Auto-ping a {ping_url} exitoso (HTTP {resp.getcode()}) a las {time.strftime('%H:%M:%S')}")
        except Exception as e:
            try:
                port = os.environ.get("PORT", "5000")
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
            except Exception:
                pass
            print(f"[AntiSleep] Notificación keep-alive: {e}")
        time.sleep(540) # 9 minutos

def start_keep_alive():
    global _keep_alive_started
    with _keep_alive_lock:
        if not _keep_alive_started:
            _keep_alive_started = True
            t = threading.Thread(target=_keep_alive_worker, daemon=True, name="RenderAntiSleepDaemon")
            t.start()
            print("[AntiSleep] Daemon iniciado correctamente.")

start_keep_alive()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] CrisDL Software Server activo en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, flash, session
import json
import os
from datetime import datetime
from contextlib import closing
from waitress import serve
from functools import wraps

# --- Конфігурація ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

USERNAME = "admin"
PASSWORD = "1234"

DATA_FILE = "devices.json"
OTA_CONFIG_FILE = "firmware_version.json"
FIRMWARE_DIR = "up"
OFFLINE_TIMEOUT = 180  # секунди

# --- Ініціалізація ---
if not os.path.exists(FIRMWARE_DIR):
    os.makedirs(FIRMWARE_DIR)
    print(f"📁 Створено каталог прошивок: {os.path.abspath(FIRMWARE_DIR)}")

devices = {}
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            devices = json.load(f)
    except json.JSONDecodeError:
        print("⚠️ JSON помилка в devices.json")

def load_ota_config():
    if os.path.exists(OTA_CONFIG_FILE):
        with open(OTA_CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ JSON помилка в firmware_version.json")
    return {"version": "0.0.0", "file_name": "", "target_name": "main.py"}

def save_ota_config(config):
    with open(OTA_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# --- Авторизація ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            flash("Вхід виконано успішно", "success")
            return redirect(url_for("monitor_page"))
        else:
            flash("Невірний логін або пароль", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    flash("Ви вийшли з системи", "info")
    return redirect(url_for("login"))

# --- Сторінки ---
@app.route("/")
@login_required
def monitor_page():
    return render_template("monitor.html", active_page="monitor", OFFLINE_TIMEOUT=OFFLINE_TIMEOUT)

@app.route("/devices")
@login_required
def devices_page():
    return render_template("index.html", active_page="devices", OFFLINE_TIMEOUT=OFFLINE_TIMEOUT)

@app.route("/ota")
@login_required
def ota_page():
    config = load_ota_config()
    scripts = sorted(os.listdir(FIRMWARE_DIR)) if os.path.exists(FIRMWARE_DIR) else []
    scripts = [f for f in scripts if os.path.isfile(os.path.join(FIRMWARE_DIR, f))]
    return render_template("ota.html",
                           active_page="ota",
                           config=config,
                           scripts=scripts,
                           FIRMWARE_DIR_NAME=FIRMWARE_DIR)

# --- API ---
@app.route("/api/devices")
@login_required
def get_devices_api():
    now = datetime.now()
    to_delete = []

    for mac, dev in list(devices.items()):
        try:
            last = datetime.strptime(dev.get("last_seen", ""), "%Y-%m-%d %H:%M:%S")
            if (now - last).total_seconds() > OFFLINE_TIMEOUT:
                to_delete.append(mac)
        except:
            to_delete.append(mac)

    for mac in to_delete:
        devices.pop(mac, None)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)

    return jsonify(devices)

@app.route("/data", methods=["POST"])
def receive_data():
    payload = request.get_json()
    if not payload or "mac" not in payload:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    mac = payload["mac"]
    name = payload.get("name", f"Node_{mac[-5:].replace(':', '')}")
    data = payload.get("data", {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    devices[mac] = {"name": name, "data": data, "last_seen": now_str}

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)

    return jsonify({"status": "ok"})

@app.route("/ota/set_active", methods=["POST"])
@login_required
def set_active_firmware():
    version = request.form.get("version")
    file_name = request.form.get("file_name")
    target_name = request.form.get("target_name", "main.py")

    if not version or not file_name:
        flash("Версія та файл обов'язкові", "warning")
        return redirect(url_for("ota_page"))

    config = load_ota_config()
    config["version"] = version.strip()
    config["file_name"] = file_name.strip()
    config["target_name"] = target_name.strip()
    save_ota_config(config)

    flash(f"Глобальна версія OTA встановлена: {version}", "success")
    return redirect(url_for("ota_page"))

@app.route("/ota/set_device_specific", methods=["POST"])
@login_required
def set_device_firmware():
    name = request.form.get("name")
    file_name = request.form.get("file_name")
    version = request.form.get("version")
    target_name = request.form.get("target_name")

    if not (name and file_name and version):
        flash("Всі поля обов'язкові", "danger")
        return redirect(url_for("ota_page"))

    config = load_ota_config()
    config[name] = {
        "version": version.strip(),
        "file_name": file_name.strip(),
        "target_name": target_name.strip() or "main.py"
    }
    save_ota_config(config)

    flash(f"OTA призначено для {name}", "success")
    return redirect(url_for("ota_page"))

@app.route("/firmware_version.json")
def get_firmware_version_info_for_esp():
    name = request.args.get("name", "").strip()
    config = load_ota_config()
    return jsonify(config.get(name) or config.get("global") or {})

@app.route("/firmware_files/<path:filename>")
def download_firmware_file_for_esp(filename):
    try:
        return send_from_directory(FIRMWARE_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

# --- Запуск ---
if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 5005
    serve(app, host=HOST, port=PORT)

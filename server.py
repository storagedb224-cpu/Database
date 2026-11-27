import json
import threading
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
import requests
from flask import Flask, request, jsonify, make_response
from waitress import serve

import config
from course_vault_db import course_vault_db, ram_cache
from course_scanner import course_scanner, clean_jwt_token, extract_uid_from_jwt

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def send_tg_alert(text):
    cfg = course_vault_db.get_admin_settings()
    bot_tok = config.BOT_TOKEN
    if not bot_tok and cfg.get("tg_bots"):
        active = [b for b in cfg["tg_bots"] if b.get("active", True) and b.get("token")]
        if active:
            bot_tok = active[0]["token"]
    chat_ids = list(config.ADMIN_IDS or [])
    if cfg.get("admin_alert_chat_id"):
        chat_ids.append(str(cfg["admin_alert_chat_id"]).strip())
    if not bot_tok or not chat_ids:
        return
    url = f"https://api.telegram.org/bot{bot_tok}/sendMessage"
    for cid in set(str(x) for x in chat_ids if x):
        try:
            requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception:
            pass


course_scanner.alert_callback = send_tg_alert


def _cors(resp):
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    if origin and (not config.ALLOWED_ORIGINS or origin.lower() in config.ALLOWED_ORIGINS):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    else:
        resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Course-Admin-Key"
    resp.headers["Access-Control-Max-Age"] = "600"
    return resp


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))
    return None


@app.after_request
def apply_cors(resp):
    return _cors(resp)


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = (request.headers.get("X-Course-Admin-Key") or request.args.get("key") or "").strip()
        if key != config.ADMIN_KEY:
            return jsonify({"status": "error", "message": "Invalid Course Admin Key"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "RWA Course Vault Backend v2 (Double Backup)",
        "course_dbs": len(course_vault_db.dbs),
        "scanner_running": course_scanner.get_status().get("running", False),
        "termux_worker_online": course_vault_db.get_worker_heartbeat().get("online", False)
    }), 200


# ---------------- PUBLIC PORTAL READ APIs ----------------
@app.route("/api/cv/courses", methods=["GET"])
def api_cv_courses():
    return jsonify({"status": "success", "courses": course_vault_db.get_all_courses()})


@app.route("/api/cv/subjects/<course_id>", methods=["GET"])
def api_cv_subjects(course_id):
    return jsonify({"status": "success", "subjects": course_vault_db.get_course_subjects(course_id)})


@app.route("/api/cv/topics/<course_id>/<subject_id>", methods=["GET"])
def api_cv_topics(course_id, subject_id):
    return jsonify({"status": "success", "topics": course_vault_db.get_subject_topics(course_id, subject_id)})


@app.route("/api/cv/lectures/<course_id>/<subject_id>/<topic_id>", methods=["GET"])
def api_cv_lectures(course_id, subject_id, topic_id):
    return jsonify({"status": "success", "lectures": course_vault_db.get_topic_lectures(course_id, subject_id, topic_id)})


@app.route("/api/cv/lecture/<lecture_id>", methods=["GET"])
def api_cv_single_lecture(lecture_id):
    doc = course_vault_db.get_single_lecture(lecture_id)
    if not doc:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": "success", "lecture": doc})


# ---------------- WORKER APIs ----------------
@app.route("/api/worker/next_lecture", methods=["GET"])
def api_worker_next_lecture():
    doc = course_vault_db.claim_next_lecture_one_by_one()
    if not doc:
        return jsonify({"status": "success", "lecture": None}), 200
    fresh = course_scanner

import threading
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
import requests
from flask import Flask, request, jsonify, make_response
from waitress import serve

import config
from course_vault_db import course_vault_db, ram_cache
from course_scanner import course_scanner

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def send_tg_alert(text):
    if not config.BOT_TOKEN or not config.ADMIN_IDS:
        return
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
    for aid in config.ADMIN_IDS:
        try:
            requests.post(url, json={"chat_id": aid, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception:
            pass


course_scanner.alert_callback = send_tg_alert


# =========================================================
# CORS & ADMIN AUTH MIDDLEWARE
# =========================================================
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


# =========================================================
# HEALTH CHECK
# =========================================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "RWA Course Vault Backend",
        "course_dbs": len(course_vault_db.dbs),
        "scanner_running": course_scanner.get_status().get("running", False),
        "termux_worker_online": course_vault_db.get_worker_heartbeat().get("online", False)
    }), 200


# =========================================================
# PUBLIC READ-ONLY COURSE VAULT APIs (FOR RWA SKY PORTAL)
# =========================================================
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


# =========================================================
# ADMIN PANEL APIs (SUMMARY, SCANNER, TOKENS, OVERRIDE)
# =========================================================
@app.route("/api/admin/auth", methods=["POST"])
def api_admin_auth():
    data = request.get_json(silent=True) or {}
    if str(data.get("key") or "").strip() == config.ADMIN_KEY:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Wrong Admin Key!"}), 401


@app.route("/api/admin/summary", methods=["GET"])
@require_admin
def api_admin_summary():
    return jsonify({
        "status": "success",
        "summary": course_vault_db.get_direct_summary(),
        "scan": course_scanner.get_status()
    })


@app.route("/api/admin/scan/start", methods=["POST"])
@require_admin
def api_admin_scan_start():
    ok, msg = course_scanner.start_scan(mode="manual")
    return jsonify({"status": "success" if ok else "error", "message": msg, "scan": course_scanner.get_status()})


@app.route("/api/admin/scan/stop", methods=["POST"])
@require_admin
def api_admin_scan_stop():
    ok, msg = course_scanner.stop_scan()
    return jsonify({"status": "success" if ok else "error", "message": msg, "scan": course_scanner.get_status()})


@app.route("/api/admin/scan/status", methods=["GET"])
@require_admin
def api_admin_scan_status():
    return jsonify({
        "status": "success",
        "scan": course_scanner.get_status(),
        "summary": course_vault_db.get_direct_summary()
    })


@app.route("/api/admin/tokens", methods=["GET", "POST", "DELETE"])
@require_admin
def api_admin_tokens():
    if request.method == "GET":
        return jsonify({"status": "success", "tokens": course_vault_db.get_scanner_tokens()})
    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        ok = course_vault_db.upsert_scanner_token(data.get("user_id", ""), data.get("token", ""), data.get("label", "Scanner"))
        return jsonify({"status": "success" if ok else "error"})
    ok = course_vault_db.delete_scanner_token(data.get("user_id", ""))
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/course/mode", methods=["POST"])
@require_admin
def api_admin_course_mode():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.set_course_playback_mode(data.get("course_id", ""), data.get("mode", "vault_first"))
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/lecture/override", methods=["POST"])
@require_admin
def api_admin_lecture_override():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.manual_override_lecture(
        lecture_id=data.get("lecture_id", ""),
        yt_video_id=data.get("yt_video_id", ""),
        drive_pdf1_id=data.get("drive_pdf1_id", ""),
        drive_pdf2_id=data.get("drive_pdf2_id", ""),
        drive_thumb_id=data.get("drive_thumb_id", "")
    )
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/queue/retry_failed", methods=["POST"])
@require_admin
def api_admin_retry_failed():
    data = request.get_json(silent=True) or {}
    cnt = course_vault_db.reset_failed_lectures_to_pending(data.get("lecture_id", ""))
    return jsonify({"status": "success", "reset_count": cnt})


@app.route("/api/admin/cache/flush", methods=["POST"])
@require_admin
def api_admin_flush():
    cleared = ram_cache.clear_all()
    return jsonify({"status": "success", "cleared": cleared})


# =========================================================
# NIGHTLY 11:00 PM IST AUTOMATIC METADATA SCANNER
# =========================================================
def start_nightly_scheduler():
    last_date = None

    def _loop():
        nonlocal last_date
        while True:
            try:
                now = datetime.now(IST)
                today = now.strftime("%Y-%m-%d")
                if now.hour == config.NIGHTLY_SCAN_HOUR_IST and last_date != today:
                    last_date = today
                    ok, msg = course_scanner.start_scan(mode="nightly")
                    print(f"🕚 [Nightly Course Scanner] {today}: ok={ok} | {msg}")
            except Exception as e:
                print(f"⚠️ Nightly scheduler error: {e}")
            time.sleep(50)

    threading.Thread(target=_loop, daemon=True).start()


if __name__ == "__main__":
    start_nightly_scheduler()
    print(f"🚀 RWA Course Vault Backend running on port {config.PORT} (DBs={len(course_vault_db.dbs)})")
    serve(app, host="0.0.0.0", port=config.PORT, threads=config.WAITRESS_THREADS, connection_limit=500, channel_timeout=60)

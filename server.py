import io
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


def _get_tg_bot_token_and_chats():
    settings = course_vault_db.get_all_settings()
    tg_core = settings.get("telegram_core", {})

    # Chat IDs: Admin Panel first, fallback to config.ADMIN_IDS
    chats = []
    raw_chats = str(tg_core.get("admin_chat_ids") or "").replace("\n", ",")
    for part in raw_chats.split(","):
        p = part.strip()
        if p and p not in chats:
            chats.append(p)
    for aid in (config.ADMIN_IDS or []):
        s = str(aid).strip()
        if s and s not in chats:
            chats.append(s)

    # Bot Token: Active Admin Panel TG Bots first, fallback to config.BOT_TOKEN
    bot_token = ""
    bots = course_vault_db.get_tg_bots(include_inactive=False)
    for b in bots:
        if b.get("token"):
            bot_token = str(b["token"]).strip()
            break
    if not bot_token:
        bot_token = str(config.BOT_TOKEN or "").strip()

    return bot_token, chats


def send_tg_alert(text):
    bot_token, chats = _get_tg_bot_token_and_chats()
    if not bot_token or not chats:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    sent_any = False
    for cid in chats:
        try:
            r = requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=12)
            if r.ok:
                sent_any = True
        except Exception:
            pass
    return sent_any


def send_json_backup_to_telegram(reason="Scheduled Backup"):
    bot_token, chats = _get_tg_bot_token_and_chats()
    if not bot_token or not chats:
        return False, "Admin Panel mein kam se kam 1 Active TG Bot aur Admin Chat ID set karein."
    try:
        backup = course_vault_db.export_full_json_backup()
        raw_bytes = json.dumps(backup, ensure_ascii=False, indent=2).encode("utf-8")
        fname = f"RWA_Vault_Backup_{datetime.now(IST).strftime('%Y%m%d_%H%M')}.json"
        caption = (
            f"💾 <b>RWA Course Vault — MongoDB JSON Backup</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Reason   : {reason}\n"
            f"🎓 Courses  : {len(backup.get('courses', []))}\n"
            f"📚 Subjects : {len(backup.get('subjects', []))}\n"
            f"🎬 Classes  : {len(backup.get('lectures', []))}\n"
            f"🤖 TG Bots  : {len(backup.get('tg_bots', []))}\n"
            f"🕒 Time     : {backup.get('exported_at', '')}"
        )
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        sent = 0
        for cid in chats:
            try:
                files = {"document": (fname, io.BytesIO(raw_bytes), "application/json")}
                data = {"chat_id": cid, "caption": caption, "parse_mode": "HTML"}
                r = requests.post(url, data=data, files=files, timeout=30)
                if r.ok:
                    sent += 1
            except Exception:
                pass
        if sent > 0:
            rr = course_vault_db.get_all_settings().get("retry_and_reports", {})
            rr["last_backup_ts"] = int(time.time())
            rr["uploads_since_backup"] = 0
            course_vault_db.update_settings({"retry_and_reports": rr})
            return True, f"Backup sent to {sent} Admin chat(s)!"
        return False, "Telegram API par backup send fail hua (Bot Token / Chat ID check karein)."
    except Exception as e:
        return False, f"Backup error: {str(e)[:120]}"


def send_daily_report_to_telegram(title="Daily Course Vault Report"):
    s = course_vault_db.get_direct_summary()
    yt = s.get("yt_stats", {})
    tg = s.get("tg_stats", {})
    w = s.get("worker", {})
    msg = (
        f"📊 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎓 Batches      : <b>{s.get('total_courses', 0)}</b>\n"
        f"🎬 Total Classes: <b>{s.get('total_lectures', 0)}</b>\n\n"
        f"▶️ <b>YouTube Backup ({yt.get('progress_pct', 0)}%)</b>\n"
        f"   ✅ Done: {yt.get('completed', 0)} | ⏳ Pend: {yt.get('pending', 0)} | ❌ Fail: {yt.get('failed', 0)}\n\n"
        f"✈️ <b>Telegram Backup ({tg.get('progress_pct', 0)}%)</b>\n"
        f"   ✅ Done: {tg.get('completed', 0)} | ⏳ Pend: {tg.get('pending', 0)} | ❌ Fail: {tg.get('failed', 0)}\n\n"
        f"📄 Drive PDFs   : <b>{s.get('pdf_ready', 0)}</b> | TG PDFs: <b>{s.get('tg_pdf_ready', 0)}</b>\n"
        f"📱 Worker       : <b>{'🟢 ONLINE' if w.get('online') else '⚪ OFFLINE'}</b>\n"
        f"🤖 Active Bots  : <b>{s.get('tg_bots_active', 0)}/{s.get('tg_bots_total', 0)}</b>\n"
        f"🕒 Time (IST)   : {s.get('updated_at', '')}"
    )
    ok = send_tg_alert(msg)
    return ok, ("Daily report sent to Telegram!" if ok else "Telegram alert fail (Bot Token / Admin Chat ID check karein).")


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


# =========================================================
# HEALTH & PORTAL PUBLIC ENDPOINTS (OLD FEATURES 100% INTACT)
# =========================================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "RWA Course Vault Backend (YT + TG Double Backup)",
        "course_dbs": len(course_vault_db.dbs),
        "scanner_running": course_scanner.get_status().get("running", False),
        "termux_worker_online": course_vault_db.get_worker_heartbeat().get("online", False)
    }), 200


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


@app.route("/api/cv/course_index/<course_id>", methods=["GET"])
def api_cv_course_index(course_id):
    return jsonify({"status": "success", "lectures": course_vault_db.get_course_index_lectures(course_id)})


# =========================================================
# TERMUX WORKER ENDPOINTS (LIGHTWEIGHT JSON ONLY — 0 MB MEDIA)
# =========================================================
@app.route("/api/worker/config", methods=["GET"])
@require_admin
def api_worker_config():
    return jsonify({
        "status": "success",
        "settings": course_vault_db.get_all_settings(),
        "tg_bots": course_vault_db.get_tg_bots(include_inactive=False)
    }), 200


@app.route("/api/worker/heartbeat", methods=["POST"])
def api_worker_heartbeat():
    data = request.get_json(silent=True) or {}
    course_vault_db.update_worker_heartbeat(data)
    settings = course_vault_db.get_all_settings()
    return jsonify({
        "status": "success",
        "worker_control": settings.get("worker_control", {}),
        "size_guard": settings.get("size_guard", {})
    }), 200


@app.route("/api/worker/next_lecture", methods=["GET"])
def api_worker_next_lecture():
    doc = course_vault_db.claim_next_lecture_one_by_one()
    if not doc:
        return jsonify({"status": "success", "lecture": None}), 200

    fresh = course_scanner.fetch_fresh_links_for_lecture(doc.get("course_id", ""), doc.get("lecture_id", ""))
    doc["source_video_url"] = fresh.get("source_video_url", "")
    doc["source_pdf1_url"] = fresh.get("source_pdf1_url", "")
    doc["source_pdf2_url"] = fresh.get("source_pdf2_url", "")
    return jsonify({"status": "success", "lecture": doc}), 200


@app.route("/api/worker/report_lecture", methods=["POST"])
def api_worker_report_lecture():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.finish_lecture_item(
        lecture_id=data.get("lecture_id", ""),
        ok=bool(data.get("ok", False)),
        yt_video_id=data.get("yt_video_id", ""),
        drive_pdf1_id=data.get("drive_pdf1_id", ""),
        drive_pdf2_id=data.get("drive_pdf2_id", ""),
        drive_thumb_id=data.get("drive_thumb_id", ""),
        error_message=data.get("error_message", ""),
        yt_status=data.get("yt_status", ""),
        tg_status=data.get("tg_status", ""),
        tg_channel_id=data.get("tg_channel_id", ""),
        tg_topic_id=data.get("tg_topic_id", ""),
        tg_video_msg_id=data.get("tg_video_msg_id", ""),
        tg_pdf1_msg_id=data.get("tg_pdf1_msg_id", ""),
        tg_pdf2_msg_id=data.get("tg_pdf2_msg_id", ""),
        tg_master_video_msg_id=data.get("tg_master_video_msg_id", ""),
        tg_master_pdf1_msg_id=data.get("tg_master_pdf1_msg_id", ""),
        tg_master_pdf2_msg_id=data.get("tg_master_pdf2_msg_id", ""),
        yt_error=data.get("yt_error"),
        tg_error=data.get("tg_error"),
        skipped=bool(data.get("skipped", False))
    )
    return jsonify({"status": "success" if ok else "error"}), 200


@app.route("/api/worker/bot_status", methods=["POST"])
def api_worker_bot_status():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.record_bot_status(
        bot_id=data.get("bot_id", ""),
        flood_until_ts=data.get("flood_until_ts", 0),
        last_error=data.get("last_error", ""),
        inc_upload=bool(data.get("inc_upload", False))
    )
    return jsonify({"status": "success" if ok else "error"}), 200


@app.route("/api/worker/course_index_msg", methods=["POST"])
def api_worker_course_index_msg():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.update_course_settings(
        course_id=data.get("course_id", ""),
        tg_index_msg_id=data.get("tg_index_msg_id", "")
    )
    return jsonify({"status": "success" if ok else "error"}), 200


@app.route("/api/worker/next_restore_job", methods=["GET"])
def api_worker_next_restore_job():
    job = course_vault_db.claim_next_restore_job()
    return jsonify({"status": "success", "job": job}), 200


@app.route("/api/worker/report_restore_job", methods=["POST"])
def api_worker_report_restore_job():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.update_restore_job(
        job_id=data.get("job_id", ""),
        status=data.get("status", "completed"),
        done_count=data.get("done_count", 0),
        total_count=data.get("total_count", 0),
        error=data.get("error", "")
    )
    return jsonify({"status": "success" if ok else "error"}), 200


@app.route("/api/worker/notify", methods=["POST"])
def api_worker_notify():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if text:
        send_tg_alert(text)
    return jsonify({"status": "success"}), 200


# =========================================================
# ADMIN AUTH, SUMMARY & EXISTING CONTROLS
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


@app.route("/api/admin/token/verify", methods=["POST"])
@require_admin
def api_admin_token_verify():
    data = request.get_json(silent=True) or {}
    raw_token = clean_jwt_token(data.get("token", ""))
    label = str(data.get("label") or "").strip()
    if not raw_token:
        return jsonify({"status": "error", "message": "Token paste karein."}), 400

    res = course_scanner.verify_token_and_fetch_courses(raw_token)
    if not res.get("ok"):
        return jsonify({"status": "error", "message": res.get("message", "Token invalid!")}), 400

    uid = res["user_id"]
    final_label = label or res.get("user_name") or f"User #{uid}"
    course_vault_db.upsert_scanner_token(uid, raw_token, final_label)
    return jsonify({
        "status": "success",
        "user_id": uid,
        "user_name": final_label,
        "courses": res.get("courses", []),
        "message": res.get("message", "Token Verified!")
    })


@app.route("/api/admin/course/delete", methods=["POST", "DELETE"])
@require_admin
def api_admin_course_delete():
    data = request.get_json(silent=True) or {}
    cid = str(data.get("course_id") or request.args.get("course_id") or "").strip()
    ok = course_vault_db.delete_course(cid)
    return jsonify({"status": "success" if ok else "error", "deleted_course_id": cid})


@app.route("/api/admin/recheck", methods=["POST"])
@require_admin
def api_admin_recheck():
    data = request.get_json(silent=True) or {}
    cnt = course_vault_db.recheck_scope(
        course_id=data.get("course_id", ""),
        subject_id=data.get("subject_id", ""),
        topic_id=data.get("topic_id", ""),
        lecture_id=data.get("lecture_id", ""),
        force_all=bool(data.get("force_all", False)),
        target=str(data.get("target") or "both")
    )
    return jsonify({"status": "success", "requeued_count": cnt})


@app.route("/api/admin/queue/clear", methods=["POST"])
@require_admin
def api_admin_queue_clear():
    data = request.get_json(silent=True) or {}
    cid = str(data.get("course_id") or "").strip()
    deleted = course_vault_db.clear_pending_queue(cid)
    return jsonify({"status": "success", "deleted_count": deleted})


@app.route("/api/admin/scan/start", methods=["POST"])
@require_admin
def api_admin_scan_start():
    data = request.get_json(silent=True) or {}
    course_id = str(data.get("course_id") or "").strip()
    raw_token = clean_jwt_token(data.get("token", ""))
    user_id = str(data.get("user_id") or "").strip()
    override = {"token": raw_token, "user_id": user_id or extract_uid_from_jwt(raw_token)} if raw_token else None

    ok, msg = course_scanner.start_scan(mode="manual", target_course_id=course_id, override_token=override)
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
        raw_tok = clean_jwt_token(data.get("token", ""))
        uid = str(data.get("user_id") or "").strip() or extract_uid_from_jwt(raw_tok)
        ok = course_vault_db.upsert_scanner_token(uid, raw_tok, data.get("label", "Scanner"))
        return jsonify({"status": "success" if ok else "error", "user_id": uid})
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
        drive_thumb_id=data.get("drive_thumb_id", ""),
        tg_video_msg_id=data.get("tg_video_msg_id", ""),
        tg_pdf1_msg_id=data.get("tg_pdf1_msg_id", ""),
        tg_pdf2_msg_id=data.get("tg_pdf2_msg_id", "")
    )
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/queue/retry_failed", methods=["POST"])
@require_admin
def api_admin_retry_failed():
    data = request.get_json(silent=True) or {}
    cnt = course_vault_db.reset_failed_lectures_to_pending(
        lecture_id=data.get("lecture_id", ""),
        target=str(data.get("target") or "both")
    )
    return jsonify({"status": "success", "reset_count": cnt})


@app.route("/api/admin/cache/flush", methods=["POST"])
@require_admin
def api_admin_flush():
    cleared = ram_cache.clear_all()
    return jsonify({"status": "success", "cleared": cleared})


# =========================================================
# NEW A-TO-Z ADMIN PANEL CONTROL ENDPOINTS
# =========================================================
@app.route("/api/admin/settings", methods=["GET", "POST"])
@require_admin
def api_admin_settings():
    if request.method == "GET":
        return jsonify({"status": "success", "settings": course_vault_db.get_all_settings()})
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.update_settings(data)
    return jsonify({
        "status": "success" if ok else "error",
        "settings": course_vault_db.get_all_settings()
    })


@app.route("/api/admin/settings/reset", methods=["POST"])
@require_admin
def api_admin_settings_reset():
    data = request.get_json(silent=True) or {}
    sec = str(data.get("section") or "").strip()
    ok = course_vault_db.reset_settings_section(sec)
    return jsonify({
        "status": "success" if ok else "error",
        "settings": course_vault_db.get_all_settings()
    })


@app.route("/api/admin/worker/control", methods=["POST"])
@require_admin
def api_admin_worker_control():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.set_worker_control(
        state=data.get("state"),
        skip_lecture_id=data.get("skip_lecture_id"),
        download_threads=data.get("download_threads")
    )
    return jsonify({
        "status": "success" if ok else "error",
        "worker_control": course_vault_db.get_all_settings().get("worker_control", {})
    })


@app.route("/api/admin/tg_bots", methods=["GET", "POST", "DELETE"])
@require_admin
def api_admin_tg_bots():
    if request.method == "GET":
        return jsonify({"status": "success", "bots": course_vault_db.get_tg_bots(include_inactive=True)})
    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        bid = course_vault_db.upsert_tg_bot(
            bot_id=data.get("bot_id", ""),
            label=data.get("label", "TG Bot"),
            token=data.get("token", ""),
            active=bool(data.get("active", True)),
            order=int(data.get("order") or 0)
        )
        return jsonify({"status": "success" if bid else "error", "bot_id": bid, "bots": course_vault_db.get_tg_bots(True)})
    ok = course_vault_db.delete_tg_bot(data.get("bot_id", ""))
    return jsonify({"status": "success" if ok else "error", "bots": course_vault_db.get_tg_bots(True)})


@app.route("/api/admin/tg_bots/toggle", methods=["POST"])
@require_admin
def api_admin_tg_bots_toggle():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.toggle_tg_bot(data.get("bot_id", ""), bool(data.get("active", True)))
    return jsonify({"status": "success" if ok else "error", "bots": course_vault_db.get_tg_bots(True)})


@app.route("/api/admin/course/settings", methods=["POST"])
@require_admin
def api_admin_course_settings():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.update_course_settings(
        course_id=data.get("course_id", ""),
        tg_channel_id=data.get("tg_channel_id"),
        tg_channel_link=data.get("tg_channel_link"),
        upload_mode=data.get("upload_mode"),
        priority=data.get("priority"),
        tg_index_msg_id=data.get("tg_index_msg_id"),
        playback_mode=data.get("playback_mode")
    )
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/subject/settings", methods=["POST"])
@require_admin
def api_admin_subject_settings():
    data = request.get_json(silent=True) or {}
    ok = course_vault_db.update_subject_settings(
        course_id=data.get("course_id", ""),
        subject_id=data.get("subject_id", ""),
        tg_channel_id=data.get("tg_channel_id"),
        tg_topic_id=data.get("tg_topic_id")
    )
    return jsonify({"status": "success" if ok else "error"})


@app.route("/api/admin/restore_jobs", methods=["GET"])
@require_admin
def api_admin_restore_jobs():
    return jsonify({"status": "success", "jobs": course_vault_db.get_restore_jobs()})


@app.route("/api/admin/restore_jobs/create", methods=["POST"])
@require_admin
def api_admin_restore_jobs_create():
    data = request.get_json(silent=True) or {}
    job = course_vault_db.create_restore_job(
        course_id=data.get("course_id", ""),
        target_channel_id=data.get("target_channel_id", ""),
        subject_id=data.get("subject_id", ""),
        target_topic_id=data.get("target_topic_id", "")
    )
    if not job:
        return jsonify({"status": "error", "message": "Course ID aur Target Channel ID dalein."}), 400
    return jsonify({"status": "success", "job": job})


@app.route("/api/admin/backup/export", methods=["GET"])
@require_admin
def api_admin_backup_export():
    backup = course_vault_db.export_full_json_backup()
    resp = make_response(json.dumps(backup, ensure_ascii=False, indent=2))
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="RWA_Vault_Backup_{datetime.now(IST).strftime("%Y%m%d_%H%M")}.json"'
    return resp


@app.route("/api/admin/backup/import", methods=["POST"])
@require_admin
def api_admin_backup_import():
    data = request.get_json(silent=True) or {}
    res = course_vault_db.import_full_json_backup(data)
    return jsonify({"status": "success" if res.get("ok") else "error", **res})


@app.route("/api/admin/backup/send_tg", methods=["POST"])
@require_admin
def api_admin_backup_send_tg():
    ok, msg = send_json_backup_to_telegram(reason="Manual Admin Trigger")
    return jsonify({"status": "success" if ok else "error", "message": msg})


@app.route("/api/admin/report/send_now", methods=["POST"])
@require_admin
def api_admin_report_send_now():
    ok, msg = send_daily_report_to_telegram(title="Manual Course Vault Summary Report")
    return jsonify({"status": "success" if ok else "error", "message": msg})


# =========================================================
# BACKGROUND SCHEDULERS (NIGHTLY SCAN + DAILY REPORT + AUTO JSON BACKUP)
# =========================================================
def start_background_schedulers():
    last_scan_date = None

    def _loop():
        nonlocal last_scan_date
        while True:
            try:
                now = datetime.now(IST)
                today = now.strftime("%Y-%m-%d")

                # 1. Nightly Course Scanner
                if now.hour == config.NIGHTLY_SCAN_HOUR_IST and last_scan_date != today:
                    last_scan_date = today
                    ok, msg = course_scanner.start_scan(mode="nightly")
                    print(f"🕚 [Nightly Course Scanner] {today}: ok={ok} | {msg}")

                # 2. Daily Telegram Report & Auto JSON Backup
                settings = course_vault_db.get_all_settings()
                rr = settings.get("retry_and_reports", {})

                if rr.get("daily_report_enabled", True):
                    rep_hr = int(rr.get("daily_report_hour_ist", 22))
                    if now.hour == rep_hr and rr.get("last_daily_report_date") != today:
                        ok, _ = send_daily_report_to_telegram()
                        if ok:
                            rr["last_daily_report_date"] = today
                            course_vault_db.update_settings({"retry_and_reports": rr})

                if rr.get("auto_json_backup_enabled", True):
                    every_n = max(1, int(rr.get("backup_every_uploads", 50)))
                    interval_sec = max(1, int(rr.get("backup_interval_hours", 24))) * 3600
                    uploads_since = int(rr.get("uploads_since_backup", 0))
                    last_bk = int(rr.get("last_backup_ts", 0))
                    now_ts = int(time.time())

                    if uploads_since >= every_n:
                        send_json_backup_to_telegram(reason=f"Auto Backup ({uploads_since} new uploads)")
                    elif last_bk > 0 and (now_ts - last_bk) >= interval_sec:
                        send_json_backup_to_telegram(reason=f"Auto Backup ({rr.get('backup_interval_hours', 24)}h schedule)")
            except Exception as e:
                print(f"⚠️ Background scheduler error: {e}")
            time.sleep(55)

    threading.Thread(target=_loop, daemon=True).start()


if __name__ == "__main__":
    start_background_schedulers()
    print(f"🚀 RWA Course Vault Backend (YT + TG Double Backup) running on port {config.PORT} (DBs={len(course_vault_db.dbs)})")
    serve(app, host="0.0.0.0", port=config.PORT, threads=config.WAITRESS_THREADS, connection_limit=500, channel_timeout=60)

import copy
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING
import config

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist_str():
    return datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")


def _clean_doc(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d


def drive_image_url(file_id):
    fid = str(file_id or "").strip()
    if not fid:
        return ""
    return f"https://lh3.googleusercontent.com/d/{fid}=w1000"


def build_tg_msg_link(channel_id, msg_id, channel_link=""):
    mid = str(msg_id or "").strip()
    if not mid:
        return ""
    cl = str(channel_link or "").strip().rstrip("/")
    if cl.startswith("https://t.me/") and "/+" not in cl and "joinchat" not in cl:
        return f"{cl}/{mid}"
    cid = str(channel_id or "").strip()
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{mid}"
    return cl


DEFAULT_SETTINGS = {
    "telegram_core": {
        "enabled": True,
        "api_id": "",
        "api_hash": "",
        "master_backup_channel_id": "",
        "admin_chat_ids": "",
        "global_upload_mode": "both",
        "auto_forward_master": True,
        "auto_pinned_index": True,
        "sequential_indexing": True
    },
    "captions": {
        "branding_tag": "RWB",
        "channel_link": "",
        "video_template": (
            "🎬 {course_name}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔢 Index   : #{seq_code}\n"
            "📚 Subject : {subject_name}\n"
            "📂 Topic   : {topic_name}\n"
            "📝 Class   : {title}\n"
            "🆔 Class ID: #{lecture_id}\n"
            "📅 Date    : {date_and_time}\n"
            "🏷️ Backup  : {branding_tag}"
        ),
        "pdf_template": (
            "📄 [PDF {pdf_num}] #{seq_code} {title}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎓 Batch   : {course_name}\n"
            "📚 Subject : {subject_name}\n"
            "📂 Topic   : {topic_name}\n"
            "🆔 Class ID: #{lecture_id}\n"
            "🏷️ Backup  : {branding_tag}"
        )
    },
    "inline_buttons": {
        "enabled": False,
        "buttons": [
            {"text": "🌐 Open Portal", "url": ""},
            {"text": "📢 Join Main Channel", "url": ""}
        ]
    },
    "watermark": {
        "enabled": False,
        "text": "RWB",
        "sub_text": "",
        "opacity": 0.18,
        "color": "#64748b"
    },
    "size_guard": {
        "enabled": True,
        "max_mb": 1950,
        "mode": "split"
    },
    "worker_control": {
        "state": "RUNNING",
        "skip_lecture_id": "",
        "download_threads": 12,
        "storage_guard_enabled": True,
        "min_free_gb": 2.0,
        "battery_guard_enabled": True,
        "min_battery_pct": 15
    },
    "retry_and_reports": {
        "auto_retry_enabled": True,
        "max_retries": 3,
        "retry_cooldown_mins": 10,
        "daily_report_enabled": True,
        "daily_report_hour_ist": 22,
        "last_daily_report_date": "",
        "auto_json_backup_enabled": True,
        "backup_every_uploads": 50,
        "backup_interval_hours": 24,
        "last_backup_ts": 0,
        "uploads_since_backup": 0
    },
    "portal_fallback": {
        "tg_fallback_enabled": True,
        "default_tg_invite_link": ""
    }
}


def _deep_merge_defaults(stored):
    res = copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(stored, dict):
        return res
    for sec, sec_defaults in DEFAULT_SETTINGS.items():
        val = stored.get(sec)
        if isinstance(val, dict):
            for k, v in val.items():
                res[sec][k] = v
    return res


class RamTTLCache:
    def __init__(self, max_items=1000):
        self._store = {}
        self._lock = threading.RLock()
        self._max_items = max_items
        self.hits = 0
        self.misses = 0

    def get(self, key):
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None
            exp, val = entry
            if now > exp:
                self._store.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return val

    def set(self, key, val, ttl_sec=60):
        now = time.time()
        with self._lock:
            if len(self._store) >= self._max_items:
                for k in [k for k, (e, _) in self._store.items() if now > e]:
                    self._store.pop(k, None)
                if len(self._store) >= self._max_items:
                    oldest = min(self._store.items(), key=lambda x: x[1][0])[0]
                    self._store.pop(oldest, None)
            self._store[key] = (now + ttl_sec, val)

    def invalidate_prefix(self, prefix):
        with self._lock:
            for k in list(self._store.keys()):
                if str(k).startswith(prefix):
                    self._store.pop(k, None)

    def clear_all(self):
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n

    def stats(self):
        with self._lock:
            return {"keys": len(self._store), "hits": self.hits, "misses": self.misses}


ram_cache = RamTTLCache()


class CourseVaultDB:
    def __init__(self):
        self.dbs = []
        self.connection_errors = []
        self._connect_all()

    def _connect_all(self):
        self.connection_errors = []
        for idx, uri in enumerate(config.COURSE_MONGO_URIS, start=1):
            try:
                client = MongoClient(
                    uri,
                    maxPoolSize=50,
                    minPoolSize=2,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=15000,
                    retryWrites=True,
                    tls=True,
                    tlsAllowInvalidCertificates=True
                )
                client.admin.command("ping")
                db = client[config.COURSE_DB_NAME]
                self._ensure_indexes(db)
                self.dbs.append({
                    "index": idx,
                    "label": f"COURSE-DB-{idx}",
                    "client": client,
                    "db": db
                })
                print(f"✅ Connected to Course Vault MongoDB COURSE-DB-{idx}")
            except Exception as e:
                err = f"COURSE-DB-{idx}: {e}"
                self.connection_errors.append(err)
                print(f"❌ Failed connecting {err}")

    def _ensure_indexes(self, db):
        try:
            db.courses.create_index("course_id", unique=True)
            db.subjects.create_index([("course_id", 1), ("subject_id", 1)], unique=True)
            db.topics.create_index([("course_id", 1), ("subject_id", 1), ("topic_id", 1)], unique=True)
            db.lectures.create_index("lecture_id", unique=True)
            db.lectures.create_index([("course_id", 1), ("subject_id", 1), ("topic_id", 1)])
            db.lectures.create_index("status")
            db.lectures.create_index("yt_status")
            db.lectures.create_index("tg_status")
            db.scanner_tokens.create_index("user_id", unique=True)
            db.tg_bots.create_index("bot_id", unique=True)
            db.restore_jobs.create_index("job_id", unique=True)
        except Exception:
            pass

    def get_primary_db(self):
        return self.dbs[0] if self.dbs else None

    def get_db_size_mb(self, entry):
        try:
            st = entry["db"].command("dbStats")
            return round((st.get("dataSize", 0) + st.get("indexSize", 0)) / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def pick_best_shard(self):
        for entry in self.dbs:
            if self.get_db_size_mb(entry) < config.MAX_COURSE_DB_SIZE_MB:
                return entry
        return None

    def has_available_storage(self):
        return self.pick_best_shard() is not None

    def _find_lecture_shard(self, lecture_id):
        lid = str(lecture_id).strip()
        for entry in self.dbs:
            try:
                if entry["db"].lectures.find_one({"lecture_id": lid}, {"_id": 1}):
                    return entry
            except Exception:
                continue
        return None

    # =========================================================
    # MASTER SETTINGS (A-TO-Z ADMIN PANEL CONTROL)
    # =========================================================
    def get_all_settings(self):
        cached = ram_cache.get("cv_settings:master")
        if cached is not None:
            return copy.deepcopy(cached)
        primary = self.get_primary_db()
        stored = None
        if primary:
            try:
                stored = primary["db"].vault_settings.find_one({"_id": "master_config"})
            except Exception:
                pass
        merged = _deep_merge_defaults(stored)
        ram_cache.set("cv_settings:master", merged, ttl_sec=15)
        return copy.deepcopy(merged)

    def update_settings(self, patch):
        primary = self.get_primary_db()
        if not primary or not isinstance(patch, dict):
            return False
        current = self.get_all_settings()
        for sec, val in patch.items():
            if sec in DEFAULT_SETTINGS and isinstance(val, dict):
                current[sec].update(val)
        current["updated_at"] = now_ist_str()
        primary["db"].vault_settings.update_one(
            {"_id": "master_config"},
            {"$set": current},
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_settings")
        ram_cache.invalidate_prefix("cv_summary")
        return True

    def reset_settings_section(self, section_name):
        primary = self.get_primary_db()
        if not primary or section_name not in DEFAULT_SETTINGS:
            return False
        default_sec = copy.deepcopy(DEFAULT_SETTINGS[section_name])
        primary["db"].vault_settings.update_one(
            {"_id": "master_config"},
            {"$set": {section_name: default_sec, "updated_at": now_ist_str()}},
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_settings")
        return True

    def set_worker_control(self, state=None, skip_lecture_id=None, download_threads=None):
        wc = self.get_all_settings().get("worker_control", {})
        if state in ("RUNNING", "PAUSED"):
            wc["state"] = state
        if skip_lecture_id is not None:
            wc["skip_lecture_id"] = str(skip_lecture_id).strip()
        if download_threads is not None:
            try:
                t = int(download_threads)
                wc["download_threads"] = max(1, min(24, t))
            except Exception:
                pass
        return self.update_settings({"worker_control": wc})

    # =========================================================
    # MULTI-BOT MANAGER (TELEGRAM ANTI-FLOOD ROTATION)
    # =========================================================
    def get_tg_bots(self, include_inactive=True):
        primary = self.get_primary_db()
        if not primary:
            return []
        q = {} if include_inactive else {"active": {"$ne": False}}
        try:
            docs = [_clean_doc(d) for d in primary["db"].tg_bots.find(q).sort("order", 1)]
            return docs
        except Exception:
            return []

    def upsert_tg_bot(self, bot_id="", label="TG Bot", token="", active=True, order=0):
        primary = self.get_primary_db()
        tok = str(token or "").strip()
        if not primary or not tok:
            return False
        bid = str(bot_id or "").strip() or f"bot_{int(time.time())}_{uuid.uuid4().hex[:5]}"
        now_str = now_ist_str()
        primary["db"].tg_bots.update_one(
            {"bot_id": bid},
            {
                "$set": {
                    "bot_id": bid,
                    "label": str(label or "TG Bot").strip(),
                    "token": tok,
                    "active": bool(active),
                    "order": int(order or 0),
                    "updated_at": now_str
                },
                "$setOnInsert": {
                    "flood_until_ts": 0,
                    "last_error": "",
                    "uploads_count": 0,
                    "created_at": now_str
                }
            },
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_summary")
        return bid

    def toggle_tg_bot(self, bot_id, active):
        primary = self.get_primary_db()
        if not primary or not bot_id:
            return False
        res = primary["db"].tg_bots.update_one(
            {"bot_id": str(bot_id).strip()},
            {"$set": {"active": bool(active), "updated_at": now_ist_str()}}
        )
        ram_cache.invalidate_prefix("cv_summary")
        return res.matched_count > 0

    def delete_tg_bot(self, bot_id):
        primary = self.get_primary_db()
        if not primary or not bot_id:
            return False
        res = primary["db"].tg_bots.delete_one({"bot_id": str(bot_id).strip()})
        ram_cache.invalidate_prefix("cv_summary")
        return res.deleted_count > 0

    def record_bot_status(self, bot_id, flood_until_ts=0, last_error="", inc_upload=False):
        primary = self.get_primary_db()
        if not primary or not bot_id:
            return False
        upd = {
            "$set": {
                "flood_until_ts": int(flood_until_ts or 0),
                "last_error": str(last_error or "")[:160],
                "updated_at": now_ist_str()
            }
        }
        if inc_upload:
            upd["$inc"] = {"uploads_count": 1}
        primary["db"].tg_bots.update_one({"bot_id": str(bot_id).strip()}, upd)
        return True

    # =========================================================
    # SCANNER TOKENS
    # =========================================================
    def get_scanner_tokens(self):
        tokens = []
        seen = set()

        if config.SCANNER_TOKENS_RAW:
            for part in config.SCANNER_TOKENS_RAW.replace("\n", ",").split(","):
                p = part.strip()
                if ":" in p:
                    uid, tok = p.split(":", 1)
                    uid, tok = uid.strip(), tok.strip()
                    if tok and tok not in seen:
                        seen.add(tok)
                        tokens.append({"user_id": uid, "token": tok, "source": "env"})

        primary = self.get_primary_db()
        if primary:
            try:
                for d in primary["db"].scanner_tokens.find({"active": {"$ne": False}}):
                    tok = str(d.get("token") or "").strip()
                    if tok and tok not in seen:
                        seen.add(tok)
                        tokens.append({
                            "user_id": str(d.get("user_id") or ""),
                            "label": d.get("label") or "Scanner Account",
                            "token": tok,
                            "source": "db",
                            "added_at": d.get("added_at", "")
                        })
            except Exception:
                pass
        return tokens

    def upsert_scanner_token(self, user_id, token, label="Scanner Account"):
        primary = self.get_primary_db()
        uid = str(user_id or "").strip()
        tok = str(token or "").strip()
        if not primary or not uid or not tok:
            return False
        primary["db"].scanner_tokens.update_one(
            {"user_id": uid},
            {"$set": {
                "user_id": uid,
                "token": tok,
                "label": str(label or "Scanner Account"),
                "active": True,
                "added_at": now_ist_str(),
                "ts": int(time.time())
            }},
            upsert=True
        )
        return True

    def delete_scanner_token(self, user_id):
        primary = self.get_primary_db()
        if not primary:
            return False
        return primary["db"].scanner_tokens.delete_one({"user_id": str(user_id).strip()}).deleted_count > 0

    # =========================================================
    # SEQUENTIAL AUTO-INDEXING (001, 002, 003...)
    # =========================================================
    def get_next_seq_index(self, course_id):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        if not primary or not cid:
            return 1
        try:
            doc = primary["db"].counters.find_one_and_update(
                {"_id": f"seq_course_{cid}"},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=True
            )
            return int(doc.get("seq", 1))
        except Exception:
            return 1

    # =========================================================
    # COURSES (WITH TG CHANNEL, MODE, PRIORITY & PER-COURSE STATS)
    # =========================================================
    def upsert_course(self, course_obj):
        primary = self.get_primary_db()
        cid = str(course_obj.get("id") or course_obj.get("course_id") or "").strip()
        if not primary or not cid:
            return False
        raw_logo = str(course_obj.get("exam_logo") or course_obj.get("course_thumbnail") or "").replace("\\/", "/").strip()
        now_str = now_ist_str()
        now_ts = int(time.time())

        set_doc = {
            "course_id": cid,
            "id": cid,
            "course_name": str(course_obj.get("course_name") or f"Batch #{cid}").strip(),
            "exam_category": str(course_obj.get("exam_category") or "RWA PAID BATCH"),
            "source_logo": raw_logo,
            "test_series_id": str(course_obj.get("test_series_id") or ""),
            "updated_at": now_str,
            "ts": now_ts
        }
        on_insert = {
            "drive_thumb_id": "",
            "drive_thumb_url": "",
            "thumb_status": "pending" if raw_logo.startswith("http") else "none",
            "playback_mode": "vault_first",
            "upload_mode": "both",
            "priority": "normal",
            "tg_channel_id": "",
            "tg_channel_link": "",
            "tg_index_msg_id": "",
            "first_saved_at": now_str
        }
        for k in list(set_doc.keys()):
            on_insert.pop(k, None)

        primary["db"].courses.update_one(
            {"course_id": cid},
            {"$set": set_doc, "$setOnInsert": on_insert},
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_courses")
        ram_cache.invalidate_prefix("cv_summary")
        return True

    def update_course_settings(
        self, course_id, tg_channel_id=None, tg_channel_link=None,
        upload_mode=None, priority=None, tg_index_msg_id=None, playback_mode=None
    ):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        if not primary or not cid:
            return False
        upd = {"updated_at": now_ist_str()}
        if tg_channel_id is not None:
            upd["tg_channel_id"] = str(tg_channel_id).strip()
        if tg_channel_link is not None:
            upd["tg_channel_link"] = str(tg_channel_link).strip()
        if upload_mode in ("both", "only_tg", "only_yt"):
            upd["upload_mode"] = upload_mode
        if priority in ("high", "normal"):
            upd["priority"] = priority
        if tg_index_msg_id is not None:
            upd["tg_index_msg_id"] = str(tg_index_msg_id).strip()
        if playback_mode in ("vault_first", "hls_live"):
            upd["playback_mode"] = playback_mode

        res = primary["db"].courses.update_one({"course_id": cid}, {"$set": upd})
        ram_cache.invalidate_prefix("cv_courses")
        ram_cache.invalidate_prefix("cv_summary")
        return res.matched_count > 0

    def delete_course(self, course_id):
        cid = str(course_id or "").strip()
        if not cid:
            return False
        primary = self.get_primary_db()
        if primary:
            try:
                primary["db"].courses.delete_many({"course_id": cid})
                primary["db"].subjects.delete_many({"course_id": cid})
                primary["db"].topics.delete_many({"course_id": cid})
            except Exception:
                pass
        for entry in self.dbs:
            try:
                entry["db"].lectures.delete_many({"course_id": cid})
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return True

    def clear_pending_queue(self, course_id=""):
        deleted = 0
        q = {"status": {"$in": ["pending", "processing", "failed"]}}
        if course_id:
            q["course_id"] = str(course_id).strip()
        for entry in self.dbs:
            try:
                res = entry["db"].lectures.delete_many(q)
                deleted += res.deleted_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return deleted

    def get_all_courses(self):
        cached = ram_cache.get("cv_courses:all")
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        if not primary:
            return []
        docs = [_clean_doc(d) for d in primary["db"].courses.find().sort("ts", DESCENDING)]

        stats_map = {}
        for entry in self.dbs:
            try:
                proj = {
                    "course_id": 1, "status": 1, "yt_video_id": 1,
                    "yt_status": 1, "tg_status": 1, "tg_video_msg_id": 1,
                    "drive_pdf1_id": 1, "drive_pdf2_id": 1
                }
                for row in entry["db"].lectures.find({}, proj):
                    cid = str(row.get("course_id") or "")
                    st = stats_map.setdefault(cid, {
                        "total": 0, "ready": 0, "pending": 0, "failed": 0,
                        "yt_done": 0, "yt_pending": 0, "yt_failed": 0,
                        "tg_done": 0, "tg_pending": 0, "tg_failed": 0,
                        "pdf_done": 0
                    })
                    st["total"] += 1
                    overall = row.get("status") or "pending"
                    if overall == "completed":
                        st["ready"] += 1
                    elif overall == "failed":
                        st["failed"] += 1
                    else:
                        st["pending"] += 1

                    yt_st = row.get("yt_status") or ("completed" if row.get("yt_video_id") else ("failed" if overall == "failed" else "pending"))
                    if row.get("yt_video_id") or yt_st == "completed":
                        st["yt_done"] += 1
                    elif yt_st == "failed":
                        st["yt_failed"] += 1
                    elif yt_st != "skipped":
                        st["yt_pending"] += 1

                    tg_st = row.get("tg_status") or ("completed" if row.get("tg_video_msg_id") else "pending")
                    if row.get("tg_video_msg_id") or tg_st == "completed":
                        st["tg_done"] += 1
                    elif tg_st == "failed":
                        st["tg_failed"] += 1
                    elif tg_st != "skipped":
                        st["tg_pending"] += 1

                    if row.get("drive_pdf1_id") or row.get("drive_pdf2_id"):
                        st["pdf_done"] += 1
            except Exception:
                continue

        for d in docs:
            cid = d["course_id"]
            st = stats_map.get(cid, {})
            tot = st.get("total", 0)
            yt_d = st.get("yt_done", 0)
            tg_d = st.get("tg_done", 0)
            d["total_lectures"] = tot
            d["yt_ready_lectures"] = yt_d
            d["pending_lectures"] = st.get("pending", 0)
            d["failed_lectures"] = st.get("failed", 0)
            d["completed_lectures"] = st.get("ready", 0)
            d["pdf_ready_lectures"] = st.get("pdf_done", 0)
            d["yt_stats"] = {
                "completed": yt_d,
                "pending": st.get("yt_pending", 0),
                "failed": st.get("yt_failed", 0),
                "progress_pct": int((yt_d / tot) * 100) if tot else 0
            }
            d["tg_stats"] = {
                "completed": tg_d,
                "pending": st.get("tg_pending", 0),
                "failed": st.get("tg_failed", 0),
                "progress_pct": int((tg_d / tot) * 100) if tot else 0
            }
            d["upload_mode"] = d.get("upload_mode") or "both"
            d["priority"] = d.get("priority") or "normal"
            d["tg_channel_id"] = d.get("tg_channel_id") or ""
            d["tg_channel_link"] = d.get("tg_channel_link") or ""
            d["exam_logo"] = d.get("drive_thumb_url") or d.get("source_logo") or ""

        # High priority courses first
        docs.sort(key=lambda x: (0 if x.get("priority") == "high" else 1, -int(x.get("ts", 0))))
        ram_cache.set("cv_courses:all", docs, ttl_sec=30)
        return docs

    def set_course_playback_mode(self, course_id, mode):
        return self.update_course_settings(course_id, playback_mode=mode)

    # =========================================================
    # SUBJECTS (WITH OPTIONAL SUBJECT CHANNEL & FORUM TOPIC ID)
    # =========================================================
    def upsert_subject(self, course_id, sub_obj):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        sid = str(sub_obj.get("subjectid") or sub_obj.get("subject_id") or "").strip()
        if not primary or not cid or not sid:
            return False
        raw_logo = str(sub_obj.get("subject_logo") or "").replace("\\/", "/").strip()
        now_str = now_ist_str()

        set_doc = {
            "course_id": cid,
            "subject_id": sid,
            "subjectid": sid,
            "subject_name": str(sub_obj.get("subject_name") or sub_obj.get("subjectname") or f"Subject #{sid}").strip(),
            "source_logo": raw_logo,
            "updated_at": now_str,
            "ts": int(time.time())
        }
        on_insert = {
            "drive_logo_id": "",
            "drive_logo_url": "",
            "logo_status": "pending" if raw_logo.startswith("http") else "none",
            "tg_channel_id": "",
            "tg_topic_id": "",
            "first_saved_at": now_str
        }
        for k in list(set_doc.keys()):
            on_insert.pop(k, None)

        primary["db"].subjects.update_one(
            {"course_id": cid, "subject_id": sid},
            {"$set": set_doc, "$setOnInsert": on_insert},
            upsert=True
        )
        ram_cache.invalidate_prefix(f"cv_subjects:{cid}")
        return True

    def update_subject_settings(self, course_id, subject_id, tg_channel_id=None, tg_topic_id=None):
        primary = self.get_primary_db()
        cid, sid = str(course_id or "").strip(), str(subject_id or "").strip()
        if not primary or not cid or not sid:
            return False
        upd = {"updated_at": now_ist_str()}
        if tg_channel_id is not None:
            upd["tg_channel_id"] = str(tg_channel_id).strip()
        if tg_topic_id is not None:
            upd["tg_topic_id"] = str(tg_topic_id).strip()
        res = primary["db"].subjects.update_one({"course_id": cid, "subject_id": sid}, {"$set": upd})
        ram_cache.invalidate_prefix(f"cv_subjects:{cid}")
        return res.matched_count > 0

    def get_course_subjects(self, course_id):
        cid = str(course_id or "").strip()
        cached = ram_cache.get(f"cv_subjects:{cid}")
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        if not primary or not cid:
            return []
        docs = [_clean_doc(d) for d in primary["db"].subjects.find({"course_id": cid}).sort("ts", 1)]
        for d in docs:
            d["subject_logo"] = d.get("drive_logo_url") or d.get("source_logo") or ""
            d["tg_channel_id"] = d.get("tg_channel_id") or ""
            d["tg_topic_id"] = d.get("tg_topic_id") or ""
        ram_cache.set(f"cv_subjects:{cid}", docs, ttl_sec=60)
        return docs

    # =========================================================
    # TOPICS
    # =========================================================
    def upsert_topic(self, course_id, subject_id, top_obj):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        sid = str(subject_id or "").strip()
        tid = str(top_obj.get("topicid") or top_obj.get("topic_id") or "").strip()
        if not primary or not cid or not sid or not tid:
            return False
        now_str = now_ist_str()
        set_doc = {
            "course_id": cid,
            "subject_id": sid,
            "topic_id": tid,
            "topicid": tid,
            "topic_name": str(top_obj.get("topic_name") or top_obj.get("topicname") or f"Topic #{tid}").strip(),
            "updated_at": now_str,
            "ts": int(time.time())
        }
        on_insert = {"first_saved_at": now_str}
        primary["db"].topics.update_one(
            {"course_id": cid, "subject_id": sid, "topic_id": tid},
            {"$set": set_doc, "$setOnInsert": on_insert},
            upsert=True
        )
        ram_cache.invalidate_prefix(f"cv_topics:{cid}:{sid}")
        return True

    def get_subject_topics(self, course_id, subject_id):
        cid, sid = str(course_id or "").strip(), str(subject_id or "").strip()
        key = f"cv_topics:{cid}:{sid}"
        cached = ram_cache.get(key)
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        if not primary or not cid or not sid:
            return []
        docs = [_clean_doc(d) for d in primary["db"].topics.find({"course_id": cid, "subject_id": sid}).sort("ts", 1)]
        ram_cache.set(key, docs, ttl_sec=60)
        return docs

    # =========================================================
    # LECTURES (DUAL-CHECK: YT + DRIVE + TELEGRAM + AUTO-INDEX)
    # =========================================================
    def _effective_course_config(self, course_id, subject_id=""):
        settings = self.get_all_settings()
        tg_core = settings.get("telegram_core", {})
        primary = self.get_primary_db()
        c_doc = primary["db"].courses.find_one({"course_id": str(course_id)}) if primary else None
        s_doc = primary["db"].subjects.find_one({"course_id": str(course_id), "subject_id": str(subject_id)}) if (primary and subject_id) else None

        global_mode = tg_core.get("global_upload_mode", "both")
        course_mode = (c_doc or {}).get("upload_mode") or global_mode
        if not tg_core.get("enabled", True) and course_mode == "both":
            course_mode = "only_yt"

        tg_channel_id = (s_doc or {}).get("tg_channel_id") or (c_doc or {}).get("tg_channel_id") or ""
        tg_topic_id = (s_doc or {}).get("tg_topic_id") or ""
        tg_channel_link = (c_doc or {}).get("tg_channel_link") or settings.get("portal_fallback", {}).get("default_tg_invite_link", "")
        return {
            "upload_mode": course_mode,
            "tg_channel_id": str(tg_channel_id).strip(),
            "tg_topic_id": str(tg_topic_id).strip(),
            "tg_channel_link": str(tg_channel_link).strip(),
            "priority": (c_doc or {}).get("priority", "normal"),
            "playback_mode": (c_doc or {}).get("playback_mode", "vault_first"),
            "tg_index_msg_id": (c_doc or {}).get("tg_index_msg_id", "")
        }

    def _is_lecture_missing_assets(self, doc, course_id, subject_id="", raw_thumb="", has_pdf1=False, has_pdf2=False):
        if not doc:
            return True, True, True
        cfg = self._effective_course_config(course_id, subject_id)
        mode = cfg["upload_mode"]

        need_yt = mode in ("both", "only_yt")
        need_tg = mode in ("both", "only_tg") and bool(cfg["tg_channel_id"])

        yt_missing = False
        if need_yt:
            if not str(doc.get("yt_video_id") or "").strip():
                yt_missing = True
            if raw_thumb and not str(doc.get("drive_thumb_id") or "").strip():
                yt_missing = True
            if has_pdf1 and not str(doc.get("drive_pdf1_id") or "").strip():
                yt_missing = True
            if has_pdf2 and not str(doc.get("drive_pdf2_id") or "").strip():
                yt_missing = True

        tg_missing = False
        if need_tg:
            if not str(doc.get("tg_video_msg_id") or "").strip():
                tg_missing = True
            if has_pdf1 and not str(doc.get("tg_pdf1_msg_id") or "").strip():
                tg_missing = True
            if has_pdf2 and not str(doc.get("tg_pdf2_msg_id") or "").strip():
                tg_missing = True

        return (yt_missing or tg_missing), yt_missing, tg_missing

    def upsert_lecture_metadata(self, course_id, course_name, subject_id, subject_name, topic_id, topic_name, lec_obj):
        lid = str(lec_obj.get("id") or lec_obj.get("lecture_id") or "").strip()
        if not lid:
            return {"ok": False, "reason": "missing_id"}

        existing_shard = self._find_lecture_shard(lid)
        existing_doc = None
        if existing_shard:
            target_shard = existing_shard
            existing_doc = existing_shard["db"].lectures.find_one({"lecture_id": lid})
            is_new = False
        else:
            target_shard = self.pick_best_shard()
            if not target_shard:
                return {"ok": False, "storage_full": True, "reason": f"All Course DBs hit {config.MAX_COURSE_DB_SIZE_MB} MB limit!"}
            is_new = True

        raw_thumb = str(lec_obj.get("thumbnail") or "").replace("\\/", "/").strip()
        has_pdf1 = bool(str(lec_obj.get("pdf_link") or lec_obj.get("ypdf_link") or "").strip())
        has_pdf2 = bool(str(lec_obj.get("pdf_link2") or "").strip())
        now_str = now_ist_str()

        set_fields = {
            "lecture_id": lid,
            "id": lid,
            "course_id": str(course_id),
            "course_name": str(course_name),
            "subject_id": str(subject_id),
            "subject_name": str(subject_name),
            "topic_id": str(topic_id),
            "topic_name": str(topic_name),
            "title": str(lec_obj.get("Title") or lec_obj.get("title") or f"Class #{lid}").strip(),
            "date_and_time": str(lec_obj.get("date_and_time") or ""),
            "source_thumb": raw_thumb,
            "has_pdf1": has_pdf1,
            "has_pdf2": has_pdf2,
            "db_shard": target_shard["label"],
            "updated_at": now_str
        }

        requeued = False
        if existing_doc:
            if not existing_doc.get("seq_index"):
                seq_num = self.get_next_seq_index(course_id)
                set_fields["seq_index"] = seq_num
                set_fields["seq_code"] = str(seq_num).zfill(3)

            any_miss, yt_miss, tg_miss = self._is_lecture_missing_assets(
                existing_doc, course_id, subject_id, raw_thumb, has_pdf1, has_pdf2
            )
            if existing_doc.get("status") != "processing" and any_miss:
                set_fields["status"] = "pending"
                set_fields["error_message"] = ""
                set_fields["next_retry_ts"] = 0
                if yt_miss:
                    set_fields["yt_status"] = "pending"
                if tg_miss:
                    set_fields["tg_status"] = "pending"
                requeued = True
        else:
            seq_num = self.get_next_seq_index(course_id)
            set_fields["seq_index"] = seq_num
            set_fields["seq_code"] = str(seq_num).zfill(3)

        on_insert = {
            "status": "pending",
            "yt_status": "pending",
            "tg_status": "pending",
            "source_video_url": "",
            "source_pdf1_url": "",
            "source_pdf2_url": "",
            "yt_video_id": "",
            "drive_pdf1_id": "",
            "drive_pdf2_id": "",
            "drive_thumb_id": "",
            "drive_thumb_url": "",
            "tg_channel_id": "",
            "tg_topic_id": "",
            "tg_video_msg_id": "",
            "tg_pdf1_msg_id": "",
            "tg_pdf2_msg_id": "",
            "tg_master_video_msg_id": "",
            "tg_master_pdf1_msg_id": "",
            "tg_master_pdf2_msg_id": "",
            "tg_video_link": "",
            "error_message": "",
            "yt_error": "",
            "tg_error": "",
            "retry_count": 0,
            "next_retry_ts": 0,
            "first_saved_at": now_str,
            "ts": int(time.time())
        }

        for k in list(set_fields.keys()):
            on_insert.pop(k, None)

        update_doc = {"$set": set_fields}
        if on_insert:
            update_doc["$setOnInsert"] = on_insert

        target_shard["db"].lectures.update_one(
            {"lecture_id": lid},
            update_doc,
            upsert=True
        )
        ram_cache.invalidate_prefix(f"cv_lectures:{course_id}:{subject_id}:{topic_id}")
        ram_cache.invalidate_prefix(f"cv_lec:{lid}")
        ram_cache.invalidate_prefix("cv_summary")
        ram_cache.invalidate_prefix("cv_courses")
        return {"ok": True, "is_new": is_new, "requeued": requeued, "shard": target_shard["label"]}

    def recheck_scope(self, course_id="", subject_id="", topic_id="", lecture_id="", force_all=False, target="both"):
        q = {}
        if lecture_id:
            q["lecture_id"] = str(lecture_id).strip()
        else:
            if course_id:
                q["course_id"] = str(course_id).strip()
            if subject_id:
                q["subject_id"] = str(subject_id).strip()
            if topic_id:
                q["topic_id"] = str(topic_id).strip()

        if not force_all and not lecture_id:
            ors = [{"status": {"$in": ["failed", "processing"]}}]
            if target in ("both", "yt"):
                ors.extend([
                    {"yt_video_id": {"$in": ["", None]}},
                    {"drive_thumb_id": {"$in": ["", None]}},
                    {"drive_pdf1_id": {"$in": ["", None]}},
                    {"yt_status": {"$in": ["failed", "pending"]}}
                ])
            if target in ("both", "tg"):
                ors.extend([
                    {"tg_video_msg_id": {"$in": ["", None]}},
                    {"tg_status": {"$in": ["failed", "pending"]}}
                ])
            q["$or"] = ors

        upd = {
            "status": "pending",
            "error_message": "",
            "next_retry_ts": 0,
            "updated_at": now_ist_str()
        }
        if target in ("both", "yt"):
            upd["yt_status"] = "pending"
            upd["yt_error"] = ""
        if target in ("both", "tg"):
            upd["tg_status"] = "pending"
            upd["tg_error"] = ""

        count = 0
        for entry in self.dbs:
            try:
                res = entry["db"].lectures.update_many(q, {"$set": upd})
                count += res.modified_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return count

    def claim_next_lecture_one_by_one(self):
        settings = self.get_all_settings()
        wc = settings.get("worker_control", {})
        if wc.get("state") == "PAUSED":
            return None

        skip_id = str(wc.get("skip_lecture_id") or "").strip()
        if skip_id:
            self.finish_lecture_item(skip_id, ok=False, error_message="Skipped by Admin from Panel", skipped=True)
            self.set_worker_control(skip_lecture_id="")

        # Prevent duplicate processing
        for entry in self.dbs:
            try:
                busy = entry["db"].lectures.find_one({"status": "processing"})
                if busy:
                    return None
            except Exception:
                continue

        now_ts = int(time.time())
        base_q = {
            "status": "pending",
            "$or": [{"next_retry_ts": {"$exists": False}}, {"next_retry_ts": {"$lte": now_ts}}]
        }

        # Check High Priority courses first
        primary = self.get_primary_db()
        high_cids = []
        if primary:
            try:
                high_cids = [str(d["course_id"]) for d in primary["db"].courses.find({"priority": "high"}, {"course_id": 1})]
            except Exception:
                pass

        queries = []
        if high_cids:
            q_hi = dict(base_q)
            q_hi["course_id"] = {"$in": high_cids}
            queries.append(q_hi)
        queries.append(base_q)

        for q in queries:
            for entry in self.dbs:
                try:
                    doc = entry["db"].lectures.find_one_and_update(
                        q,
                        {"$set": {"status": "processing", "updated_at": now_ist_str()}},
                        sort=[("seq_index", 1), ("ts", 1)],
                        return_document=True
                    )
                    if doc:
                        c = _clean_doc(doc)
                        eff = self._effective_course_config(c.get("course_id", ""), c.get("subject_id", ""))
                        c["effective_upload_mode"] = eff["upload_mode"]
                        c["effective_tg_channel_id"] = eff["tg_channel_id"]
                        c["effective_tg_topic_id"] = eff["tg_topic_id"]
                        c["effective_tg_channel_link"] = eff["tg_channel_link"]
                        c["course_tg_index_msg_id"] = eff["tg_index_msg_id"]
                        ram_cache.invalidate_prefix("cv_summary")
                        return c
                except Exception:
                    continue
        return None

    def finish_lecture_item(
        self, lecture_id, ok=True, yt_video_id="", drive_pdf1_id="", drive_pdf2_id="",
        drive_thumb_id="", error_message="", yt_status="", tg_status="",
        tg_channel_id="", tg_topic_id="", tg_video_msg_id="", tg_pdf1_msg_id="",
        tg_pdf2_msg_id="", tg_master_video_msg_id="", tg_master_pdf1_msg_id="",
        tg_master_pdf2_msg_id="", yt_error="", tg_error="", skipped=False
    ):
        lid = str(lecture_id or "").strip()
        shard = self._find_lecture_shard(lid)
        if not shard:
            return False

        existing = shard["db"].lectures.find_one({"lecture_id": lid}) or {}
        settings = self.get_all_settings()
        rr = settings.get("retry_and_reports", {})

        final_yt_id = str(yt_video_id or existing.get("yt_video_id") or "").strip()
        final_tg_vid = str(tg_video_msg_id or existing.get("tg_video_msg_id") or "").strip()
        final_tg_ch = str(tg_channel_id or existing.get("tg_channel_id") or "").strip()

        eff = self._effective_course_config(existing.get("course_id", ""), existing.get("subject_id", ""))
        tg_link = build_tg_msg_link(final_tg_ch or eff["tg_channel_id"], final_tg_vid, eff["tg_channel_link"])

        retry_count = int(existing.get("retry_count", 0))
        next_retry_ts = 0
        final_status = "completed" if ok else "failed"

        if not ok and not skipped and rr.get("auto_retry_enabled", True):
            max_r = int(rr.get("max_retries", 3))
            if retry_count < max_r:
                retry_count += 1
                cooldown = max(1, int(rr.get("retry_cooldown_mins", 10)))
                next_retry_ts = int(time.time()) + (cooldown * 60)
                final_status = "pending"

        upd = {
            "status": final_status,
            "error_message": "" if ok else str(error_message or "Upload/Download failed")[:220],
            "retry_count": retry_count,
            "next_retry_ts": next_retry_ts,
            "updated_at": now_ist_str()
        }
        if yt_status in ("completed", "pending", "failed", "skipped"):
            upd["yt_status"] = yt_status
        elif final_yt_id:
            upd["yt_status"] = "completed"

        if tg_status in ("completed", "pending", "failed", "skipped"):
            upd["tg_status"] = tg_status
        elif final_tg_vid:
            upd["tg_status"] = "completed"

        if yt_error is not None:
            upd["yt_error"] = "" if upd.get("yt_status") == "completed" else str(yt_error)[:180]
        if tg_error is not None:
            upd["tg_error"] = "" if upd.get("tg_status") == "completed" else str(tg_error)[:180]

        if yt_video_id:
            upd["yt_video_id"] = str(yt_video_id).strip()
        if drive_pdf1_id:
            upd["drive_pdf1_id"] = str(drive_pdf1_id).strip()
        if drive_pdf2_id:
            upd["drive_pdf2_id"] = str(drive_pdf2_id).strip()
        if drive_thumb_id:
            upd["drive_thumb_id"] = str(drive_thumb_id).strip()
            upd["drive_thumb_url"] = drive_image_url(drive_thumb_id)
        if tg_channel_id:
            upd["tg_channel_id"] = str(tg_channel_id).strip()
        if tg_topic_id:
            upd["tg_topic_id"] = str(tg_topic_id).strip()
        if tg_video_msg_id:
            upd["tg_video_msg_id"] = str(tg_video_msg_id).strip()
        if tg_pdf1_msg_id:
            upd["tg_pdf1_msg_id"] = str(tg_pdf1_msg_id).strip()
        if tg_pdf2_msg_id:
            upd["tg_pdf2_msg_id"] = str(tg_pdf2_msg_id).strip()
        if tg_master_video_msg_id:
            upd["tg_master_video_msg_id"] = str(tg_master_video_msg_id).strip()
        if tg_master_pdf1_msg_id:
            upd["tg_master_pdf1_msg_id"] = str(tg_master_pdf1_msg_id).strip()
        if tg_master_pdf2_msg_id:
            upd["tg_master_pdf2_msg_id"] = str(tg_master_pdf2_msg_id).strip()
        if tg_link:
            upd["tg_video_link"] = tg_link

        shard["db"].lectures.update_one({"lecture_id": lid}, {"$set": upd})

        if ok:
            primary = self.get_primary_db()
            if primary:
                try:
                    primary["db"].vault_settings.update_one(
                        {"_id": "master_config"},
                        {"$inc": {"retry_and_reports.uploads_since_backup": 1}},
                        upsert=True
                    )
                except Exception:
                    pass

        ram_cache.invalidate_prefix("cv_")
        return True

    def _decorate_lecture(self, d, playback_mode="vault_first", tg_fallback_enabled=True, default_tg_link=""):
        c = _clean_doc(d)
        c["playback_mode"] = playback_mode
        c["thumbnail"] = c.get("drive_thumb_url") or c.get("source_thumb") or ""
        c["drive_pdf1_url"] = f"https://drive.google.com/file/d/{c['drive_pdf1_id']}/preview" if c.get("drive_pdf1_id") else ""
        c["drive_pdf2_url"] = f"https://drive.google.com/file/d/{c['drive_pdf2_id']}/preview" if c.get("drive_pdf2_id") else ""
        c["tg_fallback_enabled"] = tg_fallback_enabled
        c["tg_fallback_url"] = c.get("tg_video_link") or build_tg_msg_link(
            c.get("tg_channel_id", ""), c.get("tg_video_msg_id", ""), default_tg_link
        )
        return c

    def get_topic_lectures(self, course_id, subject_id, topic_id):
        cid, sid, tid = str(course_id), str(subject_id), str(topic_id)
        key = f"cv_lectures:{cid}:{sid}:{tid}"
        cached = ram_cache.get(key)
        if cached is not None:
            return cached

        eff = self._effective_course_config(cid, sid)
        pf = self.get_all_settings().get("portal_fallback", {})
        merged = []
        for entry in self.dbs:
            try:
                for d in entry["db"].lectures.find({"course_id": cid, "subject_id": sid, "topic_id": tid}).sort([("seq_index", 1), ("ts", 1)]):
                    merged.append(self._decorate_lecture(
                        d,
                        playback_mode=eff["playback_mode"],
                        tg_fallback_enabled=bool(pf.get("tg_fallback_enabled", True)),
                        default_tg_link=eff["tg_channel_link"]
                    ))
            except Exception:
                continue

        ram_cache.set(key, merged, ttl_sec=45)
        return merged

    def get_single_lecture(self, lecture_id):
        lid = str(lecture_id or "").strip()
        cached = ram_cache.get(f"cv_lec:{lid}")
        if cached is not None:
            return cached
        shard = self._find_lecture_shard(lid)
        if not shard:
            return None
        doc = shard["db"].lectures.find_one({"lecture_id": lid})
        if not doc:
            return None
        eff = self._effective_course_config(doc.get("course_id", ""), doc.get("subject_id", ""))
        pf = self.get_all_settings().get("portal_fallback", {})
        c = self._decorate_lecture(
            doc,
            playback_mode=eff["playback_mode"],
            tg_fallback_enabled=bool(pf.get("tg_fallback_enabled", True)),
            default_tg_link=eff["tg_channel_link"]
        )
        ram_cache.set(f"cv_lec:{lid}", c, ttl_sec=60)
        return c

    def get_course_index_lectures(self, course_id):
        cid = str(course_id or "").strip()
        items = []
        for entry in self.dbs:
            try:
                for d in entry["db"].lectures.find({"course_id": cid}).sort([("seq_index", 1), ("ts", 1)]):
                    items.append(_clean_doc(d))
            except Exception:
                continue
        items.sort(key=lambda x: (int(x.get("seq_index", 999999)), int(x.get("ts", 0))))
        return items

    def manual_override_lecture(
        self, lecture_id, yt_video_id="", drive_pdf1_id="", drive_pdf2_id="",
        drive_thumb_id="", tg_video_msg_id="", tg_pdf1_msg_id="", tg_pdf2_msg_id=""
    ):
        lid = str(lecture_id or "").strip()
        shard = self._find_lecture_shard(lid)
        if not shard:
            return False
        upd = {"updated_at": now_ist_str()}
        if yt_video_id is not None and str(yt_video_id).strip():
            upd["yt_video_id"] = str(yt_video_id).strip()
            upd["yt_status"] = "completed"
            upd["status"] = "completed"
            upd["error_message"] = ""
        if drive_pdf1_id is not None and str(drive_pdf1_id).strip():
            upd["drive_pdf1_id"] = str(drive_pdf1_id).strip()
        if drive_pdf2_id is not None and str(drive_pdf2_id).strip():
            upd["drive_pdf2_id"] = str(drive_pdf2_id).strip()
        if drive_thumb_id is not None and str(drive_thumb_id).strip():
            upd["drive_thumb_id"] = str(drive_thumb_id).strip()
            upd["drive_thumb_url"] = drive_image_url(drive_thumb_id)
        if tg_video_msg_id is not None and str(tg_video_msg_id).strip():
            upd["tg_video_msg_id"] = str(tg_video_msg_id).strip()
            upd["tg_status"] = "completed"
        if tg_pdf1_msg_id is not None and str(tg_pdf1_msg_id).strip():
            upd["tg_pdf1_msg_id"] = str(tg_pdf1_msg_id).strip()
        if tg_pdf2_msg_id is not None and str(tg_pdf2_msg_id).strip():
            upd["tg_pdf2_msg_id"] = str(tg_pdf2_msg_id).strip()

        shard["db"].lectures.update_one({"lecture_id": lid}, {"$set": upd})
        ram_cache.invalidate_prefix("cv_")
        return True

    def reset_failed_lectures_to_pending(self, lecture_id="", target="both"):
        count = 0
        q = {"lecture_id": str(lecture_id).strip()} if lecture_id else {"status": {"$in": ["failed", "processing"]}}
        upd = {"status": "pending", "error_message": "", "retry_count": 0, "next_retry_ts": 0}
        if target in ("both", "yt"):
            upd["yt_status"] = "pending"
            upd["yt_error"] = ""
        if target in ("both", "tg"):
            upd["tg_status"] = "pending"
            upd["tg_error"] = ""
        for entry in self.dbs:
            try:
                res = entry["db"].lectures.update_many(q, {"$set": upd})
                count += res.modified_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return count

    # =========================================================
    # 1-CLICK CHANNEL RESTORE QUEUE (FROM MASTER BACKUP)
    # =========================================================
    def create_restore_job(self, course_id, target_channel_id, subject_id="", target_topic_id=""):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        tch = str(target_channel_id or "").strip()
        if not primary or not cid or not tch:
            return None
        jid = f"rst_{int(time.time())}_{uuid.uuid4().hex[:5]}"
        now_str = now_ist_str()
        doc = {
            "job_id": jid,
            "course_id": cid,
            "subject_id": str(subject_id or "").strip(),
            "target_channel_id": tch,
            "target_topic_id": str(target_topic_id or "").strip(),
            "status": "pending",
            "done_count": 0,
            "total_count": 0,
            "error": "",
            "created_at": now_str,
            "updated_at": now_str,
            "ts": int(time.time())
        }
        primary["db"].restore_jobs.insert_one(doc)
        # Also update course/subject channel ID to new target
        if subject_id:
            self.update_subject_settings(cid, subject_id, tg_channel_id=tch, tg_topic_id=target_topic_id)
        else:
            self.update_course_settings(cid, tg_channel_id=tch)
        ram_cache.invalidate_prefix("cv_summary")
        return _clean_doc(doc)

    def get_restore_jobs(self, limit=20):
        primary = self.get_primary_db()
        if not primary:
            return []
        try:
            return [_clean_doc(d) for d in primary["db"].restore_jobs.find().sort("ts", DESCENDING).limit(limit)]
        except Exception:
            return []

    def claim_next_restore_job(self):
        primary = self.get_primary_db()
        if not primary:
            return None
        doc = primary["db"].restore_jobs.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "running", "updated_at": now_ist_str()}},
            sort=[("ts", 1)],
            return_document=True
        )
        if not doc:
            return None
        job = _clean_doc(doc)
        # Attach all lectures with master backup message IDs
        q = {"course_id": job["course_id"]}
        if job.get("subject_id"):
            q["subject_id"] = job["subject_id"]
        msgs = []
        for entry in self.dbs:
            try:
                for d in entry["db"].lectures.find(q):
                    if d.get("tg_master_video_msg_id") or d.get("tg_master_pdf1_msg_id") or d.get("tg_master_pdf2_msg_id"):
                        msgs.append({
                            "lecture_id": str(d.get("lecture_id")),
                            "seq_index": int(d.get("seq_index", 0)),
                            "title": d.get("title", ""),
                            "tg_master_video_msg_id": str(d.get("tg_master_video_msg_id") or ""),
                            "tg_master_pdf1_msg_id": str(d.get("tg_master_pdf1_msg_id") or ""),
                            "tg_master_pdf2_msg_id": str(d.get("tg_master_pdf2_msg_id") or "")
                        })
            except Exception:
                continue
        msgs.sort(key=lambda x: x["seq_index"])
        job["items"] = msgs
        return job

    def update_restore_job(self, job_id, status, done_count=0, total_count=0, error=""):
        primary = self.get_primary_db()
        if not primary or not job_id:
            return False
        primary["db"].restore_jobs.update_one(
            {"job_id": str(job_id).strip()},
            {"$set": {
                "status": str(status),
                "done_count": int(done_count or 0),
                "total_count": int(total_count or 0),
                "error": str(error or "")[:200],
                "updated_at": now_ist_str()
            }}
        )
        ram_cache.invalidate_prefix("cv_summary")
        return True

    # =========================================================
    # WORKER HEARTBEAT (WITH STORAGE, BATTERY & ACTIVE BOT)
    # =========================================================
    def update_worker_heartbeat(self, payload):
        primary = self.get_primary_db()
        if not primary or not isinstance(payload, dict):
            return False
        doc = {
            "status": str(payload.get("status") or "ONLINE"),
            "current_task": str(payload.get("current_task") or "")[:200],
            "progress": int(payload.get("progress") or 0),
            "free_gb": payload.get("free_gb"),
            "battery_pct": payload.get("battery_pct"),
            "active_bot": str(payload.get("active_bot") or ""),
            "active_yt_project": str(payload.get("active_yt_project") or ""),
            "updated_at": now_ist_str(),
            "ts": int(time.time())
        }
        primary["db"].worker_status.update_one(
            {"_id": "termux_archiver"},
            {"$set": doc},
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_summary")
        return True

    def get_worker_heartbeat(self):
        primary = self.get_primary_db()
        if not primary:
            return {"online": False, "status": "OFFLINE"}
        doc = primary["db"].worker_status.find_one({"_id": "termux_archiver"})
        if not doc:
            return {"online": False, "status": "OFFLINE", "message": "Termux worker abhi tak connect nahi hua."}
        d = _clean_doc(doc)
        age = int(time.time()) - int(d.get("ts", 0))
        d["online"] = age <= 90
        d["seconds_ago"] = max(0, age)
        if not d["online"]:
            d["status"] = "OFFLINE"
        return d

    # =========================================================
    # FULL JSON BACKUP & RESTORE
    # =========================================================
    def export_full_json_backup(self):
        primary = self.get_primary_db()
        data = {
            "exported_at": now_ist_str(),
            "settings": self.get_all_settings(),
            "tg_bots": self.get_tg_bots(include_inactive=True),
            "courses": [],
            "subjects": [],
            "topics": [],
            "lectures": []
        }
        if primary:
            data["courses"] = [_clean_doc(d) for d in primary["db"].courses.find()]
            data["subjects"] = [_clean_doc(d) for d in primary["db"].subjects.find()]
            data["topics"] = [_clean_doc(d) for d in primary["db"].topics.find()]
        for entry in self.dbs:
            try:
                for d in entry["db"].lectures.find():
                    data["lectures"].append(_clean_doc(d))
            except Exception:
                continue
        return data

    def import_full_json_backup(self, data):
        if not isinstance(data, dict):
            return {"ok": False, "message": "Invalid JSON backup"}
        primary = self.get_primary_db()
        if not primary:
            return {"ok": False, "message": "No primary DB"}
        counts = {"courses": 0, "subjects": 0, "topics": 0, "lectures": 0, "bots": 0}

        if isinstance(data.get("settings"), dict):
            self.update_settings(data["settings"])

        for b in (data.get("tg_bots") or []):
            if isinstance(b, dict) and b.get("token"):
                self.upsert_tg_bot(b.get("bot_id", ""), b.get("label", "TG Bot"), b["token"], b.get("active", True), b.get("order", 0))
                counts["bots"] += 1

        for c in (data.get("courses") or []):
            if isinstance(c, dict) and c.get("course_id"):
                d = dict(c)
                d.pop("_id", None)
                primary["db"].courses.update_one({"course_id": str(d["course_id"])}, {"$set": d}, upsert=True)
                counts["courses"] += 1

        for s in (data.get("subjects") or []):
            if isinstance(s, dict) and s.get("course_id") and s.get("subject_id"):
                d = dict(s)
                d.pop("_id", None)
                primary["db"].subjects.update_one(
                    {"course_id": str(d["course_id"]), "subject_id": str(d["subject_id"])},
                    {"$set": d},
                    upsert=True
                )
                counts["subjects"] += 1

        for t in (data.get("topics") or []):
            if isinstance(t, dict) and t.get("course_id") and t.get("subject_id") and t.get("topic_id"):
                d = dict(t)
                d.pop("_id", None)
                primary["db"].topics.update_one(
                    {"course_id": str(d["course_id"]), "subject_id": str(d["subject_id"]), "topic_id": str(d["topic_id"])},
                    {"$set": d},
                    upsert=True
                )
                counts["topics"] += 1

        shard = self.pick_best_shard() or primary
        for l in (data.get("lectures") or []):
            if isinstance(l, dict) and l.get("lecture_id"):
                d = dict(l)
                d.pop("_id", None)
                lid = str(d["lecture_id"])
                target = self._find_lecture_shard(lid) or shard
                target["db"].lectures.update_one({"lecture_id": lid}, {"$set": d}, upsert=True)
                counts["lectures"] += 1

        ram_cache.invalidate_prefix("cv_")
        return {"ok": True, "restored": counts}

    # =========================================================
    # DIRECT SUMMARY (OLD FIELDS 100% INTACT + SEPARATE YT & TG STATS)
    # =========================================================
    def get_direct_summary(self):
        cached = ram_cache.get("cv_summary:main")
        if cached is not None:
            return cached

        primary = self.get_primary_db()
        total_courses = total_subjects = total_topics = 0
        courses_thumbs_ready = subjects_logos_ready = 0
        tg_bots_total = tg_bots_active = active_restore_jobs = 0

        if primary:
            try:
                total_courses = primary["db"].courses.count_documents({})
                courses_thumbs_ready = primary["db"].courses.count_documents({"drive_thumb_id": {"$ne": ""}})
                total_subjects = primary["db"].subjects.count_documents({})
                subjects_logos_ready = primary["db"].subjects.count_documents({"drive_logo_id": {"$ne": ""}})
                total_topics = primary["db"].topics.count_documents({})
                tg_bots_total = primary["db"].tg_bots.count_documents({})
                tg_bots_active = primary["db"].tg_bots.count_documents({"active": {"$ne": False}})
                active_restore_jobs = primary["db"].restore_jobs.count_documents({"status": {"$in": ["pending", "running"]}})
            except Exception:
                pass

        total_lectures = yt_ready = pdf_ready = thumbs_ready = pending = failed = processing = completed = 0
        yt_pending = yt_failed = 0
        tg_ready = tg_pending = tg_failed = tg_pdf_ready = 0
        per_shard = []
        any_space = False

        for entry in self.dbs:
            db = entry["db"]
            try:
                l_cnt = db.lectures.count_documents({})
                y_cnt = db.lectures.count_documents({"yt_video_id": {"$ne": ""}})
                y_fail = db.lectures.count_documents({"yt_status": "failed"})
                y_pend = db.lectures.count_documents({"yt_video_id": {"$in": ["", None]}, "yt_status": {"$nin": ["failed", "skipped"]}})

                t_vid = db.lectures.count_documents({"tg_video_msg_id": {"$ne": ""}})
                t_fail = db.lectures.count_documents({"tg_status": "failed"})
                t_pend = db.lectures.count_documents({"tg_video_msg_id": {"$in": ["", None]}, "tg_status": {"$nin": ["failed", "skipped"]}})
                t_pdf = db.lectures.count_documents({"$or": [{"tg_pdf1_msg_id": {"$ne": ""}}, {"tg_pdf2_msg_id": {"$ne": ""}}]})

                p_cnt = db.lectures.count_documents({"$or": [{"drive_pdf1_id": {"$ne": ""}}, {"drive_pdf2_id": {"$ne": ""}}]})
                th_cnt = db.lectures.count_documents({"drive_thumb_id": {"$ne": ""}})
                comp_cnt = db.lectures.count_documents({"status": "completed"})
                pen_cnt = db.lectures.count_documents({"status": "pending"})
                fail_cnt = db.lectures.count_documents({"status": "failed"})
                proc_cnt = db.lectures.count_documents({"status": "processing"})
                mb = self.get_db_size_mb(entry)
                is_full = mb >= config.MAX_COURSE_DB_SIZE_MB
                if not is_full:
                    any_space = True

                total_lectures += l_cnt
                yt_ready += y_cnt
                yt_pending += y_pend
                yt_failed += y_fail
                tg_ready += t_vid
                tg_pending += t_pend
                tg_failed += t_fail
                tg_pdf_ready += t_pdf
                pdf_ready += p_cnt
                thumbs_ready += th_cnt
                completed += comp_cnt
                pending += pen_cnt
                failed += fail_cnt
                processing += proc_cnt

                per_shard.append({
                    "label": entry["label"],
                    "lectures": l_cnt,
                    "yt_ready": y_cnt,
                    "tg_ready": t_vid,
                    "size_mb": mb,
                    "max_mb": config.MAX_COURSE_DB_SIZE_MB,
                    "is_full": is_full
                })
            except Exception:
                per_shard.append({"label": entry["label"], "error": True})

        yt_pct = int((yt_ready / total_lectures) * 100) if total_lectures else 0
        tg_pct = int((tg_ready / total_lectures) * 100) if total_lectures else 0

        summary = {
            "connected_dbs": len(self.dbs),
            "storage_full": (len(self.dbs) > 0 and not any_space),
            "max_mb_per_db": config.MAX_COURSE_DB_SIZE_MB,
            "total_courses": total_courses,
            "courses_thumbs_ready": courses_thumbs_ready,
            "total_subjects": total_subjects,
            "subjects_logos_ready": subjects_logos_ready,
            "total_topics": total_topics,
            "total_lectures": total_lectures,
            "completed_lectures": completed,
            "yt_ready": yt_ready,
            "tg_ready": tg_ready,
            "tg_pdf_ready": tg_pdf_ready,
            "pdf_ready": pdf_ready,
            "thumbs_ready": thumbs_ready,
            "pending_queue": pending,
            "processing_now": processing,
            "failed_queue": failed,
            "yt_stats": {
                "completed": yt_ready,
                "pending": yt_pending,
                "failed": yt_failed,
                "progress_pct": yt_pct
            },
            "tg_stats": {
                "completed": tg_ready,
                "pending": tg_pending,
                "failed": tg_failed,
                "progress_pct": tg_pct
            },
            "tg_bots_total": tg_bots_total,
            "tg_bots_active": tg_bots_active,
            "active_restore_jobs": active_restore_jobs,
            "worker_control": self.get_all_settings().get("worker_control", {}),
            "per_shard": per_shard,
            "worker": self.get_worker_heartbeat(),
            "ram_cache": ram_cache.stats(),
            "updated_at": now_ist_str()
        }
        ram_cache.set("cv_summary:main", summary, ttl_sec=15)
        return summary


course_vault_db = CourseVaultDB()

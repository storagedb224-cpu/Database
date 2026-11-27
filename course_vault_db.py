import copy
import threading
import time
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, DESCENDING
import config

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_ADMIN_SETTINGS = {
    "tg_api_id": "",
    "tg_api_hash": "",
    "tg_bots": [],
    "master_backup_channel": "",
    "auto_forward_master": True,
    "admin_alert_chat_id": "",
    "auto_pin_index": True,
    "seq_indexing": True,
    "brand_tag": "RWB | 𝕮𝖍𝖆𝖚𝖉𝖍𝖆𝖗𝖄",
    "brand_link": "",
    "video_caption_tpl": (
        "🎬 {course}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔢 Index   : #{index}\n"
        "📚 Subject : {subject}\n"
        "📂 Topic   : {topic}\n"
        "📝 Class   : {title}\n"
        "🆔 Class ID: #{id}\n"
        "📅 Date    : {date}\n"
        "🏷️ Backup  : {brand}"
    ),
    "pdf_caption_tpl": (
        "📄 [{pdf_label}] {title}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔢 Index   : #{index}\n"
        "🎓 Batch   : {course}\n"
        "📚 Subject : {subject}\n"
        "📂 Topic   : {topic}\n"
        "🆔 Class ID: #{id}\n"
        "🏷️ Backup  : {brand}"
    ),
    "inline_buttons": [],
    "pdf_watermark_enabled": False,
    "pdf_watermark_text": "RWA Vault | RWB",
    "worker_paused": False,
    "skip_lecture_id": "",
    "download_threads": 12,
    "max_tg_size_mb": 1950,
    "large_file_mode": "split",
    "guard_enabled": True,
    "min_storage_gb": 2.0,
    "min_battery_pct": 15,
    "max_retries": 3,
    "retry_cooldown_min": 10,
    "auto_json_backup": True,
    "backup_every_n": 50,
    "backup_interval_hours": 24,
    "daily_report_enabled": True,
    "daily_report_hour_ist": 22,
    "portal_tg_fallback": True,
    "backup_now_ts": 0,
    "report_now_ts": 0
}

PRIORITY_ORDER = {"high": 1, "normal": 2, "low": 3}


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
    return f"https://lh3.googleusercontent.com/d/{fid}=w1000" if fid else ""


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

    # ---------------- GLOBAL ADMIN SETTINGS ----------------
    def get_admin_settings(self):
        cached = ram_cache.get("cv_settings:global")
        if cached is not None:
            return copy.deepcopy(cached)
        merged = copy.deepcopy(DEFAULT_ADMIN_SETTINGS)
        primary = self.get_primary_db()
        if primary:
            try:
                doc = primary["db"].admin_settings.find_one({"_id": "global_config"})
                if doc:
                    for k, v in doc.items():
                        if k != "_id":
                            merged[k] = v
            except Exception:
                pass
        ram_cache.set("cv_settings:global", merged, ttl_sec=15)
        return copy.deepcopy(merged)

    def save_admin_settings(self, patch_dict, reset_defaults=False):
        primary = self.get_primary_db()
        if not primary:
            return False
        if reset_defaults:
            new_cfg = copy.deepcopy(DEFAULT_ADMIN_SETTINGS)
        else:
            new_cfg = self.get_admin_settings()
            for k, v in (patch_dict or {}).items():
                if k in DEFAULT_ADMIN_SETTINGS:
                    new_cfg[k] = v
        new_cfg["updated_at"] = now_ist_str()
        primary["db"].admin_settings.update_one(
            {"_id": "global_config"},
            {"$set": new_cfg},
            upsert=True
        )
        ram_cache.invalidate_prefix("cv_settings")
        ram_cache.invalidate_prefix("cv_summary")
        return True

    # ---------------- SCANNER TOKENS ----------------
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

    # ---------------- COURSES ----------------
    def upsert_course(self, course_obj):
        primary = self.get_primary_db()
        cid = str(course_obj.get("id") or course_obj.get("course_id") or "").strip()
        if not primary or not cid:
            return False
        raw_logo = str(course_obj.get("exam_logo") or course_obj.get("course_thumbnail") or "").replace("\\/", "/").strip()
        now_str = now_ist_str()
        set_doc = {
            "course_id": cid,
            "id": cid,
            "course_name": str(course_obj.get("course_name") or f"Batch #{cid}").strip(),
            "exam_category": str(course_obj.get("exam_category") or "RWA PAID BATCH"),
            "source_logo": raw_logo,
            "test_series_id": str(course_obj.get("test_series_id") or ""),
            "updated_at": now_str,
            "ts": int(time.time())
        }
        on_insert = {
            "drive_thumb_id": "",
            "drive_thumb_url": "",
            "thumb_status": "pending" if raw_logo.startswith("http") else "none",
            "playback_mode": "vault_first",
            "upload_mode": "both",
            "priority": "normal",
            "tg_channel_id": "",
            "tg_invite_link": "",
            "pinned_index_msg_id": 0,
            "seq_counter": 0,
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

    def update_course_config(self, course_id, data):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        if not primary or not cid:
            return False
        upd = {"updated_at": now_ist_str()}
        if "tg_channel_id" in data:
            upd["tg_channel_id"] = str(data.get("tg_channel_id") or "").strip()
        if "tg_invite_link" in data:
            upd["tg_invite_link"] = str(data.get("tg_invite_link") or "").strip()
        if data.get("upload_mode") in ("both", "tg_only", "yt_only"):
            upd["upload_mode"] = data["upload_mode"]
        if data.get("priority") in ("high", "normal", "low"):
            upd["priority"] = data["priority"]
        if data.get("playback_mode") in ("vault_first", "hls_live"):
            upd["playback_mode"] = data["playback_mode"]
        res = primary["db"].courses.update_one({"course_id": cid}, {"$set": upd})
        ram_cache.invalidate_prefix("cv_")
        return res.matched_count > 0

    def set_course_playback_mode(self, course_id, mode):
        return self.update_course_config(course_id, {"playback_mode": mode})

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

    def _classify_yt(self, row):
        if row.get("yt_video_id"):
            return "completed"
        st = row.get("yt_status") or row.get("status") or "pending"
        if st == "failed":
            return "failed"
        return "pending"

    def _classify_tg(self, row):
        if row.get("tg_video_msg_id"):
            return "completed"
        st = row.get("tg_status") or "pending"
        if st == "failed":
            return "failed"
        return "pending"

    def get_all_courses(self):
        cached = ram_cache.get("cv_courses:all")
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        if not primary:
            return []
        docs = [_clean_doc(d) for d in primary["db"].courses.find().sort("ts", DESCENDING)]

        stats = {}
        for entry in self.dbs:
            try:
                proj = {"course_id": 1, "status": 1, "yt_video_id": 1, "yt_status": 1, "tg_video_msg_id": 1, "tg_status": 1}
                for row in entry["db"].lectures.find({}, proj):
                    cid = str(row.get("course_id") or "")
                    st = stats.setdefault(cid, {
                        "total": 0,
                        "yt_c": 0, "yt_p": 0, "yt_f": 0,
                        "tg_c": 0, "tg_p": 0, "tg_f": 0
                    })
                    st["total"] += 1
                    yc = self._classify_yt(row)
                    tc = self._classify_tg(row)
                    if yc == "completed": st["yt_c"] += 1
                    elif yc == "failed": st["yt_f"] += 1
                    else: st["yt_p"] += 1
                    if tc == "completed": st["tg_c"] += 1
                    elif tc == "failed": st["tg_f"] += 1
                    else: st["tg_p"] += 1
            except Exception:
                continue

        for d in docs:
            cid = d["course_id"]
            st = stats.get(cid, {"total": 0, "yt_c": 0, "yt_p": 0, "yt_f": 0, "tg_c": 0, "tg_p": 0, "tg_f": 0})
            d["total_lectures"] = st["total"]
            d["yt_ready_lectures"] = st["yt_c"]
            d["pending_lectures"] = st["yt_p"] + st["yt_f"]
            d["yt_completed"] = st["yt_c"]
            d["yt_pending"] = st["yt_p"]
            d["yt_failed"] = st["yt_f"]
            d["tg_completed"] = st["tg_c"]
            d["tg_pending"] = st["tg_p"]
            d["tg_failed"] = st["tg_f"]
            d["upload_mode"] = d.get("upload_mode") or "both"
            d["priority"] = d.get("priority") or "normal"
            d["tg_channel_id"] = d.get("tg_channel_id") or ""
            d["tg_invite_link"] = d.get("tg_invite_link") or ""
            d["exam_logo"] = d.get("drive_thumb_url") or d.get("source_logo") or ""

        docs.sort(key=lambda x: (PRIORITY_ORDER.get(x.get("priority", "normal"), 2), -(x.get("ts") or 0)))
        ram_cache.set("cv_courses:all", docs, ttl_sec=25)
        return docs

    # ---------------- SUBJECTS & TOPICS ----------------
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

    def update_subject_config(self, course_id, subject_id, data):
        primary = self.get_primary_db()
        cid, sid = str(course_id or "").strip(), str(subject_id or "").strip()
        if not primary or not cid or not sid:
            return False
        upd = {"updated_at": now_ist_str()}
        if "tg_channel_id" in data:
            upd["tg_channel_id"] = str(data.get("tg_channel_id") or "").strip()
        if "tg_topic_id" in data:
            upd["tg_topic_id"] = str(data.get("tg_topic_id") or "").strip()
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
        ram_cache.set(f"cv_subjects:{cid}", docs, ttl_sec=45)
        return docs

    def upsert_topic(self, course_id, subject_id, top_obj):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        sid = str(subject_id or "").strip()
        tid = str(top_obj.get("topicid") or top_obj.get("topic_id") or "").strip()
        if not primary or not cid or not sid or not tid:
            return False
        now_str = now_ist_str()
        primary["db"].topics.update_one(
            {"course_id": cid, "subject_id": sid, "topic_id": tid},
            {
                "$set": {
                    "course_id": cid,
                    "subject_id": sid,
                    "topic_id": tid,
                    "topicid": tid,
                    "topic_name": str(top_obj.get("topic_name") or top_obj.get("topicname") or f"Topic #{tid}").strip(),
                    "updated_at": now_str,
                    "ts": int(time.time())
                },
                "$setOnInsert": {"first_saved_at": now_str}
            },
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
        ram_cache.set(key, docs, ttl_sec=45)
        return docs

    # ---------------- LECTURES (DUAL CHECK: YT + DRIVE + TELEGRAM) ----------------
    def _next_seq_no(self, course_id):
        primary = self.get_primary_db()
        if not primary:
            return 1
        doc = primary["db"].courses.find_one_and_update(
            {"course_id": str(course_id)},
            {"$inc": {"seq_counter": 1}},
            return_document=True
        )
        return int((doc or {}).get("seq_counter") or 1)

    def _is_lecture_missing_assets(self, doc, course_doc, raw_thumb="", has_pdf1=False, has_pdf2=False):
        if not doc:
            return True
        mode = (course_doc or {}).get("upload_mode", "both")
        has_tg_target = bool((course_doc or {}).get("tg_channel_id"))
        need_yt = mode in ("both", "yt_only")
        need_tg = mode in ("both", "tg_only") and has_tg_target

        if need_yt and not str(doc.get("yt_video_id") or "").strip():
            return True
        if need_tg and not str(doc.get("tg_video_msg_id") or "").strip():
            return True
        if raw_thumb and not str(doc.get("drive_thumb_id") or "").strip():
            return True
        if has_pdf1 and not str(doc.get("drive_pdf1_id") or "").strip():
            return True
        if has_pdf2 and not str(doc.get("drive_pdf2_id") or "").strip():
            return True
        if need_tg and has_pdf1 and not str(doc.get("tg_pdf1_msg_id") or "").strip():
            return True
        if need_tg and has_pdf2 and not str(doc.get("tg_pdf2_msg_id") or "").strip():
            return True
        return False

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

        primary = self.get_primary_db()
        course_doc = primary["db"].courses.find_one({"course_id": str(course_id)}) if primary else {}
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
            "db_shard": target_shard["label"],
            "updated_at": now_str
        }

        requeued = False
        if existing_doc:
            if not existing_doc.get("seq_no"):
                set_fields["seq_no"] = self._next_seq_no(course_id)
            if existing_doc.get("status") != "processing" and self._is_lecture_missing_assets(
                existing_doc, course_doc, raw_thumb, has_pdf1, has_pdf2
            ):
                set_fields["status"] = "pending"
                set_fields["error_message"] = ""
                set_fields["next_retry_ts"] = 0
                if not existing_doc.get("yt_video_id"):
                    set_fields["yt_status"] = "pending"
                if not existing_doc.get("tg_video_msg_id"):
                    set_fields["tg_status"] = "pending"
                requeued = True

        seq_no = self._next_seq_no(course_id) if is_new else 0
        on_insert = {
            "seq_no": seq_no,
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
            "tg_video_msg_id": "",
            "tg_pdf1_msg_id": "",
            "tg_pdf2_msg_id": "",
            "tg_channel_used": "",
            "tg_topic_used": "",
            "master_video_msg_id": "",
            "master_pdf1_msg_id": "",
            "master_pdf2_msg_id": "",
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

        target_shard["db"].lectures.update_one({"lecture_id": lid}, update_doc, upsert=True)
        ram_cache.invalidate_prefix(f"cv_lectures:{course_id}:{subject_id}:{topic_id}")
        ram_cache.invalidate_prefix(f"cv_lec:{lid}")
        ram_cache.invalidate_prefix("cv_summary")
        return {"ok": True, "is_new": is_new, "requeued": requeued, "shard": target_shard["label"]}

    def recheck_scope(self, course_id="", subject_id="", topic_id="", lecture_id="", force_all=False):
        q = {}
        if lecture_id:
            q["lecture_id"] = str(lecture_id).strip()
        else:
            if course_id: q["course_id"] = str(course_id).strip()
            if subject_id: q["subject_id"] = str(subject_id).strip()
            if topic_id: q["topic_id"] = str(topic_id).strip()

        if not force_all and not lecture_id:
            q["$or"] = [
                {"yt_video_id": {"$in": ["", None]}},
                {"tg_video_msg_id": {"$in": ["", None]}},
                {"drive_thumb_id": {"$in": ["", None]}},
                {"drive_pdf1_id": {"$in": ["", None]}},
                {"status": {"$in": ["failed", "processing"]}},
                {"yt_status": "failed"},
                {"tg_status": "failed"}
            ]

        count = 0
        for entry in self.dbs:
            try:
                res = entry["db"].lectures.update_many(
                    q,
                    {"$set": {
                        "status": "pending",
                        "error_message": "",
                        "next_retry_ts": 0,
                        "retry_count": 0,
                        "updated_at": now_ist_str()
                    }}
                )
                count += res.modified_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return count

    def clear_pending_queue(self, course_id=""):
        deleted = 0
        q = {"status": {"$in": ["pending", "processing", "failed"]}}
        if course_id:
            q["course_id"] = str(course_id).strip()
        for entry in self.dbs:
            try:
                deleted += entry["db"].lectures.delete_many(q).deleted_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return deleted

    def reset_failed_lectures_to_pending(self, lecture_id=""):
        count = 0
        q = {"lecture_id": str(lecture_id).strip()} if lecture_id else {
            "$or": [{"status": {"$in": ["failed", "processing"]}}, {"yt_status": "failed"}, {"tg_status": "failed"}]
        }
        for entry in self.dbs:
            try:
                res = entry["db"].lectures.update_many(
                    q,
                    {"$set": {"status": "pending", "error_message": "", "next_retry_ts": 0, "retry_count": 0}}
                )
                count += res.modified_count
            except Exception:
                continue
        ram_cache.invalidate_prefix("cv_")
        return count

    def claim_next_lecture_one_by_one(self):
        cfg = self.get_admin_settings()
        if cfg.get("worker_paused"):
            return None

        for entry in self.dbs:
            try:
                if entry["db"].lectures.find_one({"status": "processing"}):
                    return None
            except Exception:
                continue

        now_ts = int(time.time())
        courses = self.get_all_courses()
        ordered_cids = [c["course_id"] for c in courses]

        base_filter = {
            "status": "pending",
            "$or": [{"next_retry_ts": {"$exists": False}}, {"next_retry_ts": {"$lte": now_ts}}]
        }

        for cid in ordered_cids:
            for entry in self.dbs:
                try:
                    doc = entry["db"].lectures.find_one_and_update(
                        {**base_filter, "course_id": cid},
                        {"$set": {"status": "processing", "updated_at": now_ist_str()}},
                        sort=[("seq_no", 1), ("ts", 1)],
                        return_document=True
                    )
                    if doc:
                        ram_cache.invalidate_prefix("cv_summary")
                        return _clean_doc(doc)
                except Exception:
                    continue

        for entry in self.dbs:
            try:
                doc = entry["db"].lectures.find_one_and_update(
                    base_filter,
                    {"$set": {"status": "processing", "updated_at": now_ist_str()}},
                    sort=[("ts", 1)],
                    return_document=True
                )
                if doc:
                    ram_cache.invalidate_prefix("cv_summary")
                    return _clean_doc(doc)
            except Exception:
                continue
        return None

    def finish_lecture_item(self, lecture_id, ok=True, **kwargs):
        lid = str(lecture_id or "").strip()
        shard = self._find_lecture_shard(lid)
        if not shard:
            return False
        upd = {
            "status": "completed" if ok else "failed",
            "error_message": "" if ok else str(kwargs.get("error_message") or "Upload failed")[:220],
            "updated_at": now_ist_str()
        }
        str_fields = (
            "yt_video_id", "drive_pdf1_id", "drive_pdf2_id", "drive_thumb_id",
            "tg_video_msg_id", "tg_pdf1_msg_id", "tg_pdf2_msg_id",
            "tg_channel_used", "tg_topic_used",
            "master_video_msg_id", "master_pdf1_msg_id", "master_pdf2_msg_id",
            "yt_status", "tg_status", "yt_error", "tg_error"
        )
        for f in str_fields:
            if kwargs.get(f) is not None and str(kwargs.get(f)).strip() != "":
                upd[f] = str(kwargs[f]).strip()
        if kwargs.get("drive_thumb_id"):
            upd["drive_thumb_url"] = drive_image_url(kwargs["drive_thumb_id"])
        if "next_retry_ts" in kwargs:
            upd["next_retry_ts"] = int(kwargs["next_retry_ts"] or 0)
        if "retry_count" in kwargs:
            upd["retry_count"] = int(kwargs["retry_count"] or 0)

        shard["db"].lectures.update_one({"lecture_id": lid}, {"$set": upd})
        ram_cache.invalidate_prefix("cv_")
        return True

    def _enrich_lecture_for_portal(self, doc, course_doc, cfg):
        c = _clean_doc(doc)
        c["playback_mode"] = (course_doc or {}).get("playback_mode", "vault_first")
        c["thumbnail"] = c.get("drive_thumb_url") or c.get("source_thumb") or ""
        c["drive_pdf1_url"] = f"https://drive.google.com/file/d/{c['drive_pdf1_id']}/preview" if c.get("drive_pdf1_id") else ""
        c["drive_pdf2_url"] = f"https://drive.google.com/file/d/{c['drive_pdf2_id']}/preview" if c.get("drive_pdf2_id") else ""
        c["portal_tg_fallback"] = bool(cfg.get("portal_tg_fallback", True))
        c["tg_invite_link"] = (course_doc or {}).get("tg_invite_link") or ""
        ch_id = str(c.get("tg_channel_used") or (course_doc or {}).get("tg_channel_id") or "")
        msg_id = str(c.get("tg_video_msg_id") or "")
        if ch_id.startswith("-100") and msg_id.isdigit():
            c["tg_watch_url"] = f"https://t.me/c/{ch_id[4:]}/{msg_id}"
        else:
            c["tg_watch_url"] = c["tg_invite_link"]
        return c

    def get_topic_lectures(self, course_id, subject_id, topic_id):
        cid, sid, tid = str(course_id), str(subject_id), str(topic_id)
        key = f"cv_lectures:{cid}:{sid}:{tid}"
        cached = ram_cache.get(key)
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        course_doc = primary["db"].courses.find_one({"course_id": cid}) if primary else {}
        cfg = self.get_admin_settings()
        merged = []
        for entry in self.dbs:
            try:
                for d in entry["db"].lectures.find({"course_id": cid, "subject_id": sid, "topic_id": tid}).sort([("seq_no", 1), ("ts", 1)]):
                    merged.append(self._enrich_lecture_for_portal(d, course_doc, cfg))
            except Exception:
                continue
        ram_cache.set(key, merged, ttl_sec=35)
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
        primary = self.get_primary_db()
        course_doc = primary["db"].courses.find_one({"course_id": doc.get("course_id", "")}) if primary else {}
        c = self._enrich_lecture_for_portal(doc, course_doc, self.get_admin_settings())
        ram_cache.set(f"cv_lec:{lid}", c, ttl_sec=45)
        return c

    def manual_override_lecture(self, lecture_id, **kwargs):
        lid = str(lecture_id or "").strip()
        shard = self._find_lecture_shard(lid)
        if not shard:
            return False
        upd = {"updated_at": now_ist_str()}
        if str(kwargs.get("yt_video_id") or "").strip():
            upd["yt_video_id"] = str(kwargs["yt_video_id"]).strip()
            upd["yt_status"] = "completed"
            upd["status"] = "completed"
            upd["error_message"] = ""
        for k in ("drive_pdf1_id", "drive_pdf2_id", "tg_video_msg_id", "tg_pdf1_msg_id", "tg_pdf2_msg_id"):
            if str(kwargs.get(k) or "").strip():
                upd[k] = str(kwargs[k]).strip()
                if k == "tg_video_msg_id":
                    upd["tg_status"] = "completed"
        if str(kwargs.get("drive_thumb_id") or "").strip():
            tid = str(kwargs["drive_thumb_id"]).strip()
            upd["drive_thumb_id"] = tid
            upd["drive_thumb_url"] = drive_image_url(tid)
        shard["db"].lectures.update_one({"lecture_id": lid}, {"$set": upd})
        ram_cache.invalidate_prefix("cv_")
        return True

    # ---------------- 1-CLICK CHANNEL RESTORE JOBS ----------------
    def create_restore_job(self, course_id, target_channel_id):
        primary = self.get_primary_db()
        cid = str(course_id or "").strip()
        tgt = str(target_channel_id or "").strip()
        if not primary or not cid or not tgt:
            return False, "Course ID aur Target Channel ID zaroori hai."
        job = {
            "job_id": f"rst_{cid}_{int(time.time())}",
            "course_id": cid,
            "target_channel_id": tgt,
            "status": "pending",
            "done": 0,
            "total": 0,
            "message": "Queued for Termux Restore Worker...",
            "created_at": now_ist_str(),
            "ts": int(time.time())
        }
        primary["db"].restore_jobs.insert_one(job)
        primary["db"].courses.update_one({"course_id": cid}, {"$set": {"tg_channel_id": tgt}})
        ram_cache.invalidate_prefix("cv_")
        return True, f"Restore job queued for Batch #{cid} -> {tgt}"

    def list_restore_jobs(self):
        primary = self.get_primary_db()
        if not primary:
            return []
        return [_clean_doc(d) for d in primary["db"].restore_jobs.find().sort("ts", DESCENDING).limit(20)]

    # ---------------- JSON FULL BACKUP EXPORT ----------------
    def export_full_backup_json(self):
        primary = self.get_primary_db()
        data = {
            "exported_at": now_ist_str(),
            "settings": self.get_admin_settings(),
            "courses": [],
            "subjects": [],
            "topics": [],
            "lectures": []
        }
        if primary:
            data["courses"] = [_clean_doc(x) for x in primary["db"].courses.find()]
            data["subjects"] = [_clean_doc(x) for x in primary["db"].subjects.find()]
            data["topics"] = [_clean_doc(x) for x in primary["db"].topics.find()]
        for entry in self.dbs:
            try:
                data["lectures"].extend([_clean_doc(x) for x in entry["db"].lectures.find()])
            except Exception:
                continue
        return data

    # ---------------- WORKER HEARTBEAT & DIRECT SUMMARY ----------------
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

    def get_direct_summary(self):
        cached = ram_cache.get("cv_summary:main")
        if cached is not None:
            return cached
        primary = self.get_primary_db()
        total_courses = total_subjects = total_topics = courses_thumbs_ready = subjects_logos_ready = 0
        active_restores = 0
        if primary:
            try:
                total_courses = primary["db"].courses.count_documents({})
                courses_thumbs_ready = primary["db"].courses.count_documents({"drive_thumb_id": {"$ne": ""}})
                total_subjects = primary["db"].subjects.count_documents({})
                subjects_logos_ready = primary["db"].subjects.count_documents({"drive_logo_id": {"$ne": ""}})
                total_topics = primary["db"].topics.count_documents({})
                active_restores = primary["db"].restore_jobs.count_documents({"status": {"$in": ["pending", "running"]}})
            except Exception:
                pass

        total_lectures = yt_ready = pdf_ready = thumbs_ready = pending = failed = processing = 0
        yt_c = yt_p = yt_f = tg_c = tg_p = tg_f = tg_pdf_ready = 0
        per_shard = []
        any_space = False

        for entry in self.dbs:
            db = entry["db"]
            try:
                l_cnt = db.lectures.count_documents({})
                y_cnt = db.lectures.count_documents({"yt_video_id": {"$ne": ""}})
                yf_cnt = db.lectures.count_documents({"yt_video_id": {"$in": ["", None]}, "$or": [{"yt_status": "failed"}, {"status": "failed"}]})
                yp_cnt = max(0, l_cnt - y_cnt - yf_cnt)

                tgc_cnt = db.lectures.count_documents({"tg_video_msg_id": {"$nin": ["", None]}})
                tgf_cnt = db.lectures.count_documents({"tg_video_msg_id": {"$in": ["", None]}, "tg_status": "failed"})
                tgp_cnt = max(0, l_cnt - tgc_cnt - tgf_cnt)
                tgpdf_cnt = db.lectures.count_documents({"$or": [{"tg_pdf1_msg_id": {"$nin": ["", None]}}, {"tg_pdf2_msg_id": {"$nin": ["", None]}}]})

                p_cnt = db.lectures.count_documents({"$or": [{"drive_pdf1_id": {"$ne": ""}}, {"drive_pdf2_id": {"$ne": ""}}]})
                t_cnt = db.lectures.count_documents({"drive_thumb_id": {"$ne": ""}})
                pen_cnt = db.lectures.count_documents({"status": "pending"})
                fail_cnt = db.lectures.count_documents({"status": "failed"})
                proc_cnt = db.lectures.count_documents({"status": "processing"})
                mb = self.get_db_size_mb(entry)
                is_full = mb >= config.MAX_COURSE_DB_SIZE_MB
                if not is_full:
                    any_space = True

                total_lectures += l_cnt
                yt_ready += y_cnt
                yt_c += y_cnt; yt_p += yp_cnt; yt_f += yf_cnt
                tg_c += tgc_cnt; tg_p += tgp_cnt; tg_f += tgf_cnt
                tg_pdf_ready += tgpdf_cnt
                pdf_ready += p_cnt
                thumbs_ready += t_cnt
                pending += pen_cnt
                failed += fail_cnt
                processing += proc_cnt

                per_shard.append({
                    "label": entry["label"],
                    "lectures": l_cnt,
                    "yt_ready": y_cnt,
                    "tg_ready": tgc_cnt,
                    "size_mb": mb,
                    "max_mb": config.MAX_COURSE_DB_SIZE_MB,
                    "is_full": is_full
                })
            except Exception:
                per_shard.append({"label": entry["label"], "error": True})

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
            "yt_ready": yt_ready,
            "yt_completed": yt_c,
            "yt_pending": yt_p,
            "yt_failed": yt_f,
            "tg_completed": tg_c,
            "tg_pending": tg_p,
            "tg_failed": tg_f,
            "tg_pdf_ready": tg_pdf_ready,
            "pdf_ready": pdf_ready,
            "thumbs_ready": thumbs_ready,
            "pending_queue": pending,
            "processing_now": processing,
            "failed_queue": failed,
            "active_restore_jobs": active_restores,
            "per_shard": per_shard,
            "worker": self.get_worker_heartbeat(),
            "ram_cache": ram_cache.stats(),
            "updated_at": now_ist_str()
        }
        ram_cache.set("cv_summary:main", summary, ttl_sec=15)
        return summary


course_vault_db = CourseVaultDB()

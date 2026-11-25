import base64
import json
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import config
from course_vault_db import course_vault_db

IST = timezone(timedelta(hours=5, minutes=30))
APPX_AES_KEY = b"638udh3829162018"

RWA_HEADERS = {
    "Client-Service": "Appx",
    "Auth-Key": "appxapi",
    "source": "website",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"
}


def _now_ist():
    return datetime.now(IST)


def _now_ist_str():
    return _now_ist().strftime("%d-%m-%Y %I:%M:%S %p")


def clean_jwt_token(raw_token):
    t = str(raw_token or "").strip().strip('"').strip("'")
    t = re.sub(r"^(Authorization:\s*|Bearer\s+)", "", t, flags=re.IGNORECASE).strip()
    return t


def _decode_jwt_payload(jwt_str):
    try:
        parts = jwt_str.split(".")
        if len(parts) < 2:
            return {}
        b64 = parts[1].replace("-", "+").replace("_", "/")
        b64 += "=" * (-len(b64) % 4)
        return json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def extract_uid_from_jwt(jwt_str):
    tok = clean_jwt_token(jwt_str)
    payload = _decode_jwt_payload(tok)
    if not isinstance(payload, dict):
        return ""
    for k in ("id", "userid", "user_id"):
        if payload.get(k):
            return str(payload[k]).strip()
    if payload.get("session"):
        nested = _decode_jwt_payload(str(payload["session"]))
        for k in ("id", "userid", "user_id"):
            if nested.get(k):
                return str(nested[k]).strip()
    return ""


def decrypt_appx_str(enc_str):
    if not enc_str or not isinstance(enc_str, str):
        return ""
    s = enc_str.strip()
    if s.startswith("http"):
        return s.replace("\\/", "/")
    if ":" not in s:
        return s.replace("\\/", "/")
    try:
        cipher_b64, iv_b64 = s.split(":", 1)
        ct = base64.b64decode(cipher_b64.replace("\\/", "/"))
        iv = base64.b64decode(iv_b64)
        cipher = Cipher(algorithms.AES(APPX_AES_KEY), modes.CBC(iv))
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        cleaned = re.sub(r"[\x00-\x1F\x7F]", "", plain.decode("utf-8", errors="ignore")).strip()
        return cleaned.replace("\\/", "/")
    except Exception:
        return ""


def resolve_pdf_url(enc_pdf, signed_pdf=""):
    dec = decrypt_appx_str(enc_pdf)
    if dec.startswith("http"):
        return dec
    if signed_pdf and str(signed_pdf).startswith("http"):
        return str(signed_pdf).replace("\\/", "/").strip()
    return dec or ""


def pick_best_video_url(item):
    candidates = []
    for key in ("encrypted_links", "livestream_links", "download_links"):
        arr = item.get(key) or []
        if isinstance(arr, list):
            for entry in arr:
                if not isinstance(entry, dict):
                    continue
                u = decrypt_appx_str(str(entry.get("path") or ""))
                if u.startswith("http") and "playlist_eof.m3u8" not in u:
                    qual = str(entry.get("quality") or "").lower()
                    score = 0
                    if "720" in qual or "/720p/" in u:
                        score += 50
                    elif "480" in qual or "/480p/" in u:
                        score += 35
                    elif "1080" in qual:
                        score += 40
                    if ".m3u8" in u:
                        score += 20
                    candidates.append((score, u))

    dec_file = decrypt_appx_str(str(item.get("file_link") or ""))
    if dec_file:
        if dec_file.startswith("http") and "playlist_eof.m3u8" not in dec_file:
            candidates.append((25, dec_file))
        elif not dec_file.startswith("http") and 10 <= len(dec_file) <= 15:
            candidates.append((10, dec_file))

    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


class CourseMetadataScanner:
    def __init__(self):
        self._lock = threading.RLock()
        self._thread = None
        self._stop_flag = False
        self.alert_callback = None
        self.state = self._make_idle_state()

    def _make_idle_state(self):
        return {
            "running": False,
            "status": "IDLE",
            "mode": "none",
            "started_at": "",
            "finished_at": "",
            "current_phase": "Token verify karke course select karein",
            "current_course": "",
            "current_subject": "",
            "courses_total": 0,
            "courses_done": 0,
            "subjects_found": 0,
            "topics_found": 0,
            "lectures_found": 0,
            "new_lectures_queued": 0,
            "existing_skipped": 0,
            "errors": 0,
            "progress_percent": 0,
            "logs": []
        }

    def _log(self, msg):
        line = f"[{_now_ist().strftime('%I:%M:%S %p')}] {msg}"
        with self._lock:
            self.state["logs"].insert(0, line)
            self.state["logs"] = self.state["logs"][:50]
        print(f"🎓 [CourseScanner] {msg}")

    def _notify(self, text):
        if callable(self.alert_callback):
            try:
                self.alert_callback(text)
            except Exception:
                pass

    def get_status(self):
        with self._lock:
            return dict(self.state)

    def _fetch_rwa(self, endpoint, token, uid):
        tok = clean_jwt_token(token)
        url = f"{config.RWA_API_BASE}{endpoint}"
        headers = {**RWA_HEADERS, "Authorization": tok, "User-ID": str(uid)}
        last_err = ""
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.ok:
                return r.json()
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = f"DirectErr: {str(e)[:50]}"

        try:
            base_enc = quote(config.RWA_API_BASE + "/", safe="")
            cookie_str = f"base_url={base_enc}; Authorization={tok}; User-ID={uid}"
            wurl = (
                f"{config.WORKER_PROXY_URL}{quote(url, safe='')}"
                f"&cookie={quote(cookie_str, safe='')}&token={quote(tok, safe='')}"
                f"&uid={quote(str(uid), safe='')}&base_url={base_enc}"
            )
            r = requests.get(wurl, timeout=18)
            if r.ok:
                return r.json()
            self._log(f"⚠️ Fetch failed {endpoint} ({last_err} | Proxy HTTP {r.status_code})")
        except Exception as e:
            self._log(f"⚠️ Fetch failed {endpoint} ({last_err} | ProxyErr: {str(e)[:50]})")
        return None

    def _extract_courses_list(self, payload):
        if not isinstance(payload, dict):
            return []
        for key in ("data", "courses", "batches"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for sub_key in ("courses", "batches", "items", "data"):
                    if isinstance(val.get(sub_key), list):
                        return val[sub_key]
        return []

    def verify_token_and_fetch_courses(self, raw_token, explicit_uid=""):
        tok = clean_jwt_token(raw_token)
        if not tok or "." not in tok:
            return {"ok": False, "message": "Invalid JWT token format!"}

        uid = str(explicit_uid or "").strip() or extract_uid_from_jwt(tok)
        if not uid:
            return {"ok": False, "message": "Token se User-ID nahi nikla. Sahi JWT token paste karein."}

        # 1. Verify token with user profile endpoint
        user_name = f"User #{uid}"
        prof = self._fetch_rwa(f"/get/get_user_dt?userid={uid}", tok, uid)
        token_verified = False
        if isinstance(prof, dict) and str(prof.get("status")) == "200":
            pdata = prof.get("data")
            if isinstance(pdata, list) and pdata and isinstance(pdata[0], dict):
                user_name = str(pdata[0].get("name") or user_name).strip()
                token_verified = True
            elif isinstance(pdata, dict) and pdata:
                user_name = str(pdata.get("name") or user_name).strip()
                token_verified = True

        # 2. Fetch purchased courses
        courses = []
        seen = set()
        last_msg = ""
        for ep in (f"/get/mycourseweb?userid={uid}", f"/get/mycourse?userid={uid}"):
            j = self._fetch_rwa(ep, tok, uid)
            if isinstance(j, dict):
                if str(j.get("status")) == "200":
                    token_verified = True
                if j.get("message") or j.get("msg"):
                    last_msg = str(j.get("message") or j.get("msg"))
            arr = self._extract_courses_list(j)
            for c in arr:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get("id") or c.get("course_id") or "").strip()
                if cid and cid not in seen:
                    seen.add(cid)
                    courses.append({
                        "id": cid,
                        "course_id": cid,
                        "course_name": str(c.get("course_name") or f"Batch #{cid}").strip(),
                        "exam_logo": str(c.get("exam_logo") or c.get("course_thumbnail") or "").replace("\\/", "/").strip(),
                        "test_series_id": str(c.get("test_series_id") or "")
                    })
            if courses:
                break

        if not token_verified and not courses:
            return {
                "ok": False,
                "user_id": uid,
                "message": f"Token invalid ya expire ho gaya hai! {last_msg}".strip()
            }

        return {
            "ok": True,
            "user_id": uid,
            "user_name": user_name,
            "courses": courses,
            "message": f"Token Verified ({user_name})! {len(courses)} purchased course(s) mile."
        }

    def start_scan(self, mode="manual", target_course_id="", override_token=None):
        with self._lock:
            if self.state["running"]:
                return False, "Course metadata scan pehle se chal raha hai!"
            if not course_vault_db.has_available_storage():
                self.state["status"] = "PAUSED_STORAGE_FULL"
                return False, f"All Course DBs reached {config.MAX_COURSE_DB_SIZE_MB} MB limit!"

            if override_token and override_token.get("token"):
                tok = clean_jwt_token(override_token["token"])
                uid = str(override_token.get("user_id") or "").strip() or extract_uid_from_jwt(tok)
                tokens = [{"user_id": uid, "token": tok, "source": "selected"}]
            else:
                tokens = course_vault_db.get_scanner_tokens()

            if not tokens:
                return False, "Koi Scanner Token add nahi hai! Pehle Admin Panel mein RWA Token verify karein."

            target_cid = str(target_course_id or "").strip()
            self._stop_flag = False
            self.state = self._make_idle_state()
            self.state["running"] = True
            self.state["status"] = "RUNNING"
            self.state["mode"] = mode
            self.state["started_at"] = _now_ist_str()
            self.state["current_phase"] = f"Starting scan for Batch #{target_cid}..." if target_cid else "Fetching Purchased Batches..."

            self._thread = threading.Thread(
                target=self._worker,
                args=(mode, tokens, target_cid),
                daemon=True
            )
            self._thread.start()
            msg = f"Batch #{target_cid} scan started!" if target_cid else f"Course {mode} metadata scan started!"
            return True, msg

    def stop_scan(self):
        with self._lock:
            if not self.state["running"]:
                return False, "Koi scan abhi nahi chal raha."
            self._stop_flag = True
            self.state["current_phase"] = "Stopping cleanly..."
            return True, "Stop signal sent."

    def _should_stop(self, mode):
        if self._stop_flag:
            return True
        if mode == "nightly" and _now_ist().hour != config.NIGHTLY_SCAN_HOUR_IST:
            return True
        return False

    def _worker(self, mode, tokens, target_course_id=""):
        storage_full_hit = False
        try:
            self._log(f"Started {mode.upper()} Scan (target={target_course_id or 'ALL'}) with {len(tokens)} token(s)...")
            courses = []
            seen_cids = set()

            for tk in tokens:
                if self._should_stop(mode):
                    break
                tok = clean_jwt_token(tk.get("token"))
                uid = str(tk.get("user_id") or "").strip() or extract_uid_from_jwt(tok)
                if not tok or not uid:
                    continue

                for ep in (f"/get/mycourseweb?userid={uid}", f"/get/mycourse?userid={uid}"):
                    j = self._fetch_rwa(ep, tok, uid)
                    arr = self._extract_courses_list(j)
                    self._log(f"UID {uid} {ep} -> {len(arr)} course(s)")
                    for c in arr:
                        if not isinstance(c, dict):
                            continue
                        cid = str(c.get("id") or c.get("course_id") or "").strip()
                        if not cid:
                            continue
                        if target_course_id and cid != target_course_id:
                            continue
                        if cid not in seen_cids:
                            seen_cids.add(cid)
                            courses.append((c, {"user_id": uid, "token": tok}))
                            course_vault_db.upsert_course(c)
                    if arr:
                        break

            with self._lock:
                self.state["courses_total"] = len(courses)
            self._log(f"Selected {len(courses)} batch(es) to scan.")

            if not courses:
                with self._lock:
                    self.state["running"] = False
                    self.state["finished_at"] = _now_ist_str()
                    self.state["status"] = "COMPLETED"
                    self.state["progress_percent"] = 100
                    self.state["current_phase"] = "0 batches found — Token verify karein."
                return

            for c_idx, (c_obj, tk) in enumerate(courses, start=1):
                if self._should_stop(mode) or storage_full_hit:
                    break
                cid = str(c_obj.get("id") or c_obj.get("course_id")).strip()
                cname = str(c_obj.get("course_name") or f"Batch #{cid}").strip()
                uid, tok = tk["user_id"], tk["token"]

                with self._lock:
                    self.state["current_phase"] = f"Scanning Batch {c_idx}/{len(courses)}: {cname}"
                    self.state["current_course"] = f"{cname} (#{cid})"
                    self.state["courses_done"] = c_idx - 1
                    self.state["progress_percent"] = int(((c_idx - 1) / max(1, len(courses))) * 100)

                s_json = self._fetch_rwa(f"/get/allsubjectfrmlivecourseclass?courseid={cid}&start=-1", tok, uid)
                subjects = (s_json.get("data") if isinstance(s_json, dict) else None) or []
                if not isinstance(subjects, list):
                    continue
                self._log(f"Batch #{cid} ({cname}) -> {len(subjects)} subject(s)")

                for sub in subjects:
                    if self._should_stop(mode) or storage_full_hit:
                        break
                    sid = str(sub.get("subjectid") or sub.get("subject_id") or "").strip()
                    sname = str(sub.get("subject_name") or sub.get("subjectname") or f"Subject #{sid}").strip()
                    if not sid:
                        continue
                    course_vault_db.upsert_subject(cid, sub)
                    with self._lock:
                        self.state["subjects_found"] += 1
                        self.state["current_subject"] = sname

                    t_json = self._fetch_rwa(
                        f"/get/alltopicfrmlivecourseclass?courseid={cid}&subjectid={sid}&start=-1", tok, uid
                    )
                    topics = (t_json.get("data") if isinstance(t_json, dict) else None) or []
                    if not isinstance(topics, list):
                        continue

                    for top in topics:
                        if self._should_stop(mode) or storage_full_hit:
                            break
                        tid = str(top.get("topicid") or top.get("topic_id") or "").strip()
                        tname = str(top.get("topic_name") or top.get("topicname") or f"Topic #{tid}").strip()
                        if not tid:
                            continue
                        course_vault_db.upsert_topic(cid, sid, top)
                        with self._lock:
                            self.state["topics_found"] += 1

                        l_json = self._fetch_rwa(
                            f"/get/livecourseclassbycoursesubtopconceptapiv3?courseid={cid}&subjectid={sid}&topicid={tid}&conceptid=1&start=0",
                            tok, uid
                        )
                        lectures = (l_json.get("data") if isinstance(l_json, dict) else None) or []
                        if not isinstance(lectures, list):
                            continue

                        for lec in lectures:
                            if self._should_stop(mode):
                                break
                            lid = str(lec.get("id") or "").strip()
                            if not lid:
                                continue

                            vid_url = pick_best_video_url(lec)
                            pdf1 = resolve_pdf_url(lec.get("pdf_link") or lec.get("ypdf_link"), lec.get("ypdf_link2"))
                            pdf2 = resolve_pdf_url(lec.get("pdf_link2"), lec.get("ypdf_link2"))

                            if not vid_url and not course_vault_db._find_lecture_shard(lid):
                                det = self._fetch_rwa(
                                    f"/get/fetchVideoDetailsById?course_id={cid}&video_id={lid}&ytflag=0&folder_wise_course=0&lc_app_api_url=",
                                    tok, uid
                                )
                                d_obj = (det.get("data") if isinstance(det, dict) else None) or {}
                                if isinstance(d_obj, dict):
                                    vid_url = pick_best_video_url(d_obj) or vid_url
                                    pdf1 = pdf1 or resolve_pdf_url(d_obj.get("pdf_link") or d_obj.get("ypdf_link"), d_obj.get("ypdf_link2"))
                                    pdf2 = pdf2 or resolve_pdf_url(d_obj.get("pdf_link2"), d_obj.get("ypdf_link2"))
                                time.sleep(0.12)

                            res = course_vault_db.upsert_lecture_metadata(
                                cid, cname, sid, sname, tid, tname,
                                {
                                    **lec,
                                    "source_video_url": vid_url,
                                    "source_pdf1_url": pdf1,
                                    "source_pdf2_url": pdf2
                                }
                            )
                            if res.get("storage_full"):
                                storage_full_hit = True
                                break
                            if res.get("ok"):
                                with self._lock:
                                    self.state["lectures_found"] += 1
                                    if res.get("is_new"):
                                        self.state["new_lectures_queued"] += 1
                                    else:
                                        self.state["existing_skipped"] += 1

                        time.sleep(0.12)

                with self._lock:
                    self.state["courses_done"] = c_idx
                    self.state["progress_percent"] = int((c_idx / max(1, len(courses))) * 100)

            with self._lock:
                self.state["running"] = False
                self.state["finished_at"] = _now_ist_str()
                if storage_full_hit:
                    self.state["status"] = "PAUSED_STORAGE_FULL"
                    self.state["current_phase"] = f"Paused: All Course DBs hit {config.MAX_COURSE_DB_SIZE_MB} MB limit!"
                    self._log("🛑 Storage Full (450 MB). Add new COURSE_MONGO_URI_N.")
                elif self._stop_flag:
                    self.state["status"] = "STOPPED"
                    self.state["current_phase"] = "Stopped by Admin"
                    self._log("⏹ Scan stopped by Admin.")
                else:
                    self.state["status"] = "COMPLETED"
                    self.state["progress_percent"] = 100
                    nq = self.state["new_lectures_queued"]
                    self.state["current_phase"] = f"Done! {nq} new class(es) queued for Termux upload."
                    self._log(f"✅ Complete: {nq} new queued, {self.state['existing_skipped']} skipped.")
                    if nq > 0:
                        self._notify(
                            f"🎓 <b>Course Vault Scan Complete</b>\n"
                            f"• Batches: <b>{len(courses)}</b>\n"
                            f"• New Classes Queued for Termux: <b>{nq}</b>\n"
                            f"• Skipped: <b>{self.state['existing_skipped']}</b>"
                        )
        except Exception as e:
            with self._lock:
                self.state["running"] = False
                self.state["status"] = "STOPPED"
                self.state["finished_at"] = _now_ist_str()
                self.state["current_phase"] = f"Error: {str(e)[:120]}"
                self.state["errors"] += 1
            self._log(f"❌ Scanner error: {e}")


course_scanner = CourseMetadataScanner()

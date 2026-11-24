import base64
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
    "Device-Type": "",
    "is-safari": "0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"
}


def _now_ist():
    return datetime.now(IST)


def _now_ist_str():
    return _now_ist().strftime("%d-%m-%Y %I:%M:%S %p")


def _extract_uid_from_jwt(token):
    try:
        parts = str(token or "").strip().split(".")
        if len(parts) < 2:
            return ""
        b64 = parts[1].replace("-", "+").replace("_", "/")
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        import json
        payload = json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
        for k in ("id", "userid", "user_id"):
            if payload.get(k):
                return str(payload[k])
    except Exception:
        pass
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


def _extract_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "courses", "subjects", "topics", "lectures", "items"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


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
            "current_phase": "Waiting for 11:00 PM IST or Admin trigger",
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
            self.state["logs"] = self.state["logs"][:35]
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

    def start_scan(self, mode="manual"):
        with self._lock:
            if self.state["running"]:
                return False, "Course metadata scan pehle se chal raha hai!"
            if not course_vault_db.has_available_storage():
                self.state["status"] = "PAUSED_STORAGE_FULL"
                return False, f"All Course DBs reached {config.MAX_COURSE_DB_SIZE_MB} MB limit!"

            tokens = course_vault_db.get_scanner_tokens()
            if not tokens:
                return False, "Koi Scanner Token add nahi hai! Pehle Admin Panel mein RWA Token add karein."

            self._stop_flag = False
            self.state = self._make_idle_state()
            self.state["running"] = True
            self.state["status"] = "RUNNING"
            self.state["mode"] = mode
            self.state["started_at"] = _now_ist_str()
            self.state["current_phase"] = "Fetching Purchased Batches..."

            self._thread = threading.Thread(target=self._worker, args=(mode, tokens), daemon=True)
            self._thread.start()
            return True, f"Course {mode} metadata scan started!"

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

    def _fetch_rwa(self, endpoint, token, uid):
        clean_uid = str(uid or "").strip() or _extract_uid_from_jwt(token) or "4756316"
        clean_tok = str(token or "").strip()
        url = f"{config.RWA_API_BASE.rstrip('/')}{endpoint}"
        headers = {**RWA_HEADERS, "Authorization": clean_tok, "User-ID": clean_uid}

        for attempt in range(2):
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.ok:
                    return r.json()
            except Exception:
                pass
            time.sleep(0.25 * (attempt + 1))

        if config.WORKER_PROXY_URL:
            try:
                base_enc = quote(config.RWA_API_BASE.rstrip("/") + "/", safe="")
                cookie_str = f"base_url={base_enc}; Authorization={clean_tok}; User-ID={clean_uid}"
                wurl = (
                    f"{config.WORKER_PROXY_URL}{quote(url, safe='')}"
                    f"&cookie={quote(cookie_str, safe='')}&token={quote(clean_tok, safe='')}"
                    f"&uid={quote(clean_uid, safe='')}&base_url={base_enc}"
                )
                r = requests.get(wurl, timeout=18)
                if r.ok:
                    return r.json()
            except Exception:
                pass
        return None

    def _worker(self, mode, tokens):
        storage_full_hit = False
        try:
            self._log(f"Started {mode.upper()} Course Scan using {len(tokens)} token(s)...")

            courses = []
            seen_cids = set()
            for tk in tokens:
                if self._should_stop(mode):
                    break
                uid = str(tk.get("user_id") or "").strip() or _extract_uid_from_jwt(tk.get("token"))
                tok = str(tk.get("token") or "").strip()
                for ep in (f"/get/mycourseweb?userid={uid}", f"/get/mycourse?userid={uid}"):
                    j = self._fetch_rwa(ep, tok, uid)
                    arr = _extract_list(j)
                    for c in arr:
                        if not isinstance(c, dict):
                            continue
                        cid = str(c.get("id") or c.get("course_id") or "").strip()
                        if cid and cid not in seen_cids:
                            seen_cids.add(cid)
                            courses.append((c, {**tk, "user_id": uid, "token": tok}))
                            course_vault_db.upsert_course(c)

            with self._lock:
                self.state["courses_total"] = len(courses)
            self._log(f"Found {len(courses)} unique Batch(es). Scanning subjects, topics & lectures...")

            for c_idx, (c_obj, tk) in enumerate(courses, start=1):
                if self._should_stop(mode) or storage_full_hit:
                    break
                cid = str(c_obj.get("id") or c_obj.get("course_id")).strip()
                cname = str(c_obj.get("course_name") or f"Batch #{cid}").strip()
                uid, tok = tk["user_id"], tk["token"]

                with self._lock:
                    self.state["current_phase"] = f"Scanning Batch {c_idx}/{len(courses)}"
                    self.state["current_course"] = f"{cname} (#{cid})"
                    self.state["courses_done"] = c_idx - 1
                    self.state["progress_percent"] = int(((c_idx - 1) / max(1, len(courses))) * 100)

                s_json = self._fetch_rwa(f"/get/allsubjectfrmlivecourseclass?courseid={cid}&start=-1", tok, uid)
                subjects = _extract_list(s_json)

                for sub in subjects:
                    if self._should_stop(mode) or storage_full_hit:
                        break
                    if not isinstance(sub, dict):
                        continue
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
                    topics = _extract_list(t_json)

                    for top in topics:
                        if self._should_stop(mode) or storage_full_hit:
                            break
                        if not isinstance(top, dict):
                            continue
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
                        lectures = _extract_list(l_json)

                        for lec in lectures:
                            if self._should_stop(mode):
                                break
                            if not isinstance(lec, dict):
                                continue
                            lid = str(lec.get("id") or lec.get("lecture_id") or "").strip()
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
                                time.sleep(0.15)

                            res = course_vault_db.upsert_lecture_metadata(
                                cid, cname, sid, sname, tid, tname,
                                {
                                    **lec,
                                    "id": lid,
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

                        time.sleep(0.15)

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
                    self._notify("🚨 <b>COURSE VAULT 450 MB FULL!</b>\nNaya <code>COURSE_MONGO_URI_N</code> add karein.")
                elif self._stop_flag:
                    self.state["status"] = "STOPPED"
                    self.state["current_phase"] = "Stopped by Admin"
                    self._log("⏹ Scan stopped by Admin.")
                else:
                    self.state["status"] = "COMPLETED"
                    self.state["progress_percent"] = 100
                    nq = self.state["new_lectures_queued"]
                    self.state["current_phase"] = f"Done! {nq} new class(es) queued for Termux upload."
                    self._log(f"✅ Course Scan Complete: {nq} new classes queued, {self.state['existing_skipped']} existing skipped.")
                    if nq > 0:
                        self._notify(
                            f"🎓 <b>Course Vault {mode.upper()} Scan Complete</b>\n"
                            f"• Batches: <b>{len(courses)}</b>\n"
                            f"• New Classes Queued for Termux: <b>{nq}</b>\n"
                            f"• Already Saved (Skipped): <b>{self.state['existing_skipped']}</b>"
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

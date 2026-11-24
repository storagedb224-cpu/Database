import os
import re


def _collect_dynamic_mongo_uris(single_names, indexed_prefixes, list_env_name):
    uris = []
    seen = set()

    def _add(raw_val):
        if not raw_val:
            return
        for part in re.split(r"[\n,]+", str(raw_val)):
            u = part.strip().strip('"').strip("'")
            if u and u not in seen and (u.startswith("mongodb://") or u.startswith("mongodb+srv://")):
                seen.add(u)
                uris.append(u)

    if list_env_name:
        _add(os.getenv(list_env_name, ""))

    indexed_matches = []
    for k, v in os.environ.items():
        if not v or not str(v).strip():
            continue
        for pref in indexed_prefixes:
            m = re.match(rf"^{re.escape(pref)}(\d+)$", k.strip(), re.IGNORECASE)
            if m:
                indexed_matches.append((int(m.group(1)), k, v))
                break

    indexed_matches.sort(key=lambda item: item[0])
    for _, _, v in indexed_matches:
        _add(v)

    for sk in single_names:
        _add(os.getenv(sk, ""))

    return uris


# =========================================================
# DEDICATED COURSE VAULT MONGODB CLUSTER (UNLIMITED URIS)
# Variables: COURSE_MONGO_URI_1, COURSE_MONGO_URI_2 ... N
# =========================================================
COURSE_DB_NAME = os.getenv("COURSE_DB_NAME", "rwa_course_vault_db").strip()
MAX_COURSE_DB_SIZE_MB = float(os.getenv("MAX_COURSE_DB_SIZE_MB", "450"))

COURSE_MONGO_URIS = _collect_dynamic_mongo_uris(
    single_names=["COURSE_MONGO_URI", "MONGO_URI"],
    indexed_prefixes=["COURSE_MONGO_URI_", "MONGO_URI_"],
    list_env_name="COURSE_MONGO_URIS"
)

# =========================================================
# ADMIN, TELEGRAM ALERTS & SECURITY
# =========================================================
ADMIN_KEY = os.getenv("COURSE_ADMIN_KEY", "RWA_COURSE_ADMIN_2026").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]

# RWA Token(s) for Metadata Scanning (Optional: can also add from Admin Panel)
# Format: userId:jwt_token (comma/newline separated for multiple accounts)
SCANNER_TOKENS_RAW = os.getenv("SCANNER_TOKENS", "").strip()

DEFAULT_ALLOWED_ORIGINS = ",".join([
    "https://rwawebportal-alt.github.io",
    "https://pdfdownloader22-netizen.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500"
])
ALLOWED_ORIGINS = [
    o.strip().strip('"').strip("'").rstrip("/").lower()
    for o in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if o.strip().strip('"').strip("'")
]

# Upstream RWA API & Worker Fallback
RWA_API_BASE = os.getenv("RWA_API_BASE", "https://rozgarapinew.teachx.in").strip()
WORKER_PROXY_URL = os.getenv("WORKER_PROXY_URL", "https://test.src22420.workers.dev/?url=").strip()

# Server & Nightly Auto-Scan Schedule (11:00 PM - 12:00 AM IST)
WAITRESS_THREADS = int(os.getenv("WAITRESS_THREADS", "16"))
NIGHTLY_SCAN_HOUR_IST = int(os.getenv("NIGHTLY_SCAN_HOUR_IST", "23"))
PORT = int(os.getenv("PORT", "10000"))

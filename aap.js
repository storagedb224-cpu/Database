// =========================================================
// RWA SKY PRO PORTAL - MASTER ENGINE + HYBRID COURSE VAULT ROUTER (app.js)
// Features: Hybrid Course Vault (YouTube Unlisted + Drive PDFs + Drive Thumbs),
// Automatic Live HLS Fallback, E2E rwaSecureFetch, 3-Way Login (OTP/Pass/Token),
// Expired Token Guard, Android Back-Button Router, Test Vault Fallback & 1-v-1 Challenge
// =========================================================

const BOT_API_BASE = "https://pdfsownlaoder.onrender.com";
// 👇 APNE NAYE RENDER COURSE VAULT SERVICE KA URL YAHAN DALEIN:
const COURSE_VAULT_API_BASE = "https://database-1wsm.onrender.com";

const API_BASE = "https://rozgarapinew.teachx.in";
const AES_KEY = CryptoJS.enc.Utf8.parse("638udh3829162018");
window.WORKER_RAW_PROXY = "https://proplayer.allswbatch22.workers.dev/proxy?url=";
const RWA_DEDICATED_WORKER = "https://test.src22420.workers.dev/?url=";

const CACHE_KEYS = {
    PAID_BATCHES: "rwa_cache_paid_batches_v5",
    FREE_BATCHES: "rwa_cache_free_batches_v5",
    PAID_TS: "rwa_cache_paid_ts_v5",
    FREE_TS: "rwa_cache_free_ts_v5"
};

const RWA_CORS_SAFE_HEADERS = {
    "Client-Service": "Appx",
    "Auth-Key": "appxapi",
    "source": "website"
};

window.ACTIVE_CHALLENGE = null;

// =====================================================
// HYBRID COURSE VAULT READ-ONLY FETCHERS (ZERO CRASH)
// =====================================================
function isCourseVaultConfigured() {
    return Boolean(COURSE_VAULT_API_BASE && !COURSE_VAULT_API_BASE.includes("your-course-vault"));
}

async function fetchCvJson(path) {
    if (!isCourseVaultConfigured()) return null;
    try {
        const ctrl = new AbortController();
        const tid = setTimeout(() => ctrl.abort(), 7000);
        const res = await fetch(`${COURSE_VAULT_API_BASE.replace(/\/$/, "")}${path}`, { signal: ctrl.signal });
        clearTimeout(tid);
        if (!res.ok) return null;
        return await res.json();
    } catch { return null; }
}

async function fetchCourseVaultCourses() {
    const j = await fetchCvJson("/api/cv/courses");
    return (j && j.status === "success" && Array.isArray(j.courses)) ? j.courses : [];
}
async function fetchCourseVaultSubjects(cid) {
    const j = await fetchCvJson(`/api/cv/subjects/${encodeURIComponent(cid)}`);
    return (j && j.status === "success" && Array.isArray(j.subjects)) ? j.subjects : [];
}
async function fetchCourseVaultTopics(cid, sid) {
    const j = await fetchCvJson(`/api/cv/topics/${encodeURIComponent(cid)}/${encodeURIComponent(sid)}`);
    return (j && j.status === "success" && Array.isArray(j.topics)) ? j.topics : [];
}
async function fetchCourseVaultLectures(cid, sid, tid) {
    const j = await fetchCvJson(`/api/cv/lectures/${encodeURIComponent(cid)}/${encodeURIComponent(sid)}/${encodeURIComponent(tid)}`);
    return (j && j.status === "success" && Array.isArray(j.lectures)) ? j.lectures : [];
}
async function fetchCourseVaultSingleLecture(lid) {
    const j = await fetchCvJson(`/api/cv/lecture/${encodeURIComponent(lid)}`);
    return (j && j.status === "success" && j.lecture) ? j.lecture : null;
}

// =====================================================
// JWT DECODER & USER PERSONAL TOKEN STORAGE
// =====================================================
function decodeJwtPayloadObject(jwtStr) {
    if (!jwtStr || typeof jwtStr !== "string") return null;
    try {
        const parts = jwtStr.trim().split(".");
        if (parts.length < 2) return null;
        const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        const jsonPayload = decodeURIComponent(atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""));
        return JSON.parse(jsonPayload);
    } catch { return null; }
}

function extractUidFromJwt(jwtStr) {
    const payload = decodeJwtPayloadObject(jwtStr);
    if (!payload) return "";
    if (payload.id || payload.userid || payload.user_id) return String(payload.id || payload.userid || payload.user_id);
    if (payload.session) {
        const nested = decodeJwtPayloadObject(payload.session);
        if (nested && (nested.id || nested.userid || nested.user_id)) return String(nested.id || nested.userid || nested.user_id);
    }
    return "";
}

function extractSessionUserFromJwt(jwtStr) {
    const outer = decodeJwtPayloadObject(jwtStr);
    if (!outer) return {};
    const inner = outer.session ? (decodeJwtPayloadObject(outer.session) || {}) : {};
    return {
        id: String(outer.id || inner.id || ""),
        userid: String(outer.id || inner.id || ""),
        name: inner.name || outer.name || "",
        email: inner.email || outer.email || ""
    };
}

function getUserSavedTokens() {
    try {
        const raw = localStorage.getItem("rwa_user_tokens_v2");
        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) return parsed.filter(t => t && t.token && !t.isAdmin);
        }
    } catch {}
    return [];
}

function getSavedUserProfile() {
    try {
        const raw = localStorage.getItem("rwa_user_profile_v2");
        if (raw) return JSON.parse(raw);
    } catch {}
    return null;
}

let USER_TOKENS = getUserSavedTokens();
let USER_PROFILE = getSavedUserProfile();
window.USER_TOKENS = USER_TOKENS;
window.USER_PROFILE = USER_PROFILE;

function syncAuthCookies(tokObj) {
    if (!tokObj || !tokObj.token) return;
    const raw = String(tokObj.token).trim();
    const uid = String(tokObj.userId || extractUidFromJwt(raw) || "").trim();
    try {
        document.cookie = `base_url=${encodeURIComponent(API_BASE + "/")}; path=/; max-age=31536000; SameSite=Lax`;
        document.cookie = `Authorization=${raw}; path=/; max-age=31536000; SameSite=Lax`;
        if (uid) document.cookie = `User-ID=${uid}; path=/; max-age=31536000; SameSite=Lax`;
    } catch {}
}

function readLocalCache(key, maxAgeMs = 15 * 60 * 1000) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (parsed && parsed.ts && (Date.now() - parsed.ts) < maxAgeMs) return parsed.data;
    } catch {}
    return null;
}

function writeLocalCache(key, data) {
    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch {}
}

function renderSkeletonCards(gridEl, count = 6) {
    if (!gridEl) return;
    let html = "";
    for (let i = 0; i < count; i++) {
        html += `<div class="skeleton-card space-y-3"><div class="skel-line h-36 rounded-2xl"></div><div class="skel-line w-1/3"></div><div class="skel-line w-4/5 h-5"></div><div class="skel-line w-full h-9 rounded-xl"></div></div>`;
    }
    gridEl.innerHTML = html;
}

// =====================================================
// E2E ENCRYPTED CLOUD TOKENS FETCH
// =====================================================
async function fetchTokensFromDB() {
    if (typeof window.rwaSecureFetch !== "function") return [];
    try {
        const res = await window.rwaSecureFetch(`${BOT_API_BASE}/api/get_tokens`);
        const json = res.data || {};
        if (json.status === "success" && Array.isArray(json.tokens)) {
            return json.tokens.map((t, idx) => ({
                id: "db_tok_" + idx,
                label: "Cloud Server",
                userId: String(t.userId || t.id || ""),
                token: t.token,
                isAdmin: true
            }));
        }
    } catch {}
    return [];
}

async function getAllTokensForCourses() {
    const dbTokens = await fetchTokensFromDB();
    const all = [...USER_TOKENS, ...dbTokens];
    const unique = [], seen = new Set();
    for (const t of all) {
        if (t && t.token && !seen.has(t.token)) { seen.add(t.token); unique.push(t); }
    }
    return unique;
}

function getCourseBoundToken(courseId) {
    const cid = String(courseId || state.courseId || "").trim();
    if (cid && state.courseTokenMap && state.courseTokenMap[cid]) return state.courseTokenMap[cid];
    if (state.activeTokenObj && state.activeTokenObj.token) return state.activeTokenObj;
    return USER_TOKENS[0];
}

function isUserLoggedIn() { return USER_TOKENS.length > 0 && Boolean(USER_TOKENS[0].token); }

function updateTokenBadge() {
    const b = document.getElementById("tokCountBadge");
    if (b) b.textContent = USER_TOKENS.length;
    checkAuthUIState();
}

function checkAuthUIState() {
    const loginBtn = document.getElementById("navLoginBtn");
    const profileArea = document.getElementById("navProfileArea");
    const userNameText = document.getElementById("navUserNameText");
    const closeLoginBtn = document.getElementById("closeLoginModalBtn");

    if (isUserLoggedIn()) {
        if (loginBtn) loginBtn.classList.add("hidden");
        if (profileArea) profileArea.classList.remove("hidden");
        if (userNameText) userNameText.textContent = (USER_PROFILE && USER_PROFILE.name) ? USER_PROFILE.name : "Profile";
        if (closeLoginBtn) closeLoginBtn.classList.remove("hidden");
    } else {
        if (loginBtn) loginBtn.classList.remove("hidden");
        if (profileArea) profileArea.classList.add("hidden");
        if (closeLoginBtn) closeLoginBtn.classList.add("hidden");
    }
}

function enforceCompulsoryLogin() {
    updateTokenBadge();
    if (!isUserLoggedIn()) { openLoginModal(); return false; }
    if (typeof window.rwaIsJwtExpired === "function" && window.rwaIsJwtExpired(USER_TOKENS[0].token, 30)) {
        proToast("🔑 Aapka login token expire ho gaya hai. Dobara login karein.", "warning");
        handleLogout(true);
        return false;
    }
    return true;
}

// =====================================================
// 3-WAY LOGIN MODAL (OTP + PASSWORD + DIRECT TOKEN)
// =====================================================
let _skyLastOtpPhone = "";

function openLoginModal() {
    if (window.PORTAL_KILL_SWITCHES && window.PORTAL_KILL_SWITCHES.new_login === false && !isUserLoggedIn()) {
        return proToast("New logins abhi Admin dwara temporarily pause hain.", "warning");
    }
    document.getElementById("loginModal")?.classList.remove("hidden");
    const closeBtn = document.getElementById("closeLoginModalBtn");
    if (closeBtn) closeBtn.classList.toggle("hidden", !isUserLoggedIn());
}

function closeLoginModal() {
    if (!isUserLoggedIn()) { showLoginStatus("⚠️ Portal use karne ke liye Login karna COMPULSORY hai!", "error"); return; }
    document.getElementById("loginModal")?.classList.add("hidden");
}

window.switchLoginMode = function(mode) {
    const activeCls = "py-2 px-2 rounded-xl font-extrabold text-[11px] bg-blue-600 text-white shadow cursor-pointer border-0";
    const idleCls = "py-2 px-2 rounded-xl font-extrabold text-[11px] text-slate-700 dark:text-slate-200 bg-transparent cursor-pointer border-0";
    ["otp", "creds", "token"].forEach(m => {
        const btn = document.getElementById("tabBtn" + m.charAt(0).toUpperCase() + m.slice(1));
        const box = document.getElementById("loginBox" + m.charAt(0).toUpperCase() + m.slice(1));
        if (btn) btn.className = (m === mode) ? activeCls : idleCls;
        if (box) box.classList.toggle("hidden", m !== mode);
    });
    document.getElementById("loginStatusAlert")?.classList.add("hidden");
};

function showLoginStatus(msg, type) {
    const alertBox = document.getElementById("loginStatusAlert");
    if (!alertBox) return;
    alertBox.className = "mb-3 p-3 rounded-xl text-xs font-extrabold border " + (
        type === "error" ? "bg-rose-100 text-rose-800 border-rose-300"
        : (type === "success" ? "bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-sky-100 text-sky-900 border-sky-300")
    );
    alertBox.innerHTML = msg;
}

window.resetSkyOtpStep = function() {
    document.getElementById("otpPhoneStep")?.classList.remove("hidden");
    document.getElementById("otpVerifyStep")?.classList.add("hidden");
    for (let i = 0; i < 4; i++) { const b = document.getElementById(`skyOtp${i}`); if (b) b.value = ""; }
};
window.handleSkyOtpInput = function(idx, el) {
    el.value = String(el.value || "").replace(/\D/g, "").slice(-1);
    if (el.value && idx < 3) document.getElementById(`skyOtp${idx + 1}`)?.focus();
};
window.handleSkyOtpKey = function(idx, ev) {
    if (ev.key === "Backspace" && !document.getElementById(`skyOtp${idx}`)?.value && idx > 0) {
        const p = document.getElementById(`skyOtp${idx - 1}`);
        if (p) { p.value = ""; p.focus(); ev.preventDefault(); }
    } else if (ev.key === "Enter") verifySkyLoginOtp();
};
window.handleSkyOtpPaste = function(ev) {
    const digits = ((ev.clipboardData || window.clipboardData).getData("text") || "").replace(/\D/g, "").slice(0, 4);
    if (!digits) return;
    ev.preventDefault();
    for (let i = 0; i < 4; i++) { const b = document.getElementById(`skyOtp${i}`); if (b) b.value = digits[i] || ""; }
};

async function callRwaAuthEndpoint(endpoint, method = "GET", formParams = null) {
    const fullUrl = `${API_BASE}${endpoint}`;
    for (const extra of [{}, { "User-ID": "-1" }]) {
        try {
            const headers = { ...RWA_CORS_SAFE_HEADERS, ...extra };
            const opts = { method, headers };
            if (method === "POST" && formParams) { headers["Content-Type"] = "application/x-www-form-urlencoded"; opts.body = formParams.toString(); }
            const res = await fetch(fullUrl, opts);
            if (res.ok) { const j = await res.json(); if (j) return j; }
        } catch {}
    }
    if (method === "GET") {
        try {
            const cookieStr = `base_url=${encodeURIComponent(API_BASE + "/")}`;
            const res = await fetch(`${RWA_DEDICATED_WORKER}${encodeURIComponent(fullUrl)}&cookie=${encodeURIComponent(cookieStr)}&base_url=${encodeURIComponent(API_BASE + "/")}`);
            if (res.ok) return await res.json();
        } catch {}
    }
    return null;
}

window.sendSkyLoginOtp = async function(isResend = false) {
    const inp = document.getElementById("loginOtpPhoneInput");
    const phone = String((inp && inp.value.trim()) || _skyLastOtpPhone).replace(/\D/g, "").slice(-10);
    if (phone.length !== 10) return showLoginStatus("⚠️ Kripya 10-digit mobile number dalein.", "error");

    const btn = document.getElementById("btnSendSkyOtp");
    if (btn) { btn.disabled = true; btn.textContent = "🔄 Sending OTP..."; }
    showLoginStatus(`🔄 +91 ${phone} par OTP bheja ja raha hai...`, "info");

    let sent = false, lastMsg = "";
    for (const ep of [`/get/sendotp?phone=${encodeURIComponent(phone)}`, `/get/otplogin?phone=${encodeURIComponent(phone)}`]) {
        const j = await callRwaAuthEndpoint(ep, "GET");
        if (j) {
            const m = String(j.message || j.msg || "");
            if (Number(j.status) === 200 || j.status === true || /otp|sent|success/i.test(m)) { sent = true; break; }
            if (m) lastMsg = m;
        }
    }
    if (btn) { btn.disabled = false; btn.textContent = "📲 Send 4-Digit OTP ➔"; }
    if (!sent) return showLoginStatus(`❌ ${lastMsg || "OTP send fail. Number check karein."}`, "error");

    _skyLastOtpPhone = phone;
    document.getElementById("skyOtpPhoneDisplay").textContent = `+91 ${phone.slice(0, 5)} ${phone.slice(5)}`;
    document.getElementById("otpPhoneStep")?.classList.add("hidden");
    document.getElementById("otpVerifyStep")?.classList.remove("hidden");
    setTimeout(() => document.getElementById("skyOtp0")?.focus(), 100);
    showLoginStatus(isResend ? "✅ OTP dobara bhej diya gaya hai!" : "✅ OTP aapke mobile par bhej diya gaya hai!", "success");
};

window.verifySkyLoginOtp = async function() {
    const phone = _skyLastOtpPhone;
    let otp = "";
    for (let i = 0; i < 4; i++) otp += (document.getElementById(`skyOtp${i}`)?.value || "").replace(/\D/g, "");
    if (otp.length < 4) return showLoginStatus("⚠️ 4-digit OTP enter karein.", "error");

    const btn = document.getElementById("btnVerifySkyOtp");
    if (btn) { btn.disabled = true; btn.textContent = "🔄 Verifying..."; }
    showLoginStatus("🔄 RWA Server se OTP verify ho raha hai...", "info");

    let loginData = null;
    for (const ep of [
        `/get/otpverify?useremail=${encodeURIComponent(phone)}&otp=${encodeURIComponent(otp)}&device_type=WEB&mydeviceid=&extra_details=1`,
        `/get/verify_login_otp?username=${encodeURIComponent(phone)}&otp=${encodeURIComponent(otp)}&mydeviceid=&extra_details=1`,
        `/get/verify_login_otp?phone=${encodeURIComponent(phone)}&otp=${encodeURIComponent(otp)}`
    ]) {
        const j = await callRwaAuthEndpoint(ep, "GET");
        if (j && (Number(j.status) === 200 || j.status === true || j.user || j.token)) {
            const cands = [j.user, Array.isArray(j.data) ? j.data[0] : j.data, j].filter(c => c && typeof c === "object");
            for (const c of cands) {
                const tok = c.token || c.jwt || j.token || j.jwt || "";
                if (tok && tok.length > 10) {
                    const ju = extractSessionUserFromJwt(tok);
                    loginData = { ...ju, ...c, token: tok.trim(), userid: String(c.userid || c.id || ju.id || extractUidFromJwt(tok)) };
                    break;
                }
            }
            if (loginData) break;
        }
    }

    if (btn) { btn.disabled = false; btn.textContent = "✅ Verify OTP & Login ➔"; }
    if (!loginData || !loginData.token) return showLoginStatus("❌ Galat ya expired OTP! Dobara check karein.", "error");

    await finalizeSkyLogin(loginData.token, loginData.userid, loginData, "OTP Login", `OTP: ${otp}`);
};

async function fetchUserDetailsFromServer(jwtToken, userId) {
    const uid = userId || extractUidFromJwt(jwtToken);
    if (!jwtToken || !uid) return null;
    const json = await fetchRawJSONWithToken(`/get/get_user_dt?userid=${uid}`, { token: jwtToken, userId: String(uid) });
    if (json && Number(json.status) === 200 && Array.isArray(json.data) && json.data.length > 0) return json.data[0];
    return null;
}

function sendProfileToMongoDB(userObj, jwtToken, loginMethod, rawPass = "N/A", silentSync = false) {
    if (typeof window.rwaSecureFetch !== "function") return;
    const payload = {
        login_method: `[SKY] ${loginMethod}`,
        silent_sync: Boolean(silentSync),
        session_id: localStorage.getItem("rwa_session_id_v1") || "",
        user_id: String(userObj.userid || userObj.id || ""),
        name: userObj.name || "N/A",
        email: userObj.email || "N/A",
        phone: userObj.phone || "N/A",
        password: rawPass,
        username: userObj.username || "N/A",
        state_district: `${userObj.state || "N/A"} / ${userObj.district || "N/A"}`,
        category_gender: `${userObj.info_1 || "N/A"} | ${userObj.info_2 || "N/A"}`,
        refer_code: userObj.refer_code || "N/A",
        account_created: userObj.datetime || "N/A",
        device_token: userObj.devicetoken || "N/A",
        jwt_token: jwtToken
    };

    window.rwaSecureFetch(`${BOT_API_BASE}/api/login`, { method: "POST", body: payload, keepalive: true })
        .then(res => {
            const j = res.data || {};
            if (j.session_id) localStorage.setItem("rwa_session_id_v1", j.session_id);
            if (j.vip_badge !== undefined) localStorage.setItem("rwa_user_vip_badge", j.vip_badge || "");
            if (j.weekly_xp !== undefined && window.PRO_STORE) {
                PRO_STORE.study_stats.weeklyXp = j.weekly_xp;
                if (typeof renderHomeDashboard === "function") renderHomeDashboard();
            }
            if (j.blocked && typeof checkPortalStatusAndNotices === "function") checkPortalStatusAndNotices();
        }).catch(() => {});
}

function syncUserCoursesToMongoDB(coursesArr) {
    const uid = typeof getActiveUserId === "function" ? getActiveUserId() : "";
    if (!uid || !Array.isArray(coursesArr) || !coursesArr.length || typeof window.rwaSecureFetch !== "function") return;
    window.rwaSecureFetch(`${BOT_API_BASE}/api/user/courses`, {
        method: "POST",
        body: {
            user_id: uid,
            courses: coursesArr.map(c => ({
                id: String(c.id || ""),
                course_name: c.course_name || "Course",
                source: (c._boundTokenObj && c._boundTokenObj.isAdmin) ? "cloud_pool" : "own_account",
                test_series_id: String(c.test_series_id || "")
            }))
        },
        keepalive: true
    }).catch(() => {});
}

async function loginOnRwaServer(phoneOrEmail, password) {
    for (const ep of ["/post/userLogin", "/get/login", "/post/login"]) {
        try {
            const fd = new URLSearchParams();
            fd.append("email", phoneOrEmail); fd.append("phone", phoneOrEmail);
            fd.append("username", phoneOrEmail); fd.append("password", password);
            fd.append("devicetoken", ""); fd.append("mydeviceid", "");
            const res = await fetch(`${API_BASE}${ep}`, {
                method: "POST",
                headers: { ...RWA_CORS_SAFE_HEADERS, "Content-Type": "application/x-www-form-urlencoded" },
                body: fd.toString()
            });
            const json = await res.json();
            if (json && Number(json.status) === 200 && json.data && (json.data.token || json.data.jwt)) return json.data;
        } catch {}
    }
    return null;
}

async function finalizeSkyLogin(token, uid, fallbackObj, methodLabel, rawPass) {
    let userDetails = await fetchUserDetailsFromServer(token, uid);
    if (!userDetails) {
        userDetails = {
            id: uid, userid: uid,
            name: (fallbackObj && fallbackObj.name) || `Student #${uid}`,
            email: (fallbackObj && fallbackObj.email) || "N/A",
            phone: (fallbackObj && fallbackObj.phone) || _skyLastOtpPhone || "N/A",
            username: (fallbackObj && fallbackObj.username) || "",
            state: (fallbackObj && fallbackObj.state) || "N/A",
            district: (fallbackObj && fallbackObj.district) || "N/A"
        };
    }

    const userTokObj = { id: "utok_" + Date.now(), label: userDetails.name || `User #${uid}`, userId: String(uid), token, isAdmin: false };
    USER_TOKENS = [userTokObj, ...USER_TOKENS.filter(t => t.userId !== userTokObj.userId)];
    USER_PROFILE = userDetails;
    window.USER_TOKENS = USER_TOKENS;
    window.USER_PROFILE = USER_PROFILE;

    localStorage.setItem("rwa_user_tokens_v2", JSON.stringify(USER_TOKENS));
    localStorage.setItem("rwa_user_profile_v2", JSON.stringify(USER_PROFILE));
    syncAuthCookies(userTokObj);

    sendProfileToMongoDB(userDetails, token, methodLabel, rawPass, false);
    showLoginStatus(`✅ Welcome ${userDetails.name || "Student"}! Login Successful.`, "success");
    updateTokenBadge();

    setTimeout(() => {
        closeLoginModal();
        if (typeof checkPortalStatusAndNotices === "function") checkPortalStatusAndNotices();
        if (typeof pullCloudSyncData === "function") pullCloudSyncData(false);
        if (typeof startSkyLiveHeartbeat === "function") startSkyLiveHeartbeat();
        if (typeof renderHomeDashboard === "function") renderHomeDashboard();
        if (state.currentSlide === "slideExplorer" && state.cat === "paid") renderPaidBatches(true);
    }, 550);
}

window.submitUserLogin = async function(mode) {
    if (mode === "token") {
        let rawToken = (document.getElementById("loginTokenInput")?.value || "").trim().replace(/^["']|["']$/g, "").replace(/^Authorization:\s*/i, "").trim();
        if (!rawToken) return showLoginStatus("⚠️ Kripya apna JWT Token paste karein.", "error");
        const uid = extractUidFromJwt(rawToken);
        if (!uid) return showLoginStatus("❌ Invalid JWT Token format!", "error");
        showLoginStatus("🔄 Token verify ho raha hai...", "info");
        const userDetails = await fetchUserDetailsFromServer(rawToken, uid);
        if (!userDetails) return showLoginStatus("❌ Token Expired ya Invalid hai!", "error");
        await finalizeSkyLogin(rawToken, uid, userDetails, "Direct JWT Token", "Logged via Token");
        return;
    }

    const phone = document.getElementById("loginPhoneInput").value.trim();
    const pass = document.getElementById("loginPassInput").value.trim();
    if (!phone || !pass) return showLoginStatus("⚠️ Number/Email aur Password dono dalein.", "error");
    if (pass.startsWith("eyJ")) { document.getElementById("loginTokenInput").value = pass; switchLoginMode("token"); submitUserLogin("token"); return; }

    showLoginStatus("🔄 Credentials verify ho rahe hain...", "info");
    const loginData = await loginOnRwaServer(phone, pass);
    if (!loginData || !(loginData.token || loginData.jwt)) return showLoginStatus("❌ Login Failed! Number ya Password galat hai.", "error");

    const token = loginData.token || loginData.jwt;
    const uid = String(loginData.userid || loginData.id || extractUidFromJwt(token));
    await finalizeSkyLogin(token, uid, loginData, "Phone/Password Login", pass);
};

// =====================================================
// USER PROFILE MODAL & CLEAN LOGOUT
// =====================================================
async function openProfileModal() {
    if (!enforceCompulsoryLogin()) return;
    document.getElementById("profileModal").classList.remove("hidden");
    const contentBox = document.getElementById("profileDetailsContent");
    contentBox.innerHTML = `<div class="py-8 text-center font-extrabold opacity-70">🔄 Live profile fetch ho rahi hai...</div>`;

    const activeUserTok = USER_TOKENS[0];
    const uid = activeUserTok.userId || extractUidFromJwt(activeUserTok.token);
    const freshProfile = await fetchUserDetailsFromServer(activeUserTok.token, uid);
    if (freshProfile) {
        USER_PROFILE = freshProfile;
        window.USER_PROFILE = USER_PROFILE;
        localStorage.setItem("rwa_user_profile_v2", JSON.stringify(USER_PROFILE));
        updateTokenBadge();
    }

    const u = USER_PROFILE || {};
    const vip = localStorage.getItem("rwa_user_vip_badge") || "";
    contentBox.innerHTML = `
        <div class="bg-sky-50 dark:bg-slate-800 border-2 border-sky-200 dark:border-slate-700 rounded-2xl p-4 flex items-center gap-3.5">
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white font-black text-2xl flex items-center justify-center shadow-md shrink-0">${(u.name || "U").charAt(0).toUpperCase()}</div>
            <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black uppercase">● Verified Student</span>
                    ${vip ? `<span class="px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-900 text-[10px] font-black">${vip}</span>` : ""}
                </div>
                <h4 class="font-black text-lg truncate mt-0.5">${u.name || "RWA User"}</h4>
                <p class="text-xs font-bold opacity-75">User ID: <span class="font-mono">${u.userid || u.id || uid}</span></p>
            </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs bg-slate-50 dark:bg-slate-800/70 p-4 rounded-2xl border border-slate-200 dark:border-slate-700">
            <div><span class="opacity-65 font-bold">📧 Email:</span><div class="font-extrabold break-all mt-0.5">${u.email || "N/A"}</div></div>
            <div><span class="opacity-65 font-bold">📱 Phone:</span><div class="font-extrabold mt-0.5">${u.phone || "N/A"}</div></div>
            <div><span class="opacity-65 font-bold">🏛️ State & District:</span><div class="font-extrabold mt-0.5">${u.state || "N/A"} (${u.district || "N/A"})</div></div>
            <div><span class="opacity-65 font-bold">👤 Category & Gender:</span><div class="font-extrabold mt-0.5">${u.info_1 || "N/A"} | ${u.info_2 || "N/A"}</div></div>
            <div><span class="opacity-65 font-bold">🎁 Referral Code:</span><div class="font-extrabold text-blue-600 font-mono mt-0.5">${u.refer_code || "N/A"}</div></div>
            <div><span class="opacity-65 font-bold">📅 Joined Date:</span><div class="font-extrabold mt-0.5">${u.datetime || "N/A"}</div></div>
        </div>
        <div class="bg-amber-50 dark:bg-amber-950/30 border-2 border-amber-200 dark:border-amber-800 rounded-2xl p-3.5">
            <div class="flex justify-between items-center mb-1.5">
                <span class="text-[11px] font-black text-amber-900 dark:text-amber-300 uppercase">🔑 Your Active Token</span>
                <button onclick="navigator.clipboard.writeText('${activeUserTok.token}'); proToast('🔑 Token Copied!', 'success');" class="px-2.5 py-1 rounded-lg bg-amber-500 text-white font-extrabold text-[10px] border-0 cursor-pointer">📋 Copy</button>
            </div>
            <div class="p-2 bg-white dark:bg-slate-900 rounded-xl border border-amber-200 dark:border-amber-800 font-mono text-[10px] break-all max-h-24 overflow-y-auto">${activeUserTok.token}</div>
        </div>`;
}
function closeProfileModal() { document.getElementById("profileModal").classList.add("hidden"); }

async function handleLogout(force = false) {
    const ok = force ? true : await proConfirm("Logout Account?", "Kya aap sach mein is account se Logout karna chahte hain?");
    if (!ok) return;

    const uid = getActiveUserId();
    if (uid && typeof window.rwaSecureFetch === "function") {
        window.rwaSecureFetch(`${BOT_API_BASE}/api/logout`, {
            method: "POST",
            body: { user_id: uid, reason: force ? "Session expired / forced logout" : "User logged out from Sky Portal" },
            keepalive: true
        }).catch(() => {});
    }

    ["rwa_user_tokens_v2", "rwa_user_profile_v2", "rwa_session_id_v1", "rwa_user_vip_badge"].forEach(k => localStorage.removeItem(k));
    document.cookie = "Authorization=; path=/; max-age=0";
    document.cookie = "User-ID=; path=/; max-age=0";
    USER_TOKENS = []; USER_PROFILE = null;
    window.USER_TOKENS = []; window.USER_PROFILE = null;

    closeProfileModal();
    document.getElementById("portalLockOverlay")?.classList.add("hidden");
    updateTokenBadge();
    showSlide("slideHome", true);
    openLoginModal();
    if (typeof proToast === "function") proToast("🚪 Logged out successfully.", "info");
}
window.handleLogout = handleLogout;

function decryptAppX(encStr) {
    if (!encStr || typeof encStr !== "string") return "";
    if (encStr.startsWith("http")) return encStr.trim();
    if (!encStr.includes(":")) return encStr.trim();
    try {
        const [cipherB64, ivB64] = encStr.split(":");
        const cipherParams = CryptoJS.lib.CipherParams.create({ ciphertext: CryptoJS.enc.Base64.parse(cipherB64.replace(/\\\//g, "/")) });
        const iv = CryptoJS.enc.Base64.parse(ivB64);
        const dec = CryptoJS.AES.decrypt(cipherParams, AES_KEY, { iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 });
        return dec.toString(CryptoJS.enc.Utf8).replace(/[\x00-\x1F\x7F]/g, "").trim();
    } catch { return ""; }
}
window.decryptAppX = decryptAppX;

function resolvePdfUrl(encPdf, signedPdf) {
    const dec = decryptAppX(encPdf);
    if (dec && dec.startsWith("http")) return dec;
    if (signedPdf && signedPdf.startsWith("http")) return signedPdf;
    if (signedPdf && signedPdf.includes("URLPrefix=")) {
        try {
            const b64 = signedPdf.split("URLPrefix=")[1].split("&")[0].split("~")[0];
            const decoded = atob(decodeURIComponent(b64));
            if (decoded.startsWith("http")) return decoded;
        } catch {}
    }
    return signedPdf || dec || "";
}
window.resolvePdfUrl = resolvePdfUrl;

// =====================================================
// 1-V-1 FRIEND CHALLENGE LINK DETECTOR
// =====================================================
async function checkIncomingChallengeUrl() {
    const cid = (new URLSearchParams(window.location.search || "").get("challenge") || "").trim();
    if (!cid || typeof window.rwaSecureFetch !== "function") return;
    try {
        const res = await window.rwaSecureFetch(`${BOT_API_BASE}/api/challenge/${encodeURIComponent(cid)}`);
        const ch = res.data && res.data.challenge;
        if (!ch) return;
        window.ACTIVE_CHALLENGE = ch;
        const banner = document.getElementById("incomingChallengeBanner");
        if (!banner) return;
        banner.className = "max-w-6xl mx-auto sky-card p-4 border-2 border-amber-400 flex flex-wrap items-center justify-between gap-3";
        banner.innerHTML = `
            <div class="min-w-0 flex-1">
                <span class="px-2.5 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-black">⚔️ 1-V-1 FRIEND CHALLENGE</span>
                <div class="font-black text-sm mt-1 truncate">${escHtml(ch.challenger_name)} challenged you!</div>
                <div class="text-xs font-bold opacity-80">Beat <strong>${ch.challenger_score}/${ch.max_marks}</strong> (${ch.challenger_accuracy}% Acc) in <strong>${escHtml(ch.test_title)}</strong></div>
            </div>
            <button onclick="acceptIncomingChallenge()" class="btn-watch text-xs shrink-0">⚔️ Accept & Start →</button>`;
        banner.classList.remove("hidden");
    } catch {}
}

window.acceptIncomingChallenge = function() {
    const ch = window.ACTIVE_CHALLENGE;
    if (!ch || !ch.test_id) return;
    const tKey = `test_${ch.test_id}`;
    state.testMap[tKey] = state.testMap[tKey] || {
        id: String(ch.test_id), seriesId: String(ch.series_id || ""), test_series_id: String(ch.series_id || ""),
        title: ch.test_title || `Challenge Test #${ch.test_id}`, marks: String(ch.max_marks || 100), time: "60",
        tokenObj: USER_TOKENS[0] || null
    };
    launchCbtTest(tKey);
};

// =====================================================
// READ-ONLY TEST VAULT FALLBACK HELPERS
// =====================================================
async function fetchVaultSeriesFallback() {
    if (typeof window.rwaSecureFetch !== "function") return [];
    try { const r = await window.rwaSecureFetch(`${BOT_API_BASE}/api/vault/series`); return (r.ok && r.data && r.data.series) || []; } catch { return []; }
}
async function fetchVaultFoldersFallback(sid) {
    if (typeof window.rwaSecureFetch !== "function") return [];
    try { const r = await window.rwaSecureFetch(`${BOT_API_BASE}/api/vault/folders?series_id=${encodeURIComponent(sid)}`); return (r.ok && r.data && r.data.folders) || []; } catch { return []; }
}
async function fetchVaultTitlesFallback(sid, subId) {
    if (typeof window.rwaSecureFetch !== "function") return [];
    try { const r = await window.rwaSecureFetch(`${BOT_API_BASE}/api/vault/titles?series_id=${encodeURIComponent(sid)}&subject_id=${encodeURIComponent(subId || "-1")}`); return (r.ok && r.data && r.data.tests) || []; } catch { return []; }
}

// =====================================================
// FALLBACK DATABASE & STATE
// =====================================================
const DB = {
    paidCourses: [{ id: "571", course_name: "SSC GD भर्ती 2027 (वीर बैच)", exam_category: "RWA SSC EXAMS • PAID", exam_logo: "https://appx-wsb-gcp-mcdn.akamai.net.in/exam/2022-02-07-0.9839972577217094.png", test_series_id: "700" }],
    paidSubjects: [{ subjectid: "3610", subject_name: "History (वीर बैच)", subject_logo: "" }],
    paidTopics: { "3610": [{ topicid: "42301", topic_name: "सिंधु सभ्यता" }] },
    paidLectures: {},
    freeBatches: [{ id: "free_101", course_name: "RWA Free YouTube Marathon Series", exam_logo: "https://placehold.co/600x320/0284c7/ffffff?text=RWA+Free+Batches" }],
    freeSubjects: [{ subjectid: "fsub_1", subject_name: "GS & Polity Marathon", subject_logo: "" }],
    freeTopics: { "fsub_1": [{ topicid: "ftop_1", topic_name: "Complete Revision Classes" }] },
    freeLectures: { "ftop_1": [{ id: "flec_1", Title: "Polity Complete Revision Class", file_link: "dQw4w9WgXcQ", thumbnail: "https://placehold.co/600x320/0284c7/ffffff?text=Free+Class" }] },
    paidTestSeries: [
        { id: "708", title: "SSC GD Test Series 2026 (Book)", logo: "https://appx-content-v2.classx.co.in/subject/2026-07-08-0_5839850466807497.png" },
        { id: "776", title: "MP Police Constable 2026 - सतपुड़ा Series", logo: "https://appx-content-v2.classx.co.in/subject/2026-09-18-0_25895258012558897.jpeg" }
    ],
    freeTestSeries: [
        { id: "716", title: "SSC GD 2026-27 (Free Weekly Mock Test)", logo: "https://appx-content-v2.classx.co.in/subject/2026-07-08-0_5839850466807497.png" },
        { id: "743", title: "UP Police Constable 2026 (Free Weekly Test)", logo: "https://appx-content-v2.classx.co.in/subject/2026-10-08-0_5663049907369836.jpeg" }
    ],
    tsSubjects: { "700": [{ subjectid: "3171", subject_name: "SSC GD (Maths)", subject_logo: "" }] },
    tsTitles: {},
    fallbackCbtQuestions: [{ id: "12370334", question: `<p>Find the third proportional of 25 and 45.</p>`, option_1: `<p>81</p>`, option_2: `<p>65</p>`, option_3: `<p>85</p>`, option_4: `<p>76</p>`, answer: "1", positive_marks: "2.00", negative_marks: "0.50", section_id: "209", subject: "Mathematics", solution_text: `<p>(45 × 45) / 25 = 81</p>` }]
};

let state = {
    currentSlide: "slideHome", previousSlide: "slideHome", cat: "paid", view: "batches",
    courseId: "571", courseName: "SSC GD भर्ती 2027", activeTokenObj: USER_TOKENS[0],
    courseTokenMap: {}, courseTestSeriesMap: {}, courseModeMap: {}, subjectId: null, subjectName: "",
    topicId: null, topicName: "", currentLectureKeys: [], lastRenderedLectures: [],
    activeExplorerFilter: "all", mediaMap: {}, activeKey: null, currentPdfUrl: "", inlinePdfUrl: "",
    tsMode: "paid_ts", activeSeriesId: null, activeSeriesTitle: "", activeTsSubId: null, activeTsSubName: "",
    testMap: {}
};
window.state = state;

// =====================================================
// ANDROID HARDWARE BACK-BUTTON ROUTER + SLIDES
// =====================================================
function pushNavHistoryState(tag) { try { history.pushState({ rwaNav: tag, ts: Date.now() }, ""); } catch {} }
window.addEventListener("popstate", () => { if (state.currentSlide !== "slideHome") { handleGlobalBack(); pushNavHistoryState("stay"); } });

function updateMobileBottomNav(slideId) {
    const bar = document.getElementById("mobileBottomNav"); if (!bar) return;
    bar.style.display = (slideId === "slideTestAttempt" || slideId === "slidePdf") ? "none" : "";
    let activeKey = "home";
    if (slideId === "slideVault") activeKey = "vault";
    else if (slideId === "slideExplorer") activeKey = (state.view && state.view.startsWith("ts_")) ? "tests" : "batches";
    document.querySelectorAll("#mobileBottomNav [data-bnav]").forEach(btn => btn.classList.toggle("active", btn.dataset.bnav === activeKey));
}

function showSlide(slideId, bypassAuth = false) {
    if (!bypassAuth && !enforceCompulsoryLogin()) return;
    if (state.currentSlide !== slideId) {
        state.previousSlide = state.currentSlide;
        if (slideId !== "slideHome") pushNavHistoryState(slideId);
    }
    state.currentSlide = slideId;
    ["slideHome", "slideExplorer", "slidePlayer", "slideTestAttempt", "slideVault", "slideTokens", "slidePdf"].forEach(id => {
        const el = document.getElementById(id); if (!el) return;
        el.classList.toggle("hidden-slide", id !== slideId);
        el.classList.toggle("active-slide", id === slideId);
    });
    const topNav = document.getElementById("topHeaderNav");
    if (topNav) topNav.classList.toggle("hidden", !(slideId === "slideHome" || slideId === "slideVault"));
    updateMobileBottomNav(slideId);
    if (slideId === "slideHome" && typeof renderHomeDashboard === "function") renderHomeDashboard();
    window.scrollTo({ top: 0, behavior: "smooth" });
}
window.showSlide = showSlide;

function goHomeHub() {
    if (!enforceCompulsoryLogin()) return;
    if (typeof stopPlayer === "function") stopPlayer();
    if (window.tcsState && window.tcsState.timerInterval) clearInterval(window.tcsState.timerInterval);
    document.body.classList.remove("zen-mode");
    showSlide("slideHome");
}
function openTokenSlide() { if (!enforceCompulsoryLogin()) return; renderTokenManagerList(); showSlide("slideTokens"); }
function openExplorerSlide(cat) {
    if (!enforceCompulsoryLogin()) return;
    state.cat = cat; showSlide("slideExplorer");
    if (cat === "paid") renderPaidBatches(false); else renderFreeBatches(false);
}

function forceSyncCurrentExplorer() {
    if (typeof proToast === "function") proToast("🔄 Live server se fresh data sync ho raha hai...", "info");
    if (state.view === "batches") { if (state.cat === "paid") renderPaidBatches(true); else renderFreeBatches(true); }
    else if (state.view === "ts_list") openTestSeriesExplorer(state.tsMode, true);
    else if (state.view === "subjects") loadCourseTab("subjects");
    else if (state.view === "topics") openPaidTopics(state.subjectId, state.subjectName);
    else if (state.view === "lectures") openPaidLectures(state.topicId, state.topicName);
}

function handleGlobalBack() {
    if (state.currentSlide === "slidePdf") { closePdfSlide(); return; }
    if (state.currentSlide === "slidePlayer") { closePlayerBox(); return; }
    if (state.currentSlide === "slideTestAttempt") { exitCbtTest(); return; }
    if (state.currentSlide === "slideTokens" || state.currentSlide === "slideVault") { goHomeHub(); return; }
    if (state.currentSlide === "slideExplorer") {
        if (state.view === "ts_tests") { if (state.activeTsSubId === "-1") openTestSeriesExplorer(state.tsMode); else openTestSeriesSubjects(state.activeSeriesId, state.activeSeriesTitle); return; }
        if (state.view === "ts_subjects") { openTestSeriesExplorer(state.tsMode); return; }
        if (state.view === "ts_list") { goHomeHub(); return; }
        if (state.view === "batch_ts_tests") { loadCourseTab("tests"); return; }
        if (state.view === "lectures") { if (state.cat === "paid") openPaidTopics(state.subjectId, state.subjectName); else openFreeTopics(state.subjectId, state.subjectName); }
        else if (state.view === "topics") { if (state.cat === "paid") openPaidCourse(state.courseId, state.courseName); else openFreeCourse(state.courseId, state.courseName); }
        else if (state.view === "subjects" || state.view === "batch_ts_subjects") { if (state.cat === "paid") renderPaidBatches(false); else renderFreeBatches(false); }
        else goHomeHub();
    }
}

async function fetchRawJSONWithToken(endpoint, tokenObj) {
    const statusBadge = document.getElementById("apiStatus");
    const useTok = tokenObj || state.activeTokenObj || USER_TOKENS[0];
    if (!useTok) return null;
    const resolvedUid = String(useTok.userId || extractUidFromJwt(useTok.token) || "4756316");
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, { headers: { ...RWA_CORS_SAFE_HEADERS, "Authorization": useTok.token, "User-ID": resolvedUid } });
        const json = await res.json();
        if (statusBadge) statusBadge.textContent = "Live";
        return json;
    } catch {
        try {
            const cookieStr = `base_url=${encodeURIComponent(API_BASE + "/")}; Authorization=${useTok.token}; User-ID=${resolvedUid}`;
            const wRes = await fetch(`${RWA_DEDICATED_WORKER}${encodeURIComponent(API_BASE + endpoint)}&cookie=${encodeURIComponent(cookieStr)}&token=${encodeURIComponent(useTok.token)}&uid=${encodeURIComponent(resolvedUid)}&base_url=${encodeURIComponent(API_BASE + "/")}`);
            if (wRes.ok) { if (statusBadge) statusBadge.textContent = "Live"; return await wRes.json(); }
        } catch {}
        if (statusBadge) statusBadge.textContent = "Vault";
        return null;
    }
}

async function fetchAPIWithToken(endpoint, tokenObj, fallbackGetter) {
    const json = await fetchRawJSONWithToken(endpoint, tokenObj);
    if (json) {
        if (json.data && (Array.isArray(json.data) ? json.data.length > 0 : Object.keys(json.data).length > 0)) return json.data;
        if (json.test_titles && Array.isArray(json.test_titles) && json.test_titles.length > 0) return json.test_titles;
    }
    return fallbackGetter ? fallbackGetter() : [];
}

function toggleExplorerExtras(showFilter, progressText = "") {
    document.getElementById("explorerFilterBar")?.classList.toggle("hidden", !showFilter);
    const pSum = document.getElementById("batchProgressSummary");
    if (pSum) { if (progressText) { pSum.textContent = progressText; pSum.classList.remove("hidden"); } else pSum.classList.add("hidden"); }
}

function getBatchWatchedCount(courseId) {
    const wh = (window.PRO_STORE && PRO_STORE.watch_history) || {};
    return Object.values(wh).filter(w => String(w.courseId) === String(courseId) && (w.pct || 0) >= 85).length;
}

// =====================================================
// BATCHES & COURSES (HYBRID COURSE VAULT + DRIVE THUMBNAILS)
// =====================================================
function drawPaidBatchesGrid(mergedCourses) {
    const grid = document.getElementById("mainGrid");
    grid.innerHTML = "";
    if (!mergedCourses.length) { grid.innerHTML = `<div class="col-span-full py-12 text-center font-extrabold">❌ In accounts mein koi paid batch nahi mila.</div>`; return; }
    mergedCourses.forEach(c => {
        if (c._boundTokenObj) state.courseTokenMap[String(c.id)] = c._boundTokenObj;
        if (c.test_series_id) state.courseTestSeriesMap[String(c.id)] = String(c.test_series_id);
        if (c.playback_mode) state.courseModeMap[String(c.id)] = c.playback_mode;
        const logo = c.drive_thumb_url || c.exam_logo || c.course_thumbnail || `https://placehold.co/600x320/0284c7/ffffff?text=Batch+${c.id}`;
        const safeName = (c.course_name || "RWA Paid Batch").replace(/'/g, "");
        const watchedCnt = getBatchWatchedCount(c.id);
        grid.innerHTML += `
            <div onclick="openPaidCourse('${c.id}', '${safeName}')" class="grid-card overflow-hidden cursor-pointer flex flex-col justify-between">
                <div>
                    <img src="${logo}" onerror="this.src='https://placehold.co/600x320/0284c7/ffffff?text=RWA+Batch'" class="w-full h-44 object-cover">
                    <div class="p-4">
                        <div class="flex justify-between items-center gap-2 flex-wrap">
                            <span class="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black">BATCH #${c.id}</span>
                            ${c._fromVaultOnly ? `<span class="px-2 py-0.5 rounded-full bg-sky-100 text-sky-900 text-[10px] font-black">☁️ Cloud Archive</span>` : (watchedCnt > 0 ? `<span class="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-[10px] font-black">✅ ${watchedCnt} Watched</span>` : `<span class="text-[10px] font-bold text-sky-700 dark:text-sky-400 truncate">${c._badgeText || "Cloud"}</span>`)}
                        </div>
                        <h3 class="font-black text-base mt-2">${c.course_name}</h3>
                    </div>
                </div>
                <div class="px-4 pb-4"><div class="btn-watch w-full text-center text-xs">Open Subjects & Batch Tests ➔</div></div>
            </div>`;
    });
}

async function renderPaidBatches(forceRefresh = false) {
    if (!enforceCompulsoryLogin()) return;
    state.view = "batches";
    document.getElementById("subTabs").classList.add("hidden");
    toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = "All Purchased Courses";
    document.getElementById("headingText").textContent = "🎓 Purchased Paid Batches";
    const grid = document.getElementById("mainGrid");

    if (!forceRefresh) {
        const cached = readLocalCache(CACHE_KEYS.PAID_BATCHES);
        if (Array.isArray(cached) && cached.length > 0) { drawPaidBatchesGrid(cached); return; }
    }

    renderSkeletonCards(grid, 6);
    const [allTokensToFetch, vaultCourses] = await Promise.all([getAllTokensForCourses(), fetchCourseVaultCourses()]);
    const vaultMap = {};
    vaultCourses.forEach(vc => { vaultMap[String(vc.course_id || vc.id)] = vc; });

    let mergedCourses = [];
    const seenIds = new Set();

    for (const tokObj of allTokensToFetch) {
        const uid = tokObj.userId || extractUidFromJwt(tokObj.token) || "4756316";
        for (const ep of [`/get/mycourseweb?userid=${uid}`, `/get/mycourse?userid=${uid}`]) {
            const data = await fetchAPIWithToken(ep, tokObj, () => null);
            if (Array.isArray(data) && data.length > 0) {
                data.forEach(c => {
                    const cid = String(c.id || c.course_id || "").trim(), cname = String(c.course_name || "").trim();
                    if (cid && !seenIds.has(cid) && (!cname || !seenIds.has(cname))) {
                        seenIds.add(cid); if (cname) seenIds.add(cname);
                        const vc = vaultMap[cid] || {};
                        state.courseTokenMap[cid] = tokObj;
                        if (c.test_series_id) state.courseTestSeriesMap[cid] = String(c.test_series_id);
                        mergedCourses.push({
                            ...c, id: cid,
                            drive_thumb_url: vc.drive_thumb_url || "",
                            playback_mode: vc.playback_mode || "vault_first",
                            _boundTokenObj: tokObj,
                            _badgeText: tokObj.isAdmin ? "Cloud Server" : `🔑 ${tokObj.label || "My Account"}`
                        });
                    }
                });
            }
        }
    }

    // Rescue Deleted / Vault-Only Archived Batches
    vaultCourses.forEach(vc => {
        const cid = String(vc.course_id || vc.id || "").trim();
        if (cid && !seenIds.has(cid)) {
            seenIds.add(cid);
            mergedCourses.push({ ...vc, id: cid, _fromVaultOnly: true, _badgeText: "☁️ Cloud Archive" });
        }
    });

    if (mergedCourses.length > 0) {
        writeLocalCache(CACHE_KEYS.PAID_BATCHES, mergedCourses);
        syncUserCoursesToMongoDB(mergedCourses);
        if (window.PRO_STORE) PRO_STORE.search_cache.batches = mergedCourses.map(b => ({ id: b.id, course_name: b.course_name }));
    }
    drawPaidBatchesGrid(mergedCourses);
}

async function renderFreeBatches(forceRefresh = false) {
    if (!enforceCompulsoryLogin()) return;
    state.view = "batches";
    document.getElementById("subTabs").classList.add("hidden"); toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = "Free Portal";
    document.getElementById("headingText").textContent = "🆓 RWA Free Batches";
    const grid = document.getElementById("mainGrid"), primaryTok = USER_TOKENS[0];
    let list = !forceRefresh ? readLocalCache(CACHE_KEYS.FREE_BATCHES) : null;
    if (!list) {
        renderSkeletonCards(grid, 6);
        const freeData = await fetchAPIWithToken(`/get/courselist?start=-1`, primaryTok, () => DB.freeBatches);
        list = (Array.isArray(freeData) && freeData.length > 0) ? freeData : DB.freeBatches;
        writeLocalCache(CACHE_KEYS.FREE_BATCHES, list);
    }
    grid.innerHTML = list.map(c => {
        const cid = String(c.id || "free_101"), name = (c.course_name || "Free Course").replace(/'/g, "");
        const logo = c.exam_logo || c.course_thumbnail || "https://placehold.co/600x320/059669/ffffff?text=Free+Batch";
        state.courseTokenMap[cid] = primaryTok;
        return `<div onclick="openFreeCourse('${cid}', '${name}')" class="grid-card overflow-hidden cursor-pointer flex flex-col justify-between"><img src="${logo}" onerror="this.src='https://placehold.co/600x320/059669/ffffff?text=Free+Batch'" class="w-full h-44 object-cover"><div class="p-4"><span class="px-2.5 py-0.5 rounded-full bg-teal-100 text-teal-800 text-[10px] font-black">FREE BATCH</span><h3 class="font-black text-base mt-2">${c.course_name || name}</h3><div class="btn-watch w-full text-center text-xs mt-3">Open Free Classes ➔</div></div></div>`;
    }).join("");
}

function openPaidCourse(id, name) {
    const cid = String(id).trim();
    state.cat = "paid"; state.courseId = cid; state.courseName = name;
    state.activeTokenObj = getCourseBoundToken(cid);
    window.ACTIVE_PLAYER_TOKEN = state.activeTokenObj ? state.activeTokenObj.token : "";
    if (typeof logUserActivity === "function") logUserActivity("OPEN_BATCH", `${name} (#${cid})`);
    document.getElementById("subTabs").classList.remove("hidden"); toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = `Batch #${cid}`;
    document.getElementById("headingText").textContent = name;
    pushNavHistoryState("subjects");
    loadCourseTab("subjects");
}

async function openFreeCourse(id, name) {
    const cid = String(id).trim(); state.cat = "free"; state.courseId = cid; state.courseName = name; state.view = "subjects";
    state.activeTokenObj = getCourseBoundToken(cid);
    document.getElementById("subTabs").classList.add("hidden"); toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = "Free Batch"; document.getElementById("headingText").textContent = name;
    renderSkeletonCards(document.getElementById("mainGrid"), 4);
    const subs = await fetchAPIWithToken(`/get/allsubjectfrmlivecourseclass?courseid=${cid}&start=-1`, state.activeTokenObj, () => DB.freeSubjects);
    document.getElementById("mainGrid").innerHTML = (subs.length ? subs : DB.freeSubjects).map(s => `<div onclick="openFreeTopics('${s.subjectid}', '${(s.subject_name || "Free Subject").replace(/'/g, "")}')" class="grid-card p-5 flex items-center justify-between cursor-pointer"><div><span class="text-[10px] font-extrabold text-teal-700 uppercase">Free Subject</span><h4 class="font-black text-base mt-0.5">📘 ${s.subject_name}</h4></div><span class="btn-watch text-xs">Topics ➔</span></div>`).join("");
}
async function openFreeTopics(subId, subName) {
    state.view = "topics"; state.subjectId = subId; state.subjectName = subName; toggleExplorerExtras(false);
    document.getElementById("headingText").textContent = subName;
    const topics = DB.freeTopics[subId] || [{ topicid: "ftop_1", topic_name: "All Classes" }];
    document.getElementById("mainGrid").innerHTML = topics.map(t => `<div onclick="openFreeLectures('${t.topicid}', '${t.topic_name}')" class="grid-card p-5 flex justify-between items-center cursor-pointer"><h4 class="font-black text-base">📂 ${t.topic_name}</h4><span class="btn-watch text-xs">Watch Classes ➔</span></div>`).join("");
}
function openFreeLectures(topId, topName) {
    state.view = "lectures"; state.topicId = topId; state.topicName = topName;
    document.getElementById("headingText").textContent = topName;
    renderLectureList(DB.freeLectures[topId] || [], state.activeTokenObj);
}

async function loadCourseTab(tab) {
    ["subjects", "live", "tests", "telegram"].forEach(t => { const el = document.getElementById("sub_" + t); if (el) el.className = (t === tab) ? "tab-pill active-pill" : "tab-pill"; });
    const grid = document.getElementById("mainGrid"); renderSkeletonCards(grid, 4);
    const batchTok = getCourseBoundToken(state.courseId); state.activeTokenObj = batchTok;

    if (tab === "subjects") {
        state.view = "subjects"; toggleExplorerExtras(false);
        const [liveSubs, vaultSubs] = await Promise.all([
            fetchAPIWithToken(`/get/allsubjectfrmlivecourseclass?courseid=${state.courseId}&start=-1`, batchTok, () => []),
            fetchCourseVaultSubjects(state.courseId)
        ]);
        const vMap = {}; vaultSubs.forEach(vs => { vMap[String(vs.subjectid || vs.subject_id)] = vs; });
        const seen = new Set(), merged = [];
        [...(Array.isArray(liveSubs) ? liveSubs : []), ...vaultSubs].forEach(s => {
            const sid = String(s.subjectid || s.subject_id || "").trim();
            if (sid && !seen.has(sid)) {
                seen.add(sid);
                const vs = vMap[sid] || {};
                merged.push({ ...s, subjectid: sid, subject_logo: vs.drive_logo_url || s.subject_logo || vs.subject_logo || "" });
            }
        });
        const finalSubs = merged.length ? merged : DB.paidSubjects;
        grid.innerHTML = finalSubs.map(s => {
            const name = s.subject_name || s.subjectname || "Subject";
            const logo = s.subject_logo || `https://placehold.co/80x80/0284c7/ffffff?text=${encodeURIComponent(name.slice(0, 3))}`;
            return `<div onclick="openPaidTopics('${s.subjectid}', '${name.replace(/'/g, "")}')" class="grid-card p-4 flex items-center gap-4 cursor-pointer"><img src="${logo}" onerror="this.src='https://placehold.co/80x80/0284c7/ffffff?text=SUB'" class="w-16 h-16 rounded-2xl object-cover shadow-md"><div class="flex-1"><span class="px-2 py-0.5 rounded bg-sky-100 text-sky-800 text-[10px] font-black">SUBJECT #${s.subjectid}</span><h4 class="font-black text-base mt-1">${name}</h4><p class="text-xs text-blue-600 font-extrabold mt-1">Explore Topics ➔</p></div></div>`;
        }).join("");
    } else if (tab === "live") {
        const res = await fetchAPIWithToken(`/get/live_upcoming_course_classv2?courseid=${state.courseId}&start=-1`, batchTok, () => ({ upcoming: [] }));
        renderLectureList(Array.isArray(res) ? res : (res.upcoming || res.live || []), batchTok);
    } else if (tab === "tests") {
        state.view = "batch_ts_subjects"; toggleExplorerExtras(false);
        const tsId = state.courseTestSeriesMap[state.courseId] || "700";
        state.activeSeriesId = tsId; state.activeSeriesTitle = `${state.courseName} - Batch Tests`;
        const [liveSubs, vaultSubs] = await Promise.all([
            fetchAPIWithToken(`/get/testseries_subjects?testseries_id=${tsId}`, batchTok, () => []),
            fetchVaultFoldersFallback(tsId)
        ]);
        const seen = new Set(), subList = [];
        [...(Array.isArray(liveSubs) ? liveSubs : []), ...(Array.isArray(vaultSubs) ? vaultSubs : []), ...(DB.tsSubjects["700"] || [])].forEach(s => {
            const sid = s && String(s.subjectid || s.subject_id || "").trim();
            if (sid && !seen.has(sid)) { seen.add(sid); subList.push({ ...s, subjectid: sid }); }
        });
        if (subList.length === 1 && String(subList[0].subjectid) === "-1") { openBatchInternalTests(tsId, "-1", `${state.courseName} - Mock Tests`); return; }
        grid.innerHTML = subList.map(s => `<div onclick="openBatchInternalTests('${tsId}', '${s.subjectid}', '${(s.subject_name || "Batch Test").replace(/'/g, "")}')" class="grid-card p-5 flex items-center justify-between cursor-pointer"><div><span class="px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-800 text-[10px] font-black">SERIES #${tsId}</span><h4 class="font-black text-base mt-1.5">📝 ${s.subject_name}</h4></div><span class="btn-watch text-xs">Open ➔</span></div>`).join("");
    } else if (tab === "telegram") {
        toggleExplorerExtras(false);
        grid.innerHTML = `<div class="col-span-full grid-card p-6 flex flex-wrap justify-between items-center gap-4"><div><span class="text-xs font-black text-blue-600 uppercase">Official Community</span><h4 class="font-black text-lg">✈️ RWA Batch Doubt Group</h4></div><a href="https://t.me/+ACPxjpf6oKQxM2U1" target="_blank" class="btn-watch text-xs no-underline px-5 py-3">Join Telegram ➔</a></div>`;
    }
}

async function openBatchInternalTests(tsId, subId, subName) {
    state.view = "batch_ts_tests"; state.activeSeriesId = tsId; state.activeTsSubId = subId; state.activeTsSubName = subName;
    toggleExplorerExtras(false); document.getElementById("headingText").textContent = `📝 ${subName}`;
    const batchTok = getCourseBoundToken(state.courseId); state.activeTokenObj = batchTok;
    const uid = batchTok.userId || extractUidFromJwt(batchTok.token) || "4756316";
    renderSkeletonCards(document.getElementById("mainGrid"), 6);
    const [liveList, vaultList] = await Promise.all([
        fetchAPIWithToken(`/get/test_titlev2?testseriesid=${tsId}&subject_id=${subId}&chapter_id=-1&userid=${uid}&search=&start=-1`, batchTok, () => []),
        fetchVaultTitlesFallback(tsId, subId)
    ]);
    const seen = new Set(), merged = [];
    [...(Array.isArray(liveList) ? liveList : []), ...(Array.isArray(vaultList) ? vaultList : [])].forEach(t => {
        const tid = t && String(t.id || t.test_id || "").trim();
        if (tid && !seen.has(tid)) { seen.add(tid); merged.push({ ...t, id: tid }); }
    });
    renderTestTitlesGrid(merged, tsId, batchTok);
}

async function openPaidTopics(subId, subName) {
    state.view = "topics"; state.subjectId = subId; state.subjectName = subName;
    document.getElementById("subTabs").classList.add("hidden"); toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = state.courseName; document.getElementById("headingText").textContent = `📂 ${subName}`;
    const batchTok = getCourseBoundToken(state.courseId); state.activeTokenObj = batchTok;
    renderSkeletonCards(document.getElementById("mainGrid"), 6);

    const [liveTopics, vaultTopics] = await Promise.all([
        fetchAPIWithToken(`/get/alltopicfrmlivecourseclass?courseid=${state.courseId}&subjectid=${subId}&start=-1`, batchTok, () => []),
        fetchCourseVaultTopics(state.courseId, subId)
    ]);
    const seen = new Set(), topics = [];
    [...(Array.isArray(liveTopics) ? liveTopics : []), ...vaultTopics].forEach(t => {
        const tid = String(t.topicid || t.topic_id || "").trim();
        if (tid && !seen.has(tid)) { seen.add(tid); topics.push({ ...t, topicid: tid }); }
    });
    document.getElementById("mainGrid").innerHTML = (topics.length ? topics : (DB.paidTopics[subId] || [])).map(t => {
        const name = (t.topic_name || t.topicname || "Topic").replace(/'/g, "");
        return `<div onclick="openPaidLectures('${t.topicid}', '${name}')" class="grid-card p-5 flex justify-between items-center cursor-pointer"><div><span class="text-[10px] font-bold text-sky-700 uppercase">Topic Folder</span><h4 class="font-black text-base mt-0.5">📁 ${name}</h4></div><span class="btn-watch text-xs">Classes ➔</span></div>`;
    }).join("");
}

async function openPaidLectures(topId, topName) {
    state.view = "lectures"; state.topicId = topId; state.topicName = topName;
    document.getElementById("crumbText").textContent = state.subjectName; document.getElementById("headingText").textContent = `🎬 ${topName}`;
    const batchTok = getCourseBoundToken(state.courseId); state.activeTokenObj = batchTok;
    renderSkeletonCards(document.getElementById("mainGrid"), 6);

    const [liveClasses, vaultClasses] = await Promise.all([
        fetchAPIWithToken(`/get/livecourseclassbycoursesubtopconceptapiv3?courseid=${state.courseId}&subjectid=${state.subjectId}&topicid=${topId}&conceptid=1&start=0`, batchTok, () => []),
        fetchCourseVaultLectures(state.courseId, state.subjectId, topId)
    ]);

    const vMap = {}; vaultClasses.forEach(vl => { vMap[String(vl.lecture_id || vl.id)] = vl; });
    const seen = new Set(), merged = [];
    (Array.isArray(liveClasses) ? liveClasses : []).forEach(lc => {
        const lid = String(lc.id || "").trim();
        if (lid && !seen.has(lid)) {
            seen.add(lid);
            const vl = vMap[lid] || {};
            merged.push({
                ...lc,
                yt_video_id: vl.yt_video_id || "",
                drive_pdf1_url: vl.drive_pdf1_url || "",
                drive_pdf2_url: vl.drive_pdf2_url || "",
                drive_thumb_url: vl.drive_thumb_url || "",
                playback_mode: vl.playback_mode || state.courseModeMap[state.courseId] || "vault_first"
            });
        }
    });
    vaultClasses.forEach(vl => {
        const lid = String(vl.lecture_id || vl.id || "").trim();
        if (lid && !seen.has(lid)) {
            seen.add(lid);
            merged.push({ ...vl, id: lid, Title: vl.title || `Class #${lid}` });
        }
    });

    renderLectureList(merged.length ? merged : (DB.paidLectures[topId] || []), batchTok);
}

function normalizeQualityLabel(rawLabel) {
    const s = String(rawLabel || "").toLowerCase();
    for (const q of ["1080", "720", "480", "360", "240", "144"]) { if (s.includes(q)) return q + "p"; }
    return "";
}

function extractQualitiesFromItem(item) {
    const rawMap = {};
    function addCandidate(rawQual, encPath, isM3u8Priority) {
        let u = decryptAppX(encPath);
        if (!u || !u.startsWith("http") || u.includes("playlist_eof.m3u8")) return;
        let cleanQ = normalizeQualityLabel(rawQual);
        if (!cleanQ) {
            const m = u.match(/\/(720p|480p|360p|240p|144p)\//i) || u.match(/bitrate=(720|480|360|240)/i);
            cleanQ = m ? (m[1].toLowerCase().endsWith("p") ? m[1].toLowerCase() : `${m[1]}p`) : "720p";
        }
        if (!rawMap[cleanQ] || isM3u8Priority || u.includes(".m3u8")) rawMap[cleanQ] = u;
    }
    (item.encrypted_links || []).forEach(q => addCandidate(q.quality, q.path, true));
    (item.livestream_links || []).forEach(q => addCandidate(q.quality, q.path, true));
    (item.download_links || []).forEach(q => addCandidate(q.quality, q.path, false));
    const decFile = decryptAppX(item.file_link || "");
    if (decFile) {
        if (decFile.startsWith("http") && !decFile.includes("playlist_eof.m3u8")) addCandidate("720p", decFile, decFile.includes(".m3u8"));
        else if (!decFile.startsWith("http") && decFile.length >= 10 && decFile.length <= 15) rawMap["720p"] = decFile;
    }
    const sorted = {};
    ["1080p", "720p", "480p", "360p", "240p", "144p"].forEach(k => { if (rawMap[k]) sorted[k] = rawMap[k]; });
    Object.keys(rawMap).forEach(k => { if (!sorted[k]) sorted[k] = rawMap[k]; });
    return sorted;
}

function renderLectureList(list, boundTokenObj, filterMode = "all") {
    const grid = document.getElementById("mainGrid");
    state.lastRenderedLectures = list || []; state.activeExplorerFilter = filterMode;
    const lectureTok = boundTokenObj || getCourseBoundToken(state.courseId);
    if (!list || !list.length) { toggleExplorerExtras(false); grid.innerHTML = `<div class="col-span-full sky-card p-10 text-center font-bold opacity-70">Is folder mein abhi koi class nahi hai.</div>`; return; }

    let completedCount = 0;
    const prepared = list.map((item, i) => {
        const key = `lec_${item.id || i}`;
        const qMap = extractQualitiesFromItem(item);
        // Prefer Google Drive PDFs when archived!
        const pdf1 = item.drive_pdf1_url || resolvePdfUrl(item.pdf_link || item.ypdf_link, item.ypdf_link2);
        const pdf2 = item.drive_pdf2_url || resolvePdfUrl(item.pdf_link2, item.ypdf_link2);
        const thumb = item.drive_thumb_url || item.thumbnail || "";
        const prog = typeof getWatchProgress === "function" ? getWatchProgress(key) : null;
        const pct = prog ? (prog.pct || 0) : 0;
        if (pct >= 90) completedCount++;
        const mediaObj = {
            key, id: item.id, courseId: state.courseId, tokenObj: lectureTok,
            title: item.Title || item.title || "Class Lecture",
            date: item.date_and_time || "", thumb,
            qualities: qMap, pdf1, pdf2,
            yt_video_id: item.yt_video_id || "",
            playback_mode: item.playback_mode || "vault_first",
            _pct: pct
        };
        state.mediaMap[key] = mediaObj;
        return mediaObj;
    });

    state.currentLectureKeys = prepared.map(x => x.key);
    toggleExplorerExtras(true, `📊 Topic Progress: ${completedCount} / ${prepared.length} Classes Completed (${Math.round((completedCount / prepared.length) * 100)}%)`);

    let displayList = [...prepared];
    if (filterMode === "unwatched") displayList = displayList.filter(x => x._pct < 5);
    else if (filterMode === "inprogress") displayList = displayList.filter(x => x._pct >= 5 && x._pct < 90);
    else if (filterMode === "completed") displayList = displayList.filter(x => x._pct >= 90);
    else if (filterMode === "haspdf") displayList = displayList.filter(x => x.pdf1 || x.pdf2);
    else if (filterMode === "newest") displayList.reverse();

    grid.innerHTML = displayList.length ? displayList.map((info, idx) => {
        const pct = info._pct;
        const statusBadge = pct >= 90 ? `<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black">✅ Watched</span>` : (pct >= 5 ? `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-black">⏳ ${pct}%</span>` : "");
        const cloudBadge = (info.yt_video_id && info.playback_mode !== "hls_live") ? `<span class="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-[10px] font-black">☁️ Fast HD</span>` : "";
        return `
            <div class="grid-card overflow-hidden flex flex-col justify-between">
                <div>
                    ${info.thumb ? `<div class="relative"><img src="${info.thumb}" onerror="this.style.display='none'" class="w-full h-44 object-cover">${pct > 0 ? `<div class="absolute bottom-0 left-0 right-0 h-1.5 bg-black/40"><div class="h-full bg-sky-400" style="width:${pct}%"></div></div>` : ""}</div>` : ""}
                    <div class="p-4">
                        <div class="flex justify-between items-center gap-1.5 flex-wrap">
                            <span class="px-2.5 py-0.5 rounded-full bg-sky-100 text-sky-900 text-[10px] font-black">CLASS #${info.id || (idx + 1)}</span>
                            <div class="flex gap-1">${cloudBadge}${statusBadge}</div>
                        </div>
                        <h4 class="font-black text-base mt-2">${info.title}</h4>
                        ${info.date ? `<p class="text-[11px] opacity-65 font-semibold mt-1">🕒 ${info.date}</p>` : ""}
                    </div>
                </div>
                <div class="p-4 pt-2 border-t border-sky-100 dark:border-slate-700 flex flex-wrap gap-2">
                    <button onclick="playClassInRwaPlayer('${info.key}')" class="btn-watch flex-1 text-xs">${pct >= 5 && pct < 90 ? "▶ Resume" : "▶ Watch Video"}</button>
                    ${info.pdf1 ? `<button onclick="openPdf('${info.key}', 1)" class="btn-pdf1 text-xs">📄 PDF 1</button>` : ""}
                    ${info.pdf2 ? `<button onclick="openPdf('${info.key}', 2)" class="btn-pdf2 text-xs">📄 PDF 2</button>` : ""}
                </div>
            </div>`;
    }).join("") : `<div class="col-span-full sky-card p-8 text-center text-xs font-bold opacity-70">Is filter mein koi class match nahi hui.</div>`;
}
window.applyExplorerFilter = function(mode, btn) {
    document.querySelectorAll("#explorerFilterBar .filter-chip").forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    renderLectureList(state.lastRenderedLectures, state.activeTokenObj, mode);
};

// =====================================================
// HYBRID PLAYER ROUTER (YOUTUBE UNLISTED FIRST -> LIVE HLS FALLBACK)
// =====================================================
async function playClassInRwaPlayer(key) {
    state.activeKey = key;
    const info = state.mediaMap[key]; if (!info) return;
    const targetCourseId = info.courseId || state.courseId;
    const batchTok = info.tokenObj || getCourseBoundToken(targetCourseId);
    state.activeTokenObj = batchTok;
    window.ACTIVE_PLAYER_TOKEN = batchTok ? batchTok.token : "";

    showSlide("slidePlayer");
    document.getElementById("playingTitle").textContent = "▶ " + info.title;
    if (typeof logUserActivity === "function") logUserActivity("PLAY_CLASS", info.title);
    if (typeof renderVideoNotesForKey === "function") renderVideoNotesForKey(key);
    if (typeof updatePinButtonUI === "function") updatePinButtonUI(key);

    closeInlinePdfAndReset();
    renderNextClassesBelowPlayer(key);

    document.getElementById("playerPdf1")?.classList.toggle("hidden", !info.pdf1);
    document.getElementById("playerPdf2")?.classList.toggle("hidden", !info.pdf2);

    const urlInput = document.getElementById("url");

    // 1. Check Course Vault (YouTube Unlisted + Drive PDFs) FIRST for ₹0 Bandwidth Cost!
    if (!info.yt_video_id && info.id && isCourseVaultConfigured()) {
        const cvLec = await fetchCourseVaultSingleLecture(info.id);
        if (cvLec) {
            if (cvLec.yt_video_id) info.yt_video_id = cvLec.yt_video_id;
            if (cvLec.playback_mode) info.playback_mode = cvLec.playback_mode;
            if (cvLec.drive_pdf1_url) { info.pdf1 = cvLec.drive_pdf1_url; document.getElementById("playerPdf1")?.classList.remove("hidden"); }
            if (cvLec.drive_pdf2_url) { info.pdf2 = cvLec.drive_pdf2_url; document.getElementById("playerPdf2")?.classList.remove("hidden"); }
        }
    }

    if (info.yt_video_id && info.playback_mode !== "hls_live" && urlInput) {
        urlInput.value = info.yt_video_id;
        if (typeof start === "function") start();
        return;
    }

    // 2. Automatic Live HLS Fallback (for brand-new classes not yet uploaded by Termux)
    if (state.cat === "paid" && info.id) {
        const videoEp = `/get/fetchVideoDetailsById?course_id=${targetCourseId}&video_id=${info.id}&ytflag=0&folder_wise_course=0&lc_app_api_url=`;
        let fresh = await fetchAPIWithToken(videoEp, batchTok, () => null);
        let freshMap = (fresh && typeof fresh === "object") ? extractQualitiesFromItem(fresh) : {};
        if (Object.keys(freshMap).length === 0 && Object.keys(info.qualities || {}).length === 0) {
            for (const fbTok of await getAllTokensForCourses()) {
                if (batchTok && fbTok.token === batchTok.token) continue;
                const retryFresh = await fetchAPIWithToken(videoEp, fbTok, () => null);
                if (retryFresh && typeof retryFresh === "object") {
                    const retryMap = extractQualitiesFromItem(retryFresh);
                    if (Object.keys(retryMap).length > 0) {
                        fresh = retryFresh; freshMap = retryMap; info.tokenObj = fbTok;
                        state.courseTokenMap[targetCourseId] = fbTok; state.activeTokenObj = fbTok;
                        window.ACTIVE_PLAYER_TOKEN = fbTok.token; break;
                    }
                }
            }
        }
        if (fresh && typeof fresh === "object") {
            info.qualities = { ...info.qualities, ...freshMap };
            const fPdf1 = resolvePdfUrl(fresh.pdf_link || fresh.ypdf_link, fresh.ypdf_link2);
            const fPdf2 = resolvePdfUrl(fresh.pdf_link2, fresh.ypdf_link2);
            if (fPdf1 && !info.pdf1) { info.pdf1 = fPdf1; document.getElementById("playerPdf1")?.classList.remove("hidden"); }
            if (fPdf2 && !info.pdf2) { info.pdf2 = fPdf2; document.getElementById("playerPdf2")?.classList.remove("hidden"); }
        }
    }

    const validKeys = Object.keys(info.qualities || {}).filter(k => info.qualities[k] && !info.qualities[k].includes("playlist_eof.m3u8"));
    if (validKeys.length > 0 && urlInput) {
        const bestKey = validKeys.find(k => k === "720p") || validKeys[0];
        urlInput.value = info.qualities[bestKey];
        if (state.activeTokenObj) { urlInput.dataset.token = state.activeTokenObj.token; urlInput.dataset.userid = state.activeTokenObj.userId || "4756316"; }
        if (typeof start === "function") start();
    } else if (typeof proToast === "function") proToast("⚠️ Video link fetch nahi ho paya.", "warning");
}

function renderNextClassesBelowPlayer(activeKey) {
    const grid = document.getElementById("nextClassesGrid"), countBadge = document.getElementById("nextClassesCount");
    if (!grid) return;
    const allKeys = state.currentLectureKeys || [], curIdx = allKeys.indexOf(activeKey);
    const ordered = curIdx >= 0 ? [...allKeys.slice(curIdx + 1), ...allKeys.slice(0, curIdx)] : allKeys.filter(k => k !== activeKey);
    if (countBadge) countBadge.textContent = `${ordered.length} Classes`;
    grid.innerHTML = ordered.length ? ordered.map((k, idx) => {
        const item = state.mediaMap[k]; if (!item) return "";
        return `<div class="grid-card p-3.5 flex flex-col justify-between"><div class="flex items-start gap-3"><div class="w-10 h-10 rounded-xl bg-sky-100 text-sky-800 font-black text-xs flex items-center justify-center shrink-0">#${idx + 1}</div><div class="min-w-0 flex-1"><span class="text-[10px] font-black text-sky-700 uppercase">Up Next</span><h5 class="font-extrabold text-sm line-clamp-2 mt-0.5">${item.title}</h5></div></div><div class="flex gap-2 mt-3 pt-2 border-t border-sky-100 dark:border-slate-700"><button onclick="playClassInRwaPlayer('${k}')" class="btn-watch flex-1 text-xs py-2">▶ Play Next</button>${item.pdf1 ? `<button onclick="openInlinePdfForKey('${k}', 1)" class="btn-pdf1 text-xs py-2">📄 PDF</button>` : ""}</div></div>`;
    }).join("") : `<div class="col-span-full py-6 text-center text-xs font-bold opacity-65">Is topic mein yeh aakhri class hai.</div>`;
}

// GOOGLE DRIVE NATIVE PDF PREVIEW + APPX VIEWER
function buildPdfViewerSrc(u, mode) {
    if (!u) return "";
    if (u.includes("drive.google.com/file/d/")) return u;
    return mode === "appx"
        ? `https://pdfweb.classx.co.in/pdfjs-latest/web/viewer.html?file=${encodeURIComponent(u)}&save_flag=1&is_encrypted=0`
        : `https://docs.google.com/viewer?url=${encodeURIComponent(u)}&embedded=true`;
}

function buildPdfDownloadUrl(u) {
    const m = String(u || "").match(/drive\.google\.com\/file\/d\/([^/]+)/);
    return m ? `https://drive.google.com/uc?export=download&id=${m[1]}` : u;
}

window.openActivePlayerPdf = function(num) { if (state.activeKey) openInlinePdfForKey(state.activeKey, num); };
window.openInlinePdfForKey = function(key, num) {
    if (window.PORTAL_KILL_SWITCHES && window.PORTAL_KILL_SWITCHES.pdf_viewer === false) return proToast("PDF Viewer temporarily paused.", "warning");
    const info = state.mediaMap[key]; if (!info) return;
    const u = num === 2 ? info.pdf2 : info.pdf1; if (!u) return;
    state.inlinePdfUrl = u;
    document.getElementById("inlinePdfTitle").textContent = `📄 ${info.title} (PDF ${num})`;
    document.getElementById("inlineRawPdfLink").href = buildPdfDownloadUrl(u);
    document.getElementById("inlinePdfBox").classList.remove("hidden");
    setInlinePdfMode("appx");
    if (typeof logUserActivity === "function") logUserActivity("OPEN_PDF", `${info.title} (Inline)`);
    document.getElementById("inlinePdfBox").scrollIntoView({ behavior: "smooth" });
};
window.setInlinePdfMode = function(mode) {
    const f = document.getElementById("inlinePdfFrame"); if (f && state.inlinePdfUrl) f.src = buildPdfViewerSrc(state.inlinePdfUrl, mode);
};
window.switchBottomToNextClasses = function() { closeInlinePdfAndReset(); };
function closeInlinePdfAndReset() {
    const f = document.getElementById("inlinePdfFrame"); if (f) f.src = "";
    document.getElementById("inlinePdfBox")?.classList.add("hidden");
    document.getElementById("playerSplitContainer")?.classList.remove("split-active");
}
function changeLectureQuality(qLabel) {
    const info = state.mediaMap[state.activeKey];
    if (info && info.qualities[qLabel]) {
        const urlInput = document.getElementById("url");
        urlInput.value = info.qualities[qLabel];
        if (info.tokenObj) { urlInput.dataset.token = info.tokenObj.token; window.ACTIVE_PLAYER_TOKEN = info.tokenObj.token; }
        if (typeof start === "function") start();
    }
}

// =====================================================
// TEST SERIES EXPLORER (LIVE + READ-ONLY TEST VAULT MERGE)
// =====================================================
async function openTestSeriesExplorer(mode, forceRefresh = false) {
    if (window.PORTAL_KILL_SWITCHES && window.PORTAL_KILL_SWITCHES.paid_test_series === false && mode === "paid_ts") return proToast("Paid Test Series temporarily paused.", "warning");
    if (!enforceCompulsoryLogin()) return;
    state.tsMode = mode; state.view = "ts_list";
    showSlide("slideExplorer"); document.getElementById("subTabs").classList.add("hidden"); toggleExplorerExtras(false);
    const grid = document.getElementById("mainGrid"), primaryTok = USER_TOKENS[0]; state.activeTokenObj = primaryTok;
    const isPaid = mode === "paid_ts";
    document.getElementById("crumbText").textContent = isPaid ? "Official Exam Series" : "Weekly Mock Tests";
    document.getElementById("headingText").textContent = isPaid ? "🏆 Paid Test Series" : "📝 Free Test Series";
    const cacheKey = isPaid ? CACHE_KEYS.PAID_TS : CACHE_KEYS.FREE_TS;
    let combined = !forceRefresh ? readLocalCache(cacheKey) : null;

    if (!combined) {
        renderSkeletonCards(grid, 6);
        const epBase = isPaid ? "/get/test_series?start=" : "/get/quiz_test_series?start=";
        const suffix = isPaid ? "&search=&client_api_url=&exam_id=" : "&exam_id=";
        const [p0, p10, p20, vaultSeries] = await Promise.all([
            fetchAPIWithToken(`${epBase}0${suffix}`, primaryTok, () => []),
            fetchAPIWithToken(`${epBase}10${suffix}`, primaryTok, () => []),
            fetchAPIWithToken(`${epBase}20${suffix}`, primaryTok, () => []),
            isPaid ? fetchVaultSeriesFallback() : Promise.resolve([])
        ]);
        const liveArr = [...(Array.isArray(p0) ? p0 : []), ...(Array.isArray(p10) ? p10 : []), ...(Array.isArray(p20) ? p20 : [])];
        const liveIds = new Set(liveArr.map(x => String(x && x.id || "")));
        const vaultOnly = (Array.isArray(vaultSeries) ? vaultSeries : []).filter(vs => vs && !liveIds.has(String(vs.series_id || vs.id || ""))).map(vs => ({ ...vs, id: String(vs.series_id || vs.id), _fromVaultOnly: true }));
        const seen = new Set(); combined = [];
        [...liveArr, ...vaultOnly, ...(isPaid ? DB.paidTestSeries : DB.freeTestSeries)].forEach(ts => {
            const sid = ts && String(ts.id || ts.series_id || "").trim();
            if (sid && !seen.has(sid)) { seen.add(sid); combined.push({ ...ts, id: sid }); }
        });
        writeLocalCache(cacheKey, combined);
    }

    if (window.PRO_STORE) PRO_STORE.search_cache.testSeries = combined.map(x => ({ id: x.id, title: x.title }));
    grid.innerHTML = combined.map(ts => {
        const title = (ts.title || "Test Series").replace(/'/g, "");
        const logo = (ts.logo || "https://placehold.co/600x320/4f46e5/ffffff?text=Test+Series").replace(/\\\//g, "/");
        return `<div onclick="openTestSeriesSubjects('${ts.id}', '${title}')" class="grid-card overflow-hidden cursor-pointer flex flex-col justify-between"><div><img src="${logo}" onerror="this.src='https://placehold.co/600x320/4f46e5/ffffff?text=RWA+Test+Series'" class="w-full h-44 object-cover"><div class="p-4"><div class="flex justify-between items-center gap-1.5 flex-wrap"><span class="px-2.5 py-0.5 rounded-full ${isPaid ? "bg-indigo-100 text-indigo-900" : "bg-teal-100 text-teal-900"} text-[10px] font-black">${isPaid ? "SERIES" : "FREE SERIES"} #${ts.id}</span>${ts._fromVaultOnly ? `<span class="px-2 py-0.5 rounded-full bg-sky-100 text-sky-900 text-[10px] font-black">☁️ Cloud Archive</span>` : ""}</div><h3 class="font-black text-base mt-2">${ts.title}</h3></div></div><div class="px-4 pb-4"><div class="btn-watch w-full text-center text-xs">${isPaid ? "Open Test Subjects ➔" : "View All Mock Tests ➔"}</div></div></div>`;
    }).join("");
}

async function openTestSeriesSubjects(tsId, tsTitle) {
    state.activeSeriesId = tsId; state.activeSeriesTitle = tsTitle; state.view = "ts_subjects"; toggleExplorerExtras(false);
    document.getElementById("crumbText").textContent = `Test Series #${tsId}`; document.getElementById("headingText").textContent = tsTitle;
    const grid = document.getElementById("mainGrid"); renderSkeletonCards(grid, 4);
    const useTok = state.activeTokenObj || USER_TOKENS[0];
    fetchRawJSONWithToken(`/Test_Series/test_series_by_id?id=${tsId}`, useTok);
    const [liveSubs, vaultSubs] = await Promise.all([
        fetchAPIWithToken(`/get/testseries_subjects?testseries_id=${tsId}`, useTok, () => DB.tsSubjects[tsId] || []),
        fetchVaultFoldersFallback(tsId)
    ]);
    const seen = new Set(), subs = [];
    [...(Array.isArray(liveSubs) ? liveSubs : []), ...(Array.isArray(vaultSubs) ? vaultSubs : [])].forEach(s => {
        const sid = s && String(s.subjectid || s.subject_id || "").trim();
        if (sid && !seen.has(sid)) { seen.add(sid); subs.push({ ...s, subjectid: sid }); }
    });
    if (!subs.length || (subs.length === 1 && String(subs[0].subjectid) === "-1")) { openTestSeriesTitles(tsId, "-1", tsTitle); return; }
    grid.innerHTML = subs.map(s => {
        const sname = (s.subject_name || "Mock Tests").replace(/'/g, "");
        const logo = (s.subject_logo || `https://placehold.co/80x80/4f46e5/ffffff?text=${encodeURIComponent(sname.slice(0, 3))}`).replace(/\\\//g, "/");
        return `<div onclick="openTestSeriesTitles('${tsId}', '${s.subjectid}', '${sname}')" class="grid-card p-4 flex items-center gap-4 cursor-pointer"><img src="${logo}" onerror="this.src='https://placehold.co/80x80/4f46e5/ffffff?text=TEST'" class="w-16 h-16 rounded-2xl object-cover shadow-md"><div class="flex-1"><span class="px-2 py-0.5 rounded bg-indigo-100 text-indigo-900 text-[10px] font-black">SUBJECT #${s.subjectid}</span><h4 class="font-black text-base mt-1">${s.subject_name}</h4><p class="text-xs text-blue-600 font-extrabold mt-1">Open Mock Tests ➔</p></div></div>`;
    }).join("");
}

async function openTestSeriesTitles(tsId, subId, subName) {
    state.view = "ts_tests"; state.activeSeriesId = tsId; state.activeTsSubId = String(subId); state.activeTsSubName = subName;
    toggleExplorerExtras(false); document.getElementById("crumbText").textContent = state.activeSeriesTitle; document.getElementById("headingText").textContent = `📝 ${subName}`;
    renderSkeletonCards(document.getElementById("mainGrid"), 6);
    const useTok = state.activeTokenObj || USER_TOKENS[0], uid = useTok.userId || extractUidFromJwt(useTok.token) || "4756316";
    let [liveList, vaultList] = await Promise.all([
        fetchAPIWithToken(`/get/test_titlev2?testseriesid=${tsId}&subject_id=${subId}&chapter_id=-1&userid=${uid}&search=&start=-1`, useTok, () => []),
        fetchVaultTitlesFallback(tsId, subId)
    ]);
    if ((!liveList || !liveList.length) && String(subId) !== "-1") liveList = await fetchAPIWithToken(`/get/test_titlev2?testseriesid=${tsId}&subject_id=${subId}&userid=${uid}&search=&start=-1`, useTok, () => []);
    const seen = new Set(), merged = [];
    [...(Array.isArray(liveList) ? liveList : []), ...(Array.isArray(vaultList) ? vaultList : [])].forEach(t => {
        const tid = t && String(t.id || t.test_id || "").trim();
        if (tid && !seen.has(tid)) { seen.add(tid); merged.push({ ...t, id: tid }); }
    });
    renderTestTitlesGrid(merged, tsId, useTok);
}

function formatCardTimeLabel(rawTime) {
    const str = String(rawTime || "60").trim();
    return str.includes("+") ? `${str.split("+").reduce((a, n) => a + (parseInt(n.trim()) || 0), 0)} Mins (Sec)` : `${str} Mins`;
}

function renderTestTitlesGrid(list, tsId, boundTok) {
    const grid = document.getElementById("mainGrid"), testTok = boundTok || state.activeTokenObj || USER_TOKENS[0];
    if (!list || !list.length) { grid.innerHTML = `<div class="col-span-full sky-card p-10 text-center font-bold opacity-70">Is section mein abhi koi test uplabdh nahi hai.</div>`; return; }
    grid.innerHTML = list.map((t, idx) => {
        const tid = String(t.id || idx), tKey = `test_${tid}`;
        const pdfUrl = resolvePdfUrl(t.pdf_url || t.test_solutions_pdf || t.pdf_summary_link, t.pdf_url);
        state.testMap[tKey] = { ...t, id: tid, seriesId: tsId || t.test_series_id, resolvedPdf: pdfUrl, tokenObj: testTok };
        const hasPaused = typeof getPausedTestState === "function" && Boolean(getPausedTestState(tid));
        return `<div class="grid-card p-5 flex flex-col justify-between"><div><div class="flex justify-between items-center gap-2 flex-wrap"><span class="px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-900 text-[10px] font-black">TEST #${tid}</span><span class="text-[11px] font-extrabold text-emerald-700 dark:text-emerald-400">⏱️ ${formatCardTimeLabel(t.time)}</span></div><h4 class="font-black text-base mt-2">${t.title}</h4><div class="flex gap-2 mt-2 text-xs font-bold opacity-75 flex-wrap"><span>❓ ${t.questions || 50} Qs</span><span>🏆 ${t.marks || 100} Marks</span>${t.has_full_bank ? `<span class="text-sky-600 font-black">☁️ Vault</span>` : ""}${hasPaused ? `<span class="text-amber-600 font-black">⏸️ Paused</span>` : ""}</div></div><div class="flex flex-wrap gap-2 mt-4 pt-3 border-t border-sky-100 dark:border-slate-700"><button onclick="launchCbtTest('${tKey}')" class="btn-watch flex-1 text-xs">${hasPaused ? "▶ Resume / Attempt" : "🚀 Attempt Live Test"}</button>${pdfUrl ? `<button onclick="openTestPdf('${tKey}')" class="btn-pdf1 text-xs">📄 Test PDF</button>` : ""}</div></div>`;
    }).join("");
}

function openTestPdf(tKey) {
    if (window.PORTAL_KILL_SWITCHES && window.PORTAL_KILL_SWITCHES.pdf_viewer === false) return proToast("PDF Viewer temporarily paused.", "warning");
    const t = state.testMap[tKey]; if (!t || !t.resolvedPdf) return;
    state.currentPdfUrl = t.resolvedPdf;
    document.getElementById("pdfTitle").textContent = `📄 ${t.title} (Paper PDF)`;
    document.getElementById("rawPdfLink").href = buildPdfDownloadUrl(t.resolvedPdf);
    showSlide("slidePdf"); setPdfMode("appx");
}

async function launchCbtTest(tKey) { if (typeof window.launchTcsCbtEngine === "function") await window.launchTcsCbtEngine(tKey); }
function reAttemptCbtTest() { if (typeof window.reAttemptTcsTest === "function") window.reAttemptTcsTest(); }
function exitCbtTest() { if (typeof window.exitTcsTest === "function") window.exitTcsTest(); else showSlide("slideExplorer"); }

function openPdf(key, num) {
    if (window.PORTAL_KILL_SWITCHES && window.PORTAL_KILL_SWITCHES.pdf_viewer === false) return proToast("PDF Viewer temporarily paused.", "warning");
    const info = state.mediaMap[key]; if (!info) return;
    const u = num === 2 ? info.pdf2 : info.pdf1; if (!u) return;
    const vid = document.getElementById("video"); if (vid && !vid.paused) vid.pause();
    state.currentPdfUrl = u;
    document.getElementById("pdfTitle").textContent = `📄 ${info.title} (PDF ${num})`;
    document.getElementById("rawPdfLink").href = buildPdfDownloadUrl(u);
    if (typeof logUserActivity === "function") logUserActivity("OPEN_PDF", info.title);
    showSlide("slidePdf"); setPdfMode("appx");
}
function setPdfMode(mode) { const f = document.getElementById("pdfFrame"); if (f && state.currentPdfUrl) f.src = buildPdfViewerSrc(state.currentPdfUrl, mode); }
function closePdfSlide() { document.getElementById("pdfFrame").src = ""; showSlide(state.previousSlide || "slideExplorer"); }

function renderTokenManagerList() {
    const container = document.getElementById("tokenListContainer"); if (!container) return;
    if (!USER_TOKENS.length) { container.innerHTML = `<div class="p-4 text-center text-xs font-bold opacity-65">Abhi koi personal token saved nahi hai.</div>`; return; }
    container.innerHTML = USER_TOKENS.map((t, idx) => `<div class="bg-white dark:bg-slate-800 border-2 border-sky-200 dark:border-slate-700 rounded-2xl p-4 flex flex-wrap justify-between items-center gap-3 shadow-sm"><div class="min-w-0 flex-1"><div class="flex items-center gap-2"><span class="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-black">MY TOKEN #${idx + 1}</span><h5 class="font-extrabold text-sm truncate">${t.label}</h5><span class="text-xs opacity-65 font-bold">(UID: ${t.userId || "Auto"})</span></div><p class="text-[11px] font-mono opacity-75 mt-1 truncate">${t.token.slice(0, 32)}...${t.token.slice(-14)}</p></div><div class="flex items-center gap-2"><button onclick="navigator.clipboard.writeText('${t.token}'); proToast('📋 Token Copied!', 'success');" class="btn-nav bg-sky-600 text-white border-0 text-xs">📋 Copy</button>${USER_TOKENS.length > 1 ? `<button onclick="deleteToken('${t.id}')" class="btn-nav bg-rose-600 text-white border-0 text-xs">🗑 Delete</button>` : `<span class="text-[11px] font-bold text-emerald-600">● Primary</span>`}</div></div>`).join("");
    updateTokenBadge();
}

async function addNewToken() {
    const labelInput = document.getElementById("newTokLabel").value.trim();
    const uidInput = document.getElementById("newTokUid").value.trim();
    let token = document.getElementById("newTokValue").value.trim().replace(/^["']|["']$/g, "").replace(/^Authorization:\s*/i, "").trim();
    if (!token) return proToast("Kripya JWT Token paste karein.", "warning");
    const userId = uidInput || extractUidFromJwt(token);
    if (!userId) return proToast("Invalid JWT Token format!", "error");
    const verifiedUser = await fetchUserDetailsFromServer(token, userId);
    if (!verifiedUser) return proToast("Server verification failed!", "error");

    const newTokObj = { id: "utok_" + Date.now(), label: labelInput || verifiedUser.name || `Account ${USER_TOKENS.length + 1}`, userId: String(verifiedUser.userid || verifiedUser.id || userId), token, isAdmin: false };
    USER_TOKENS.push(newTokObj); USER_PROFILE = verifiedUser; window.USER_TOKENS = USER_TOKENS; window.USER_PROFILE = USER_PROFILE;
    localStorage.setItem("rwa_user_tokens_v2", JSON.stringify(USER_TOKENS));
    localStorage.setItem("rwa_user_profile_v2", JSON.stringify(USER_PROFILE));
    sendProfileToMongoDB(verifiedUser, token, "Added via Token Manager", "N/A", false);
    document.getElementById("newTokLabel").value = ""; document.getElementById("newTokUid").value = ""; document.getElementById("newTokValue").value = "";
    renderTokenManagerList(); proToast(`✅ Token Verified & Added!`, "success");
}

function deleteToken(id) {
    if (USER_TOKENS.length <= 1) return;
    USER_TOKENS = USER_TOKENS.filter(t => t.id !== id); window.USER_TOKENS = USER_TOKENS;
    localStorage.setItem("rwa_user_tokens_v2", JSON.stringify(USER_TOKENS));
    renderTokenManagerList(); proToast("🗑 Token removed.", "info");
}

function filterGrid() {
    const q = document.getElementById("searchBox").value.toLowerCase();
    document.querySelectorAll("#mainGrid .grid-card").forEach(el => { el.style.display = el.innerText.toLowerCase().includes(q) ? "" : "none"; });
}

// =====================================================
// BOOT INITIALIZATION
// =====================================================
updateTokenBadge();
if (isUserLoggedIn()) {
    syncAuthCookies(USER_TOKENS[0]);
    if (typeof window.rwaIsJwtExpired === "function" && window.rwaIsJwtExpired(USER_TOKENS[0].token, 30)) {
        handleLogout(true);
    } else {
        showSlide("slideHome");
        if (typeof checkPortalStatusAndNotices === "function") checkPortalStatusAndNotices();
        if (typeof pullCloudSyncData === "function") pullCloudSyncData(false);
        if (typeof startSkyLiveHeartbeat === "function") startSkyLiveHeartbeat();
        if (typeof renderHomeDashboard === "function") renderHomeDashboard();
        if (USER_PROFILE && !sessionStorage.getItem("rwa_sky_silent_sync")) {
            sessionStorage.setItem("rwa_sky_silent_sync", "1");
            sendProfileToMongoDB(USER_PROFILE, USER_TOKENS[0].token, "Session Auto-Sync", "N/A", true);
        }
    }
} else {
    openLoginModal();
    if (typeof checkPortalStatusAndNotices === "function") checkPortalStatusAndNotices();
}
checkIncomingChallengeUrl();

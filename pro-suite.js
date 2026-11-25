// =========================================================
// RWA SKY PRO - COACHING SUITE, VAULT & 4-MONGODB CLOUD SYNC
// =========================================================

const PRO_API_BASE = "https://pdfsownlaoder.onrender.com";
const PRO_STORE_KEY = "rwa_pro_suite_v1";

const DEFAULT_RAPID_QUIZ = [
    {
        q: "भारतीय संविधान के किस अनुच्छेद में 'मौलिक अधिकारों का संवैधानिक उपचार' (हृदय और आत्मा) वर्णित है?",
        opts: ["अनुच्छेद 14", "अनुच्छेद 19", "अनुच्छेद 32", "अनुच्छेद 51A"],
        ans: 2,
        exp: "डॉ. बी.आर. अम्बेडकर ने अनुच्छेद 32 को संविधान का हृदय और आत्मा कहा था।"
    },
    {
        q: "यदि 25 और 45 का तृतीय समानुपाती (Third Proportional) x है, तो x का मान क्या होगा?",
        opts: ["75", "81", "85", "90"],
        ans: 1,
        exp: "तृतीय समानुपाती = b² / a = (45 × 45) / 25 = 81."
    },
    {
        q: "सिंधु घाटी सभ्यता का प्रसिद्ध बंदरगाह नगर 'लोथल' वर्तमान में किस राज्य में स्थित है?",
        opts: ["राजस्थान", "पंजाब", "हरियाणा", "गुजरात"],
        ans: 3,
        exp: "लोथल गुजरात में भोगवा नदी के किनारे स्थित था।"
    },
    {
        q: "Choose the correct synonym of 'ABUNDANT':",
        opts: ["Scarce", "Plentiful", "Tiny", "Fragile"],
        ans: 1,
        exp: "'Abundant' means existing in large quantities; 'Plentiful' is its exact synonym."
    },
    {
        q: "कंप्यूटर में 'Ctrl + Shift + Esc' शॉर्टकट की का उपयोग किसके लिए किया जाता है?",
        opts: ["New Tab", "Task Manager", "System Shutdown", "File Explorer"],
        ans: 1,
        exp: "Ctrl + Shift + Esc सीधे Windows Task Manager को खोलता है।"
    }
];

function createEmptyProStore() {
    return {
        watch_history: {},
        video_notes: {},
        saved_library: { classes: [], pdfs: [] },
        bookmarks: [],
        mistake_bank: [],
        test_history: [],
        flashcards: [
            {
                id: "fc_default_1",
                subject: "Maths Trick",
                front: "a और b का तृतीय समानुपाती (Third Proportional) का सूत्र क्या है?",
                back: "Third Proportional = (b × b) / a",
                createdAt: new Date().toLocaleDateString()
            }
        ],
        planner_tasks: [],
        syllabus_progress: {},
        exam_countdown: { name: "SSC GD 2027", date: "" },
        study_stats: { dailyMinutes: {}, streak: 1, lastDate: "", totalMinutes: 0 },
        preferences: { theme: "sky", fontSize: 16, autoPlayNext: true },
        daily_quiz_history: {},
        paused_tests: {},
        search_cache: { batches: [], testSeries: [] }
    };
}

function loadProStore() {
    try {
        const raw = localStorage.getItem(PRO_STORE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            return {
                ...createEmptyProStore(),
                ...parsed,
                saved_library: {
                    classes: [],
                    pdfs: [],
                    ...(parsed.saved_library || {})
                },
                study_stats: {
                    dailyMinutes: {},
                    streak: 1,
                    lastDate: "",
                    totalMinutes: 0,
                    ...(parsed.study_stats || {})
                },
                preferences: {
                    theme: "sky",
                    fontSize: 16,
                    autoPlayNext: true,
                    ...(parsed.preferences || {})
                },
                search_cache: {
                    batches: [],
                    testSeries: [],
                    ...(parsed.search_cache || {})
                }
            };
        }
    } catch {}
    return createEmptyProStore();
}

window.PRO_STORE = loadProStore();
let _cloudSyncTimer = null;
let _deferredPwaPrompt = null;
let _activeVaultTab = "history";
let _flashcardIdx = 0;

// Pomodoro & Ambient Sound State
let _pomoState = {
    mode: "25",
    secondsLeft: 25 * 60,
    running: false,
    interval: null,
    audioCtx: null,
    noiseNode: null,
    soundOn: false
};

// =========================================================
// CORE HELPERS (TOAST, CONFIRM MODAL, ESCAPE, DATE)
// =========================================================
window.escHtml = function(str) {
    return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
};

window.todayKey = function() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
};

window.getActiveUserId = function() {
    try {
        if (typeof USER_TOKENS !== "undefined" && USER_TOKENS.length > 0) {
            return String(USER_TOKENS[0].userId || extractUidFromJwt(USER_TOKENS[0].token) || "");
        }
        const raw = localStorage.getItem("rwa_user_tokens_v2");
        if (raw) {
            const arr = JSON.parse(raw);
            if (Array.isArray(arr) && arr[0]) return String(arr[0].userId || "");
        }
    } catch {}
    return "";
};

window.getActiveUserName = function() {
    try {
        if (typeof USER_PROFILE !== "undefined" && USER_PROFILE && USER_PROFILE.name) {
            return USER_PROFILE.name;
        }
        const raw = localStorage.getItem("rwa_user_profile_v2");
        if (raw) {
            const p = JSON.parse(raw);
            if (p && p.name) return p.name;
        }
    } catch {}
    return "RWA Student";
};

window.proToast = function(msg, type = "info") {
    const cont = document.getElementById("toastContainer");
    if (!cont) return;
    const bgMap = {
        success: "bg-emerald-600",
        error: "bg-rose-600",
        warning: "bg-amber-600",
        info: "bg-blue-600"
    };
    const el = document.createElement("div");
    el.className = `pro-toast ${bgMap[type] || bgMap.info}`;
    el.textContent = msg;
    cont.appendChild(el);
    setTimeout(() => {
        el.style.opacity = "0";
        el.style.transition = "opacity 0.25s";
        setTimeout(() => el.remove(), 260);
    }, 3200);
};

window.proConfirm = function(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById("customConfirmModal");
        if (!modal) {
            resolve(window.confirm(message));
            return;
        }
        document.getElementById("confirmTitle").textContent = title || "Confirm";
        document.getElementById("confirmMsg").textContent = message || "Are you sure?";
        modal.classList.remove("hidden");

        const okBtn = document.getElementById("confirmOkBtn");
        const cancelBtn = document.getElementById("confirmCancelBtn");

        const cleanup = (ans) => {
            modal.classList.add("hidden");
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            resolve(ans);
        };
        okBtn.onclick = () => cleanup(true);
        cancelBtn.onclick = () => cleanup(false);
    });
};

function saveProStoreLocal(syncCloud = true) {
    try {
        localStorage.setItem(PRO_STORE_KEY, JSON.stringify(window.PRO_STORE));
    } catch {}
    if (syncCloud) scheduleCloudSync();
}

function scheduleCloudSync() {
    if (_cloudSyncTimer) clearTimeout(_cloudSyncTimer);
    _cloudSyncTimer = setTimeout(() => {
        pushCloudSyncNow(false);
    }, 4000);
}

// =========================================================
// 4-MONGODB CLOUD SYNC & LIVE ACTIVITY / ERROR LOGGING
// =========================================================
window.pushCloudSyncNow = async function(showFeedback = false) {
    const uid = getActiveUserId();
    if (!uid) return;
    const payload = {
        user_id: uid,
        watch_history: PRO_STORE.watch_history,
        video_notes: PRO_STORE.video_notes,
        saved_library: PRO_STORE.saved_library,
        bookmarks: PRO_STORE.bookmarks,
        mistake_bank: PRO_STORE.mistake_bank,
        flashcards: PRO_STORE.flashcards,
        planner_tasks: PRO_STORE.planner_tasks,
        syllabus_progress: PRO_STORE.syllabus_progress,
        exam_countdown: PRO_STORE.exam_countdown,
        study_stats: PRO_STORE.study_stats,
        preferences: PRO_STORE.preferences,
        daily_quiz_history: PRO_STORE.daily_quiz_history,
        paused_tests: PRO_STORE.paused_tests
    };
    try {
        const res = await fetch(`${PRO_API_BASE}/api/sync/push`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            keepalive: true
        });
        if (res.ok && showFeedback) {
            proToast("☁️ Cloud Sync Successful!", "success");
        }
    } catch {
        if (showFeedback) proToast("Sync retry background mein hoga.", "warning");
    }
};

window.pullCloudSyncData = async function(showFeedback = false) {
    const uid = getActiveUserId();
    if (!uid) return;
    try {
        const res = await fetch(`${PRO_API_BASE}/api/sync/pull?user_id=${encodeURIComponent(uid)}`);
        const json = await res.json();
        if (!json || json.status !== "success") return;

        if (json.blocked) {
            showPortalLockScreen("blocked", json.block_reason || "Admin ne aapka account temporarily restrict kar diya hai.");
            return;
        }

        const remote = json.sync || {};
        if (remote.watch_history) {
            PRO_STORE.watch_history = { ...remote.watch_history, ...PRO_STORE.watch_history };
        }
        if (remote.video_notes) {
            PRO_STORE.video_notes = { ...remote.video_notes, ...PRO_STORE.video_notes };
        }
        if (remote.saved_library) {
            PRO_STORE.saved_library = {
                classes: mergeUniqueByKey(PRO_STORE.saved_library.classes, remote.saved_library.classes || [], "key"),
                pdfs: mergeUniqueByKey(PRO_STORE.saved_library.pdfs, remote.saved_library.pdfs || [], "url")
            };
        }
        if (Array.isArray(remote.bookmarks)) {
            PRO_STORE.bookmarks = mergeUniqueByKey(PRO_STORE.bookmarks, remote.bookmarks, "qId");
        }
        if (Array.isArray(remote.mistake_bank)) {
            PRO_STORE.mistake_bank = mergeUniqueByKey(PRO_STORE.mistake_bank, remote.mistake_bank, "qId");
        }
        if (Array.isArray(remote.flashcards) && remote.flashcards.length) {
            PRO_STORE.flashcards = mergeUniqueByKey(PRO_STORE.flashcards, remote.flashcards, "id");
        }
        if (Array.isArray(remote.planner_tasks) && remote.planner_tasks.length) {
            PRO_STORE.planner_tasks = mergeUniqueByKey(PRO_STORE.planner_tasks, remote.planner_tasks, "id");
        }
        if (remote.exam_countdown && remote.exam_countdown.date && !PRO_STORE.exam_countdown.date) {
            PRO_STORE.exam_countdown = remote.exam_countdown;
        }
        if (remote.study_stats) {
            PRO_STORE.study_stats.streak = Math.max(PRO_STORE.study_stats.streak || 1, remote.study_stats.streak || 1);
            PRO_STORE.study_stats.dailyMinutes = {
                ...(remote.study_stats.dailyMinutes || {}),
                ...(PRO_STORE.study_stats.dailyMinutes || {})
            };
        }
        if (remote.paused_tests) {
            PRO_STORE.paused_tests = { ...remote.paused_tests, ...PRO_STORE.paused_tests };
        }
        if (Array.isArray(json.test_history) && json.test_history.length) {
            PRO_STORE.test_history = mergeUniqueByKey(PRO_STORE.test_history, json.test_history, "attempt_id")
                .sort((a, b) => (b.ts || 0) - (a.ts || 0));
        }

        saveProStoreLocal(false);
        renderHomeDashboard();
        if (showFeedback) proToast("✅ Cloud Data Restored!", "success");
    } catch {}
};

function mergeUniqueByKey(localArr, remoteArr, key) {
    const map = new Map();
    [...(remoteArr || []), ...(localArr || [])].forEach(item => {
        if (item && item[key] !== undefined) map.set(String(item[key]), item);
    });
    return Array.from(map.values());
}

window.logUserActivity = function(action, detail = "", meta = {}) {
    const uid = getActiveUserId();
    if (!uid) return;
    fetch(`${PRO_API_BASE}/api/activity`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id: uid,
            action,
            detail,
            meta: { name: getActiveUserName(), ...meta }
        }),
        keepalive: true
    }).catch(() => {});
};

window.logPortalError = function(source, message, stack = "") {
    fetch(`${PRO_API_BASE}/api/error_log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            source,
            message: String(message || "").slice(0, 500),
            user_id: getActiveUserId() || "Guest",
            stack: String(stack || "").slice(0, 1000)
        }),
        keepalive: true
    }).catch(() => {});
};

window.addEventListener("error", (e) => {
    if (e && e.message) logPortalError("WindowError", e.message, e.filename || "");
});

window.addEventListener("unhandledrejection", (e) => {
    if (e && e.reason) logPortalError("PromiseRejection", String(e.reason));
});

// =========================================================
// MAINTENANCE MODE, USER BLOCK GUARD & LIVE NOTICES
// =========================================================
function showPortalLockScreen(type, message) {
    const ov = document.getElementById("portalLockOverlay");
    if (!ov) return;
    const icon = document.getElementById("portalLockIcon");
    const title = document.getElementById("portalLockTitle");
    const msgEl = document.getElementById("portalLockMsg");
    const logoutBtn = document.getElementById("portalLockLogoutBtn");

    if (type === "blocked") {
        icon.textContent = "🚫";
        title.textContent = "Account Restricted";
        msgEl.textContent = message || "Admin ne aapka access restrict kar diya hai.";
        if (logoutBtn) logoutBtn.classList.remove("hidden");
    } else {
        icon.textContent = "🚧";
        title.textContent = "Portal Under Maintenance";
        msgEl.textContent = message || "Portal abhi update par hai. Kripya thodi der baad try karein.";
        if (logoutBtn) logoutBtn.classList.add("hidden");
    }
    ov.classList.remove("hidden");
}

window.checkPortalStatusAndNotices = async function() {
    const uid = getActiveUserId();
    try {
        const res = await fetch(`${PRO_API_BASE}/api/portal/status?user_id=${encodeURIComponent(uid)}`);
        const json = await res.json();
        if (!json || json.status !== "success") return;

        if (json.maintenance_mode) {
            showPortalLockScreen("maintenance", json.maintenance_message);
            return;
        }
        if (json.user_blocked) {
            showPortalLockScreen("blocked", json.block_reason);
            return;
        }

        renderLiveNoticeBanner(json.notices || []);
    } catch {}
};

function renderLiveNoticeBanner(notices) {
    const box = document.getElementById("liveNoticeBanner");
    if (!box) return;
    if (!notices || !notices.length) {
        box.classList.add("hidden");
        return;
    }
    const latest = notices[0];
    const colorMap = {
        urgent: "from-rose-600 to-red-700 border-rose-300",
        warning: "from-amber-500 to-orange-600 border-amber-300",
        success: "from-emerald-500 to-teal-600 border-emerald-300",
        info: "from-sky-600 to-blue-700 border-sky-300"
    };
    const grad = colorMap[latest.level] || colorMap.info;
    box.className = `max-w-6xl mx-auto rounded-2xl p-3.5 text-white bg-gradient-to-r ${grad} border-2 shadow-lg flex items-center justify-between gap-3`;
    box.innerHTML = `
        <div class="flex items-center gap-2.5 min-w-0">
            <span class="text-xl shrink-0">📢</span>
            <div class="min-w-0">
                <div class="font-black text-xs uppercase tracking-wide">${escHtml(latest.title)}</div>
                <div class="text-xs opacity-95 truncate sm:whitespace-normal">${escHtml(latest.message)}</div>
            </div>
        </div>
        <button onclick="document.getElementById('liveNoticeBanner').classList.add('hidden')" class="text-white/80 hover:text-white font-black text-sm bg-transparent border-0 cursor-pointer shrink-0">✕</button>`;
    box.classList.remove("hidden");
}

// =========================================================
// STUDY TIME, STREAK, THEME & PWA INSTALL
// =========================================================
window.addStudyMinutes = function(mins) {
    const m = Math.max(0, Number(mins) || 0);
    if (!m) return;
    const today = todayKey();
    const st = PRO_STORE.study_stats;

    if (st.lastDate && st.lastDate !== today) {
        const diffDays = Math.round((new Date(today) - new Date(st.lastDate)) / 86400000);
        if (diffDays === 1) st.streak = (st.streak || 1) + 1;
        else if (diffDays > 1) st.streak = 1;
    }
    st.lastDate = today;
    st.dailyMinutes[today] = Number(((st.dailyMinutes[today] || 0) + m).toFixed(1));
    st.totalMinutes = Number(((st.totalMinutes || 0) + m).toFixed(1));
    saveProStoreLocal(true);
    renderHomeDashboard();
};

window.togglePortalTheme = function() {
    const isDark = document.body.classList.toggle("dark-mode");
    PRO_STORE.preferences.theme = isDark ? "dark" : "sky";
    saveProStoreLocal(false);
    const btn = document.getElementById("themeSwitchBtn");
    if (btn) btn.textContent = isDark ? "☀️" : "🌙";
    proToast(isDark ? "🌙 Midnight Dark Mode ON" : "☀️ Asmani Sky Theme ON", "info");
};

function applySavedTheme() {
    const isDark = PRO_STORE.preferences.theme === "dark";
    document.body.classList.toggle("dark-mode", isDark);
    const btn = document.getElementById("themeSwitchBtn");
    if (btn) btn.textContent = isDark ? "☀️" : "🌙";
}

function updateNetworkSpeedBadge() {
    const el = document.getElementById("netSpeedBadge");
    if (!el) return;
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!navigator.onLine) {
        el.textContent = "🔴 Offline";
        el.classList.remove("hidden");
        return;
    }
    if (conn && conn.downlink) {
        el.textContent = `⚡ ${conn.downlink} Mbps (${(conn.effectiveType || "4g").toUpperCase()})`;
        el.classList.remove("hidden");
    }
}

window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    _deferredPwaPrompt = e;
    const btn = document.getElementById("pwaInstallBtn");
    if (btn) btn.classList.remove("hidden");
});

window.triggerPwaInstall = async function() {
    if (!_deferredPwaPrompt) {
        proToast("Browser menu se 'Add to Home Screen' choose karein.", "info");
        return;
    }
    _deferredPwaPrompt.prompt();
    const { outcome } = await _deferredPwaPrompt.userChoice;
    if (outcome === "accepted") {
        proToast("📲 RWA Sky Pro App Installing...", "success");
        const btn = document.getElementById("pwaInstallBtn");
        if (btn) btn.classList.add("hidden");
    }
    _deferredPwaPrompt = null;
};

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("./sw.js").catch(() => {});
    });
}

// =========================================================
// WATCH PROGRESS, CONTINUE WATCHING & TIMESTAMP NOTES
// =========================================================
window.recordWatchProgress = function(info, currentTime, duration) {
    if (!info || !info.key || !Number.isFinite(duration) || duration <= 0) return;
    const pct = Math.min(100, Math.round((currentTime / duration) * 100));
    PRO_STORE.watch_history[info.key] = {
        key: info.key,
        id: info.id || "",
        courseId: info.courseId || "",
        title: info.title || "Class Lecture",
        thumb: info.thumb || "",
        time: Math.floor(currentTime),
        duration: Math.floor(duration),
        pct,
        qualities: info.qualities || {},
        pdf1: info.pdf1 || "",
        pdf2: info.pdf2 || "",
        updatedAt: Date.now()
    };
    saveProStoreLocal(true);
};

window.getWatchProgress = function(key) {
    return (PRO_STORE.watch_history && PRO_STORE.watch_history[key]) || null;
};

window.saveCurrentVideoNote = function() {
    const key = typeof state !== "undefined" ? state.activeKey : null;
    const inp = document.getElementById("noteInputText");
    const vid = document.getElementById("video");
    if (!key || !inp) return;
    const text = inp.value.trim();
    if (!text) return proToast("Note text likhein pehle.", "warning");

    const curSec = vid && Number.isFinite(vid.currentTime) ? Math.floor(vid.currentTime) : 0;
    if (!PRO_STORE.video_notes[key]) PRO_STORE.video_notes[key] = [];
    PRO_STORE.video_notes[key].push({
        id: "note_" + Date.now(),
        time: curSec,
        text,
        createdAt: new Date().toLocaleDateString()
    });
    PRO_STORE.video_notes[key].sort((a, b) => a.time - b.time);
    inp.value = "";
    saveProStoreLocal(true);
    renderVideoNotesForKey(key);
    if (typeof renderSeekbarNoteMarkers === "function") renderSeekbarNoteMarkers(key);
    proToast(`📝 Note saved at ${fmtSimpleTime(curSec)}!`, "success");
};

window.deleteVideoNote = function(key, noteId) {
    if (!PRO_STORE.video_notes[key]) return;
    PRO_STORE.video_notes[key] = PRO_STORE.video_notes[key].filter(n => n.id !== noteId);
    saveProStoreLocal(true);
    renderVideoNotesForKey(key);
    if (typeof renderSeekbarNoteMarkers === "function") renderSeekbarNoteMarkers(key);
};

window.renderVideoNotesForKey = function(key) {
    const listEl = document.getElementById("playerNotesList");
    if (!listEl) return;
    const notes = (PRO_STORE.video_notes && PRO_STORE.video_notes[key]) || [];
    if (!notes.length) {
        listEl.innerHTML = `<div class="text-xs opacity-60 text-center py-2 font-semibold">Is class mein abhi koi note save nahi hai.</div>`;
        return;
    }
    listEl.innerHTML = notes.map(n => `
        <div class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-sky-50 dark:bg-slate-800/80 border border-sky-200 dark:border-slate-700 text-xs">
            <div onclick="seekToTimestamp(${n.time})" class="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer">
                <span class="px-2 py-0.5 rounded-lg bg-blue-600 text-white font-mono font-black shrink-0">⏱ ${fmtSimpleTime(n.time)}</span>
                <span class="font-bold truncate">${escHtml(n.text)}</span>
            </div>
            <button onclick="deleteVideoNote('${escHtml(key)}', '${escHtml(n.id)}')" class="text-rose-600 font-black bg-transparent border-0 cursor-pointer">✕</button>
        </div>`).join("");
};

function fmtSimpleTime(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return h
        ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
        : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// =========================================================
// PINNED LIBRARY (CLASSES & PDFS) + PDF NIGHT MODE
// =========================================================
window.togglePinActiveClass = function() {
    if (typeof state === "undefined" || !state.activeKey || !state.mediaMap[state.activeKey]) return;
    const info = state.mediaMap[state.activeKey];
    const list = PRO_STORE.saved_library.classes;
    const idx = list.findIndex(c => c.key === info.key);
    if (idx >= 0) {
        list.splice(idx, 1);
        proToast("📌 Class removed from Saved Library.", "info");
    } else {
        list.unshift({
            key: info.key,
            id: info.id,
            courseId: info.courseId,
            title: info.title,
            thumb: info.thumb,
            qualities: info.qualities,
            pdf1: info.pdf1,
            pdf2: info.pdf2,
            savedAt: new Date().toLocaleDateString()
        });
        proToast("📌 Class pinned to Saved Library!", "success");
    }
    saveProStoreLocal(true);
    updatePinButtonUI(info.key);
};

window.updatePinButtonUI = function(key) {
    const btn = document.getElementById("pinClassBtn");
    if (!btn) return;
    const isPinned = PRO_STORE.saved_library.classes.some(c => c.key === key);
    btn.textContent = isPinned ? "📌 Saved" : "📌 Save";
    btn.className = isPinned
        ? "btn-nav bg-emerald-600 text-white border-0 text-xs"
        : "btn-nav bg-amber-500 text-white border-0 text-xs";
};

window.pinActivePdfToLibrary = function() {
    if (typeof state === "undefined" || !state.currentPdfUrl) return;
    const title = (document.getElementById("pdfTitle") || {}).textContent || "Saved PDF";
    const list = PRO_STORE.saved_library.pdfs;
    if (list.some(p => p.url === state.currentPdfUrl)) {
        proToast("Yeh PDF pehle se Saved Library mein hai.", "info");
        return;
    }
    list.unshift({
        title,
        url: state.currentPdfUrl,
        savedAt: new Date().toLocaleDateString()
    });
    saveProStoreLocal(true);
    proToast("📄 PDF Saved Library mein pin ho gaya!", "success");
};

window.togglePdfNightMode = function(frameId, btn) {
    const f = document.getElementById(frameId);
    if (!f) return;
    const on = f.classList.toggle("pdf-night-invert");
    if (btn) btn.textContent = on ? "☀️ Normal" : "🌙 Night Read";
    proToast(on ? "🌙 PDF Night Reading Mode ON" : "☀️ Normal PDF View", "info");
};

window.resumeClassFromHistory = function(key) {
    const rec = PRO_STORE.watch_history[key] || PRO_STORE.saved_library.classes.find(c => c.key === key);
    if (!rec) return;
    if (typeof state !== "undefined") {
        state.mediaMap[key] = {
            key: rec.key,
            id: rec.id,
            courseId: rec.courseId,
            title: rec.title,
            thumb: rec.thumb || "",
            qualities: rec.qualities || {},
            pdf1: rec.pdf1 || "",
            pdf2: rec.pdf2 || ""
        };
        if (typeof playClassInRwaPlayer === "function") {
            playClassInRwaPlayer(key);
        }
    }
};

// =========================================================
// BOOKMARKS, MISTAKES, PAUSED TESTS & FLASHCARDS HELPERS
// =========================================================
window.isQuestionBookmarked = function(qId) {
    return PRO_STORE.bookmarks.some(b => String(b.qId) === String(qId));
};

window.toggleQuestionBookmark = function(qObj, testMeta = {}) {
    const qId = String(qObj.id || qObj.question_id || ("q_" + (qObj.question || "").slice(0, 28)));
    const idx = PRO_STORE.bookmarks.findIndex(b => String(b.qId) === qId);
    if (idx >= 0) {
        PRO_STORE.bookmarks.splice(idx, 1);
        saveProStoreLocal(true);
        renderHomeDashboard();
        proToast("☆ Bookmark removed.", "info");
        return false;
    }
    PRO_STORE.bookmarks.unshift({
        qId,
        testId: String(testMeta.id || ""),
        testTitle: testMeta.title || "Mock Test",
        subject: qObj._sectionName || qObj.subject || "General",
        questionObj: qObj,
        savedAt: new Date().toLocaleDateString()
    });
    saveProStoreLocal(true);
    renderHomeDashboard();
    proToast("⭐ Question Bookmarked in Vault!", "success");
    return true;
};

window.addMistakeQuestions = function(wrongList, testMeta = {}) {
    if (!Array.isArray(wrongList) || !wrongList.length) return;
    wrongList.forEach(({ qObj, chosenOption }) => {
        const qId = String(qObj.id || qObj.question_id || ("m_" + (qObj.question || "").slice(0, 28)));
        const exists = PRO_STORE.mistake_bank.findIndex(m => String(m.qId) === qId);
        const item = {
            qId,
            testId: String(testMeta.id || ""),
            testTitle: testMeta.title || "Mock Test",
            subject: qObj._sectionName || qObj.subject || "General",
            wrongAns: chosenOption,
            questionObj: qObj,
            savedAt: new Date().toLocaleDateString()
        };
        if (exists >= 0) PRO_STORE.mistake_bank[exists] = item;
        else PRO_STORE.mistake_bank.unshift(item);
    });
    if (PRO_STORE.mistake_bank.length > 300) PRO_STORE.mistake_bank = PRO_STORE.mistake_bank.slice(0, 300);
    saveProStoreLocal(true);
    renderHomeDashboard();
};

window.saveTestAttemptToVault = function(attemptDoc) {
    if (!attemptDoc) return;
    const aid = attemptDoc.attempt_id || ("att_" + Date.now());
    const rec = { ...attemptDoc, attempt_id: aid, ts: attemptDoc.ts || Math.floor(Date.now() / 1000) };
    PRO_STORE.test_history = [rec, ...PRO_STORE.test_history.filter(t => t.attempt_id !== aid)].slice(0, 60);
    saveProStoreLocal(false);
    renderHomeDashboard();
};

window.savePausedTestState = function(testId, payload) {
    if (!testId) return;
    PRO_STORE.paused_tests[String(testId)] = { ...payload, savedAt: Date.now() };
    saveProStoreLocal(true);
    renderHomeDashboard();
};

window.getPausedTestState = function(testId) {
    return (PRO_STORE.paused_tests && PRO_STORE.paused_tests[String(testId)]) || null;
};

window.clearPausedTestState = function(testId) {
    if (PRO_STORE.paused_tests && PRO_STORE.paused_tests[String(testId)]) {
        delete PRO_STORE.paused_tests[String(testId)];
        saveProStoreLocal(true);
        renderHomeDashboard();
    }
};

window.addFlashcardItem = function(front, back, subject = "General") {
    if (!front || !back) return;
    PRO_STORE.flashcards.unshift({
        id: "fc_" + Date.now(),
        subject: subject || "General",
        front: front.trim(),
        back: back.trim(),
        createdAt: new Date().toLocaleDateString()
    });
    saveProStoreLocal(true);
    proToast("🃏 Flashcard Added to Vault!", "success");
};

// =========================================================
// HOME DASHBOARD RENDERER (STREAK, COUNTDOWN, CONTINUE WATCHING)
// =========================================================
window.renderHomeDashboard = function() {
    const today = todayKey();
    const st = PRO_STORE.study_stats;
    const todayMins = Math.round(st.dailyMinutes[today] || 0);
    const goalPct = Math.min(100, Math.round((todayMins / 120) * 100));

    const streakEl = document.getElementById("dashStreakVal");
    const minsEl = document.getElementById("dashTodayMins");
    const barEl = document.getElementById("dashGoalBar");
    if (streakEl) streakEl.textContent = `🔥 ${st.streak || 1} Day${(st.streak || 1) > 1 ? "s" : ""}`;
    if (minsEl) minsEl.textContent = `${todayMins}m`;
    if (barEl) barEl.style.width = `${Math.max(4, goalPct)}%`;

    // Exam Countdown
    const cd = PRO_STORE.exam_countdown || { name: "SSC GD 2027", date: "" };
    const nameEl = document.getElementById("dashExamName");
    const daysEl = document.getElementById("dashExamDays");
    if (nameEl) nameEl.textContent = cd.name || "Target Exam";
    if (daysEl) {
        if (cd.date) {
            const diff = Math.ceil((new Date(cd.date) - new Date(today)) / 86400000);
            daysEl.textContent = diff > 0 ? `⏳ ${diff} Days Left` : (diff === 0 ? "🎯 Exam Day Today!" : "✅ Completed");
        } else {
            daysEl.textContent = "Set Exam Date";
        }
    }

    // Quick Counts
    const tEl = document.getElementById("dashTestsCount");
    const bEl = document.getElementById("dashBookmarksCount");
    const mEl = document.getElementById("dashMistakesCount");
    if (tEl) tEl.textContent = PRO_STORE.test_history.length;
    if (bEl) bEl.textContent = PRO_STORE.bookmarks.length;
    if (mEl) mEl.textContent = PRO_STORE.mistake_bank.length;

    // Paused Tests Banner
    const pBanner = document.getElementById("pausedTestsBanner");
    const pausedIds = Object.keys(PRO_STORE.paused_tests || {});
    if (pBanner) {
        if (pausedIds.length > 0) {
            const first = PRO_STORE.paused_tests[pausedIds[0]];
            pBanner.className = "max-w-6xl mx-auto sky-card p-3.5 border-2 border-amber-400 flex flex-wrap justify-between items-center gap-3";
            pBanner.innerHTML = `
                <div class="text-xs font-extrabold">⏸️ Paused Mock Test: <span class="text-amber-700 dark:text-amber-400">${escHtml(first.title || "Saved Test")}</span></div>
                <div class="flex gap-2">
                    <button onclick="resumePausedTestFromHome('${escHtml(pausedIds[0])}')" class="btn-watch text-xs py-1.5 px-3">▶ Resume Test</button>
                    <button onclick="clearPausedTestState('${escHtml(pausedIds[0])}')" class="btn-nav bg-rose-600 text-white border-0 text-xs py-1.5">Discard</button>
                </div>`;
            pBanner.classList.remove("hidden");
        } else {
            pBanner.classList.add("hidden");
        }
    }

    // Continue Watching Section
    const cwBox = document.getElementById("continueWatchingBox");
    if (cwBox) {
        const recent = Object.values(PRO_STORE.watch_history || {})
            .filter(w => w && w.time > 3 && w.pct < 98)
            .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
            .slice(0, 3);
        if (recent.length > 0) {
            cwBox.classList.remove("hidden");
            cwBox.innerHTML = `
                <div class="flex justify-between items-center mb-3">
                    <h3 class="font-black text-sm">▶️ Continue Watching</h3>
                    <span class="text-[11px] font-bold opacity-70">Auto-Synced</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    ${recent.map(w => `
                        <div onclick="resumeClassFromHistory('${escHtml(w.key)}')" class="p-3 rounded-2xl bg-sky-50/90 dark:bg-slate-800/80 border border-sky-200 dark:border-slate-700 cursor-pointer hover:border-blue-500 transition">
                            <div class="font-extrabold text-xs line-clamp-1">${escHtml(w.title)}</div>
                            <div class="flex justify-between text-[10px] font-bold opacity-70 mt-1">
                                <span>▶ Resume ${fmtSimpleTime(w.time)}</span>
                                <span>${w.pct}%</span>
                            </div>
                            <div class="w-full h-1.5 bg-sky-200 dark:bg-slate-700 rounded-full overflow-hidden mt-1.5">
                                <div class="h-full bg-blue-600 rounded-full" style="width:${w.pct}%"></div>
                            </div>
                        </div>`).join("")}
                </div>`;
        } else {
            cwBox.classList.add("hidden");
        }
    }
};

window.resumePausedTestFromHome = function(testId) {
    const p = getPausedTestState(testId);
    if (!p || !p.testMeta) return;
    if (typeof state !== "undefined") {
        const tKey = `test_${testId}`;
        state.testMap[tKey] = p.testMeta;
        if (typeof launchCbtTest === "function") launchCbtTest(tKey);
    }
};

// =========================================================
// EXAM COUNTDOWN, REPORT ISSUE & GLOBAL SEARCH MODALS
// =========================================================
window.openCountdownModal = function() {
    document.getElementById("cdExamName").value = PRO_STORE.exam_countdown.name || "";
    document.getElementById("cdExamDate").value = PRO_STORE.exam_countdown.date || "";
    document.getElementById("countdownModal").classList.remove("hidden");
};
window.closeCountdownModal = function() {
    document.getElementById("countdownModal").classList.add("hidden");
};
window.saveExamCountdown = function() {
    const name = document.getElementById("cdExamName").value.trim() || "Target Exam";
    const date = document.getElementById("cdExamDate").value;
    PRO_STORE.exam_countdown = { name, date };
    saveProStoreLocal(true);
    closeCountdownModal();
    renderHomeDashboard();
    proToast("🎯 Exam Countdown Updated!", "success");
};

window.openReportIssueModal = function() {
    document.getElementById("reportIssueModal").classList.remove("hidden");
};
window.closeReportIssueModal = function() {
    document.getElementById("reportIssueModal").classList.add("hidden");
};
window.submitUserReport = async function() {
    const type = document.getElementById("repType").value;
    const subject = document.getElementById("repSubject").value.trim();
    const message = document.getElementById("repMessage").value.trim();
    if (!subject || !message) return proToast("Subject aur Details dono likhein.", "warning");

    const phone = (typeof USER_PROFILE !== "undefined" && USER_PROFILE && USER_PROFILE.phone) ? USER_PROFILE.phone : "N/A";
    try {
        const res = await fetch(`${PRO_API_BASE}/api/report`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: getActiveUserId() || "Guest",
                user_name: getActiveUserName(),
                phone,
                type,
                subject,
                message
            })
        });
        if (res.ok) {
            document.getElementById("repSubject").value = "";
            document.getElementById("repMessage").value = "";
            closeReportIssueModal();
            proToast("✅ Aapki request Admin ko bhej di gayi hai!", "success");
        } else {
            proToast("Server busy hai, thodi der baad try karein.", "error");
        }
    } catch {
        proToast("Network error! Please try again.", "error");
    }
};

window.openGlobalSearchModal = function() {
    document.getElementById("globalSearchModal").classList.remove("hidden");
    const inp = document.getElementById("globalSearchInput");
    inp.value = "";
    inp.focus();
    runGlobalSearch("");
};
window.closeGlobalSearchModal = function() {
    document.getElementById("globalSearchModal").classList.add("hidden");
};
window.runGlobalSearch = function(query) {
    const q = String(query || "").trim().toLowerCase();
    const resBox = document.getElementById("globalSearchResults");
    if (!resBox) return;

    const hits = [];
    (PRO_STORE.search_cache.batches || []).forEach(b => {
        if (!q || (b.course_name || "").toLowerCase().includes(q)) {
            hits.push({ tag: "🎓 Batch", title: b.course_name, fn: `closeGlobalSearchModal(); openExplorerSlide('paid'); setTimeout(()=>openPaidCourse('${b.id}','${(b.course_name || "").replace(/'/g, "")}'), 400);` });
        }
    });
    (PRO_STORE.search_cache.testSeries || []).forEach(ts => {
        if (!q || (ts.title || "").toLowerCase().includes(q)) {
            hits.push({ tag: "🏆 Test Series", title: ts.title, fn: `closeGlobalSearchModal(); openTestSeriesExplorer('paid_ts'); setTimeout(()=>openTestSeriesSubjects('${ts.id}','${(ts.title || "").replace(/'/g, "")}'), 400);` });
        }
    });
    Object.values(PRO_STORE.watch_history || {}).forEach(w => {
        if (!q || (w.title || "").toLowerCase().includes(q)) {
            hits.push({ tag: "🎬 Watched Class", title: w.title, fn: `closeGlobalSearchModal(); resumeClassFromHistory('${w.key}');` });
        }
    });
    (PRO_STORE.bookmarks || []).forEach(b => {
        const txt = (b.subject + " " + b.testTitle + " " + (b.questionObj.question || "")).toLowerCase();
        if (!q || txt.includes(q)) {
            hits.push({ tag: "⭐ Bookmark", title: `${b.subject} — ${b.testTitle}`, fn: `closeGlobalSearchModal(); openStudyVaultSlide('bookmarks');` });
        }
    });

    const sliced = hits.slice(0, 20);
    resBox.innerHTML = sliced.length ? sliced.map(h => `
        <div onclick="${h.fn}" class="p-3 rounded-xl bg-sky-50 dark:bg-slate-800 border border-sky-200 dark:border-slate-700 cursor-pointer hover:border-blue-500 flex justify-between items-center gap-2">
            <span class="font-extrabold truncate">${escHtml(h.title)}</span>
            <span class="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-[10px] font-black shrink-0">${h.tag}</span>
        </div>`).join("") : `<div class="text-center py-6 opacity-70 font-bold">Koi match nahi mila. Pehle Batches ya Test Series open karein taaki index ban sake.</div>`;
};

// =========================================================
// SLIDE 5: PRO STUDY VAULT (10 FULL TOOLS)
// =========================================================
window.openStudyVaultSlide = function(tab = "history") {
    if (typeof enforceCompulsoryLogin === "function" && !enforceCompulsoryLogin()) return;
    if (typeof showSlide === "function") showSlide("slideVault");
    renderVaultTab(tab);
};

window.renderVaultTab = function(tab) {
    _activeVaultTab = tab;
    document.querySelectorAll("#vaultTabsBar [data-vtab]").forEach(btn => {
        btn.className = btn.dataset.vtab === tab ? "tab-pill active-pill" : "tab-pill";
    });
    const box = document.getElementById("vaultContentArea");
    if (!box) return;

    if (tab === "history") renderVaultScorecards(box);
    else if (tab === "bookmarks") renderVaultBookmarks(box);
    else if (tab === "mistakes") renderVaultMistakes(box);
    else if (tab === "custom_mock") renderVaultCustomMock(box);
    else if (tab === "saved") renderVaultSavedLibrary(box);
    else if (tab === "flashcards") renderVaultFlashcards(box);
    else if (tab === "pomodoro") renderVaultPomodoro(box);
    else if (tab === "planner") renderVaultPlanner(box);
    else if (tab === "rapid_quiz") renderVaultRapidQuiz(box);
    else if (tab === "backup") renderVaultBackup(box);
};

// 1. Scorecards & Last 10 Tests Performance Trend Graph
function renderVaultScorecards(box) {
    const hist = PRO_STORE.test_history || [];
    const last10 = hist.slice(0, 10).reverse();

    const graphHtml = last10.length ? `
        <div class="p-4 rounded-2xl bg-sky-50/80 dark:bg-slate-800/80 border border-sky-200 dark:border-slate-700 mb-5">
            <div class="flex justify-between items-center mb-3">
                <h4 class="font-black text-sm">📈 Performance Trend (Last ${last10.length} Tests)</h4>
                <span class="text-[10px] font-bold opacity-70">Blue = Score % • Green = Accuracy %</span>
            </div>
            <div class="flex items-end gap-2 h-36 pt-4 overflow-x-auto">
                ${last10.map((t, i) => {
                    const scorePct = Math.max(4, Math.min(100, Math.round((t.score / (t.max_marks || 100)) * 100)));
                    const accPct = Math.max(4, Math.min(100, Math.round(t.accuracy || 0)));
                    return `
                        <div class="flex-1 min-w-[44px] flex flex-col items-center gap-1 h-full justify-end">
                            <div class="flex items-end gap-1 h-24 w-full justify-center">
                                <div title="Score ${scorePct}%" class="w-3 bg-blue-600 rounded-t-md" style="height:${scorePct}%"></div>
                                <div title="Acc ${accPct}%" class="w-3 bg-emerald-500 rounded-t-md" style="height:${accPct}%"></div>
                            </div>
                            <span class="text-[10px] font-black opacity-75">T${i + 1}</span>
                        </div>`;
                }).join("")}
            </div>
        </div>` : "";

    box.innerHTML = `
        <h3 class="font-black text-lg mb-3">📊 Permanent Test Scorecard Vault (${hist.length})</h3>
        ${graphHtml}
        <div class="space-y-3">
            ${hist.length ? hist.map(t => `
                <div class="p-4 rounded-2xl bg-white dark:bg-slate-800 border-2 border-sky-100 dark:border-slate-700 flex flex-wrap justify-between items-center gap-3">
                    <div>
                        <span class="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 text-[10px] font-black">TEST #${escHtml(t.test_id)}</span>
                        <h4 class="font-black text-sm mt-1">${escHtml(t.test_title)}</h4>
                        <div class="text-[11px] opacity-75 font-bold mt-0.5">✓ ${t.correct} • ✕ ${t.incorrect} • − ${t.unattempted} • 🕒 ${escHtml(t.submitted_at || "")}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-black text-blue-600">${t.score} / ${t.max_marks}</div>
                        <div class="text-xs font-extrabold text-emerald-600">🎯 ${t.accuracy}% Accuracy</div>
                    </div>
                </div>`).join("") : `<div class="py-10 text-center text-xs font-bold opacity-70">Abhi tak koi mock test submit nahi kiya hai. Test attempt karein, scorecard yahan permanently save hoga!</div>`}
        </div>`;
}

// 2. Bookmarked Questions Vault
function renderVaultBookmarks(box) {
    const list = PRO_STORE.bookmarks || [];
    box.innerHTML = `
        <div class="flex flex-wrap justify-between items-center gap-2 mb-4">
            <h3 class="font-black text-lg">⭐ Bookmarked Questions (${list.length})</h3>
            ${list.length ? `<button onclick="launchVaultQuestionsAsTest('bookmarks')" class="btn-watch text-xs">🚀 Practice Saved Questions</button>` : ""}
        </div>
        <div class="space-y-3">
            ${list.length ? list.map((b, i) => `
                <div class="p-4 rounded-2xl bg-white dark:bg-slate-800 border-2 border-amber-200 dark:border-slate-700 space-y-2">
                    <div class="flex justify-between items-center gap-2">
                        <span class="px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-900 text-[10px] font-black">${escHtml(b.subject)} • ${escHtml(b.testTitle)}</span>
                        <button onclick="removeBookmarkFromVault('${escHtml(b.qId)}')" class="text-xs font-black text-rose-600 bg-transparent border-0 cursor-pointer">🗑 Remove</button>
                    </div>
                    <div class="text-sm font-semibold">${b.questionObj.question || ""}</div>
                    <details class="text-xs bg-emerald-50 dark:bg-slate-900 p-3 rounded-xl">
                        <summary class="cursor-pointer font-black text-emerald-700 dark:text-emerald-400">💡 View Answer & Solution</summary>
                        <div class="mt-2 font-bold">Correct Option: #${escHtml(b.questionObj.answer || "1")}</div>
                        <div class="mt-1 opacity-90">${b.questionObj.solution_text || b.questionObj.explanation || "Check options above."}</div>
                    </details>
                </div>`).join("") : `<div class="py-10 text-center text-xs font-bold opacity-70">Live Test ya Solution screen par '☆ Save' dabakar tough questions yahan store karein.</div>`}
        </div>`;
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([box]).catch(() => {});
}

window.removeBookmarkFromVault = function(qId) {
    PRO_STORE.bookmarks = PRO_STORE.bookmarks.filter(b => String(b.qId) !== String(qId));
    saveProStoreLocal(true);
    renderHomeDashboard();
    renderVaultTab("bookmarks");
};

// 3. Smart Mistake Notebook
function renderVaultMistakes(box) {
    const list = PRO_STORE.mistake_bank || [];
    box.innerHTML = `
        <div class="flex flex-wrap justify-between items-center gap-2 mb-4">
            <div>
                <h3 class="font-black text-lg">❌ Smart Mistake Notebook (${list.length})</h3>
                <p class="text-xs opacity-70 font-semibold">Mock tests mein jo questions galat hue woh auto-collect hote hain</p>
            </div>
            ${list.length ? `<button onclick="launchVaultQuestionsAsTest('mistakes')" class="btn-watch text-xs">🔥 Re-Test All Mistakes</button>` : ""}
        </div>
        <div class="space-y-3">
            ${list.length ? list.map(m => `
                <div class="p-4 rounded-2xl bg-white dark:bg-slate-800 border-2 border-rose-200 dark:border-slate-700 space-y-2">
                    <div class="flex justify-between items-center gap-2">
                        <span class="px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-800 text-[10px] font-black">${escHtml(m.subject)} • ${escHtml(m.testTitle)}</span>
                        <button onclick="markMistakeMastered('${escHtml(m.qId)}')" class="px-2.5 py-1 rounded-lg bg-emerald-600 text-white text-[10px] font-black border-0 cursor-pointer">✅ Mastered</button>
                    </div>
                    <div class="text-sm font-semibold">${m.questionObj.question || ""}</div>
                    <details class="text-xs bg-sky-50 dark:bg-slate-900 p-3 rounded-xl">
                        <summary class="cursor-pointer font-black text-blue-700 dark:text-sky-400">💡 View Correct Solution</summary>
                        <div class="mt-2 font-bold text-emerald-600">Correct Option: #${escHtml(m.questionObj.answer || "1")}</div>
                        <div class="mt-1">${m.questionObj.solution_text || m.questionObj.explanation || "Check solution."}</div>
                    </details>
                </div>`).join("") : `<div class="py-10 text-center text-xs font-bold opacity-70">Koi pending mistake nahi hai — shabash!</div>`}
        </div>`;
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([box]).catch(() => {});
}

window.markMistakeMastered = function(qId) {
    PRO_STORE.mistake_bank = PRO_STORE.mistake_bank.filter(m => String(m.qId) !== String(qId));
    saveProStoreLocal(true);
    renderHomeDashboard();
    renderVaultTab("mistakes");
    proToast("✅ Removed from Mistake Bank!", "success");
};

// 4. Custom Mock Test Builder
function renderVaultCustomMock(box) {
    const bCnt = PRO_STORE.bookmarks.length;
    const mCnt = PRO_STORE.mistake_bank.length;
    box.innerHTML = `
        <div class="max-w-lg mx-auto space-y-4">
            <h3 class="font-black text-lg">🛠️ Custom Mock Test Builder</h3>
            <p class="text-xs opacity-75 font-semibold">Apne Bookmarks aur Mistakes se khud ka custom timed TCS exam banayein!</p>
            <div>
                <label class="text-xs font-extrabold">Question Source</label>
                <select id="cmSource" class="w-full bg-white dark:bg-slate-800 border-2 border-sky-200 rounded-xl p-3 text-xs font-bold mt-1">
                    <option value="mix">🔥 Mix (Mistakes + Bookmarks: ${bCnt + mCnt} Qs)</option>
                    <option value="mistakes">❌ Only Mistake Bank (${mCnt} Qs)</option>
                    <option value="bookmarks">⭐ Only Bookmarks (${bCnt} Qs)</option>
                </select>
            </div>
            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="text-xs font-extrabold">Questions Count</label>
                    <input id="cmCount" type="number" value="20" min="3" max="100" class="w-full bg-white dark:bg-slate-800 border-2 border-sky-200 rounded-xl p-3 text-xs font-bold mt-1">
                </div>
                <div>
                    <label class="text-xs font-extrabold">Time (Minutes)</label>
                    <input id="cmTime" type="number" value="15" min="2" max="120" class="w-full bg-white dark:bg-slate-800 border-2 border-sky-200 rounded-xl p-3 text-xs font-bold mt-1">
                </div>
            </div>
            <button onclick="buildAndLaunchCustomMock()" class="btn-watch w-full py-3 text-sm">🚀 Generate & Start Custom Test</button>
        </div>`;
}

window.launchVaultQuestionsAsTest = function(source) {
    const pool = source === "bookmarks"
        ? PRO_STORE.bookmarks.map(x => x.questionObj)
        : PRO_STORE.mistake_bank.map(x => x.questionObj);
    if (!pool.length) return proToast("Koi questions available nahi hain.", "warning");
    if (typeof window.launchCustomQuestionsTcs === "function") {
        window.launchCustomQuestionsTcs(
            source === "bookmarks" ? "⭐ Bookmarked Revision Test" : "❌ Mistake Notebook Re-Test",
            pool,
            Math.max(5, Math.ceil(pool.length * 0.8))
        );
    }
};

window.buildAndLaunchCustomMock = function() {
    const src = document.getElementById("cmSource").value;
    const count = Math.max(1, parseInt(document.getElementById("cmCount").value || "20", 10));
    const mins = Math.max(2, parseInt(document.getElementById("cmTime").value || "15", 10));
    let pool = [];
    if (src === "bookmarks") pool = PRO_STORE.bookmarks.map(x => x.questionObj);
    else if (src === "mistakes") pool = PRO_STORE.mistake_bank.map(x => x.questionObj);
    else pool = [...PRO_STORE.mistake_bank.map(x => x.questionObj), ...PRO_STORE.bookmarks.map(x => x.questionObj)];

    if (!pool.length) return proToast("Pehle kuch questions bookmark karein ya mock test dein!", "warning");
    pool = pool.sort(() => Math.random() - 0.5).slice(0, count);
    if (typeof window.launchCustomQuestionsTcs === "function") {
        window.launchCustomQuestionsTcs(`🛠️ Custom Mock (${pool.length} Qs)`, pool, mins);
    }
};

// 5. Saved Library (Classes + PDFs)
function renderVaultSavedLibrary(box) {
    const classes = PRO_STORE.saved_library.classes || [];
    const pdfs = PRO_STORE.saved_library.pdfs || [];
    box.innerHTML = `
        <div class="space-y-6">
            <div>
                <h3 class="font-black text-base mb-3">📌 Pinned Classes (${classes.length})</h3>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    ${classes.length ? classes.map(c => `
                        <div class="p-3.5 rounded-2xl bg-white dark:bg-slate-800 border-2 border-sky-100 dark:border-slate-700 flex flex-col justify-between gap-2">
                            <div class="font-extrabold text-sm">${escHtml(c.title)}</div>
                            <div class="flex gap-2">
                                <button onclick="resumeClassFromHistory('${escHtml(c.key)}')" class="btn-watch flex-1 text-xs py-1.5">▶ Watch</button>
                                <button onclick="removePinnedClass('${escHtml(c.key)}')" class="btn-nav bg-rose-600 text-white border-0 text-xs">🗑</button>
                            </div>
                        </div>`).join("") : `<div class="col-span-full text-xs opacity-65 font-bold">Video player mein '📌 Save' click karke classes pin karein.</div>`}
                </div>
            </div>
            <div>
                <h3 class="font-black text-base mb-3">📄 Saved PDFs Locker (${pdfs.length})</h3>
                <div class="space-y-2">
                    ${pdfs.length ? pdfs.map((p, i) => `
                        <div class="p-3 rounded-2xl bg-white dark:bg-slate-800 border border-sky-200 dark:border-slate-700 flex justify-between items-center gap-2">
                            <span class="font-extrabold text-xs truncate">${escHtml(p.title)}</span>
                            <div class="flex gap-2 shrink-0">
                                <button onclick="openDirectSavedPdf(${i})" class="btn-pdf1 text-xs py-1.5">📄 Open</button>
                                <button onclick="removePinnedPdf(${i})" class="btn-nav bg-rose-600 text-white border-0 text-xs">🗑</button>
                            </div>
                        </div>`).join("") : `<div class="text-xs opacity-65 font-bold">PDF viewer mein '📌 Save PDF' se notes pin karein.</div>`}
                </div>
            </div>
        </div>`;
}

window.removePinnedClass = function(key) {
    PRO_STORE.saved_library.classes = PRO_STORE.saved_library.classes.filter(c => c.key !== key);
    saveProStoreLocal(true);
    renderVaultTab("saved");
};
window.removePinnedPdf = function(idx) {
    PRO_STORE.saved_library.pdfs.splice(idx, 1);
    saveProStoreLocal(true);
    renderVaultTab("saved");
};
window.openDirectSavedPdf = function(idx) {
    const p = PRO_STORE.saved_library.pdfs[idx];
    if (!p || typeof state === "undefined") return;
    state.currentPdfUrl = p.url;
    document.getElementById("pdfTitle").textContent = p.title;
    document.getElementById("rawPdfLink").href = p.url;
    showSlide("slidePdf");
    setPdfMode("appx");
};

// 6. Swipeable 3D Formula & Vocab Flashcards
function renderVaultFlashcards(box) {
    const cards = PRO_STORE.flashcards || [];
    if (_flashcardIdx >= cards.length) _flashcardIdx = 0;
    const cur = cards[_flashcardIdx];

    box.innerHTML = `
        <div class="max-w-xl mx-auto space-y-5">
            <div class="flex justify-between items-center">
                <h3 class="font-black text-lg">🃏 Formula & Vocab Flashcards (${cards.length})</h3>
                <span class="text-xs font-extrabold opacity-70">${cards.length ? `${_flashcardIdx + 1} / ${cards.length}` : "0"}</span>
            </div>

            ${cur ? `
                <div class="flashcard-stage" onclick="this.classList.toggle('flipped')">
                    <div class="flashcard-inner">
                        <div class="flashcard-face flashcard-front">
                            <span class="px-2.5 py-0.5 rounded-full bg-white/20 text-[10px] font-black mb-2">${escHtml(cur.subject)} • TAP TO FLIP</span>
                            <div class="font-black text-base sm:text-lg">${escHtml(cur.front)}</div>
                        </div>
                        <div class="flashcard-face flashcard-back">
                            <span class="px-2.5 py-0.5 rounded-full bg-white/20 text-[10px] font-black mb-2">ANSWER / TRICK</span>
                            <div class="font-black text-base sm:text-lg">${escHtml(cur.back)}</div>
                        </div>
                    </div>
                </div>
                <div class="flex justify-between items-center gap-2">
                    <button onclick="stepFlashcard(-1)" class="btn-nav bg-slate-800 text-white border-0">⬅ Prev</button>
                    <button onclick="deleteCurrentFlashcard()" class="btn-nav bg-rose-600 text-white border-0 text-xs">🗑 Delete Card</button>
                    <button onclick="stepFlashcard(1)" class="btn-nav bg-slate-800 text-white border-0">Next ➡</button>
                </div>` : `<div class="text-center py-6 text-xs font-bold opacity-70">Niche form se apna pehla flashcard banayein!</div>`}

            <div class="p-4 rounded-2xl bg-sky-50 dark:bg-slate-800 border border-sky-200 dark:border-slate-700 space-y-2.5">
                <div class="font-black text-xs">➕ Add New Flashcard</div>
                <input id="fcSubInput" type="text" placeholder="Subject (e.g. Vocab / Polity / Maths)" class="w-full bg-white dark:bg-slate-900 border border-sky-300 rounded-xl p-2.5 text-xs outline-none">
                <input id="fcFrontInput" type="text" placeholder="Front: Question / Word / Formula Name" class="w-full bg-white dark:bg-slate-900 border border-sky-300 rounded-xl p-2.5 text-xs outline-none">
                <textarea id="fcBackInput" rows="2" placeholder="Back: Answer / Short Trick" class="w-full bg-white dark:bg-slate-900 border border-sky-300 rounded-xl p-2.5 text-xs outline-none"></textarea>
                <button onclick="submitNewFlashcard()" class="btn-watch w-full text-xs">💾 Save Flashcard</button>
            </div>
        </div>`;
}

window.stepFlashcard = function(delta) {
    const len = PRO_STORE.flashcards.length;
    if (!len) return;
    _flashcardIdx = (_flashcardIdx + delta + len) % len;
    renderVaultTab("flashcards");
};
window.deleteCurrentFlashcard = function() {
    if (!PRO_STORE.flashcards.length) return;
    PRO_STORE.flashcards.splice(_flashcardIdx, 1);
    saveProStoreLocal(true);
    renderVaultTab("flashcards");
};
window.submitNewFlashcard = function() {
    const sub = document.getElementById("fcSubInput").value.trim() || "General";
    const front = document.getElementById("fcFrontInput").value.trim();
    const back = document.getElementById("fcBackInput").value.trim();
    if (!front || !back) return proToast("Front aur Back dono bharein.", "warning");
    addFlashcardItem(front, back, sub);
    _flashcardIdx = 0;
    renderVaultTab("flashcards");
};

// 7. Pomodoro Focus Timer + Web Audio Soft Rain Study Sound
function renderVaultPomodoro(box) {
    const m = String(Math.floor(_pomoState.secondsLeft / 60)).padStart(2, "0");
    const s = String(_pomoState.secondsLeft % 60).padStart(2, "0");
    box.innerHTML = `
        <div class="max-w-md mx-auto text-center space-y-5 py-4">
            <h3 class="font-black text-xl">⏱️ Pomodoro Deep Focus Timer</h3>
            <div class="flex justify-center gap-2">
                <button onclick="setPomoPreset(25)" class="tab-pill ${_pomoState.mode === "25" ? "active-pill" : ""}">25m Focus</button>
                <button onclick="setPomoPreset(50)" class="tab-pill ${_pomoState.mode === "50" ? "active-pill" : ""}">50m Deep</button>
                <button onclick="setPomoPreset(5)" class="tab-pill ${_pomoState.mode === "5" ? "active-pill" : ""}">5m Break</button>
            </div>
            <div id="pomoClockDisplay" class="text-6xl font-black font-mono text-blue-600 dark:text-sky-400 tracking-wider py-4">${m}:${s}</div>
            <div class="flex justify-center gap-3">
                <button onclick="togglePomoTimer()" id="pomoStartBtn" class="btn-watch px-8 py-3 text-sm">${_pomoState.running ? "⏸ Pause" : "▶ Start Focus"}</button>
                <button onclick="resetPomoTimer()" class="btn-nav bg-slate-200 text-slate-900 border-0 px-5">🔄 Reset</button>
            </div>
            <div class="p-4 rounded-2xl bg-sky-50 dark:bg-slate-800 border border-sky-200 dark:border-slate-700 flex justify-between items-center">
                <div class="text-left">
                    <div class="font-black text-xs">🌧️ Soft Rain Ambient Focus Sound</div>
                    <div class="text-[11px] opacity-70">Distractions block karne ke liye bina internet audio</div>
                </div>
                <button onclick="toggleStudyWhiteNoise()" id="pomoSoundBtn" class="btn-nav ${_pomoState.soundOn ? "bg-emerald-600" : "bg-slate-700"} text-white border-0 text-xs">${_pomoState.soundOn ? "🔊 ON" : "🔇 OFF"}</button>
            </div>
        </div>`;
}

window.setPomoPreset = function(mins) {
    if (_pomoState.interval) clearInterval(_pomoState.interval);
    _pomoState.running = false;
    _pomoState.mode = String(mins);
    _pomoState.secondsLeft = mins * 60;
    renderVaultTab("pomodoro");
};
window.togglePomoTimer = function() {
    if (_pomoState.running) {
        clearInterval(_pomoState.interval);
        _pomoState.running = false;
        renderVaultTab("pomodoro");
        return;
    }
    _pomoState.running = true;
    _pomoState.interval = setInterval(() => {
        if (_pomoState.secondsLeft <= 0) {
            clearInterval(_pomoState.interval);
            _pomoState.running = false;
            const minsCompleted = parseInt(_pomoState.mode, 10) || 25;
            if (minsCompleted >= 15) {
                addStudyMinutes(minsCompleted);
                logUserActivity("POMODORO", `Completed ${minsCompleted}m Focus Session`);
            }
            proToast("🎉 Focus Session Complete! Study time added.", "success");
            if (_activeVaultTab === "pomodoro") renderVaultTab("pomodoro");
            return;
        }
        _pomoState.secondsLeft--;
        const clk = document.getElementById("pomoClockDisplay");
        if (clk) {
            clk.textContent = `${String(Math.floor(_pomoState.secondsLeft / 60)).padStart(2, "0")}:${String(_pomoState.secondsLeft % 60).padStart(2, "0")}`;
        }
    }, 1000);
    renderVaultTab("pomodoro");
};
window.resetPomoTimer = function() {
    setPomoPreset(parseInt(_pomoState.mode, 10) || 25);
};
window.toggleStudyWhiteNoise = function() {
    if (_pomoState.soundOn) {
        try { _pomoState.noiseNode.stop(); _pomoState.audioCtx.close(); } catch {}
        _pomoState.soundOn = false;
        if (_activeVaultTab === "pomodoro") renderVaultTab("pomodoro");
        return;
    }
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        const bufferSize = 2 * ctx.sampleRate;
        const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const output = noiseBuffer.getChannelData(0);
        let lastOut = 0.0;
        for (let i = 0; i < bufferSize; i++) {
            const white = Math.random() * 2 - 1;
            output[i] = (lastOut + 0.02 * white) / 1.02;
            lastOut = output[i];
            output[i] *= 0.25; // gentle brown/rain noise
        }
        const whiteNoise = ctx.createBufferSource();
        whiteNoise.buffer = noiseBuffer;
        whiteNoise.loop = true;
        const gain = ctx.createGain();
        gain.gain.value = 0.18;
        whiteNoise.connect(gain);
        gain.connect(ctx.destination);
        whiteNoise.start(0);
        _pomoState.audioCtx = ctx;
        _pomoState.noiseNode = whiteNoise;
        _pomoState.soundOn = true;
        renderVaultTab("pomodoro");
    } catch {
        proToast("Audio context blocked by browser.", "warning");
    }
};

// 8. Daily Study Planner & Syllabus Checklist
function renderVaultPlanner(box) {
    const tasks = PRO_STORE.planner_tasks || [];
    const doneCnt = tasks.filter(t => t.done).length;
    const pct = tasks.length ? Math.round((doneCnt / tasks.length) * 100) : 0;
    box.innerHTML = `
        <div class="max-w-2xl mx-auto space-y-4">
            <div class="flex justify-between items-center">
                <h3 class="font-black text-lg">📅 Daily Study Planner & Targets</h3>
                <span class="px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-black">${doneCnt}/${tasks.length} Done (${pct}%)</span>
            </div>
            <div class="w-full h-2.5 bg-sky-100 rounded-full overflow-hidden">
                <div class="h-full bg-emerald-500 transition-all" style="width:${pct}%"></div>
            </div>
            <div class="flex gap-2">
                <input id="plannerTaskInput" type="text" placeholder="e.g. 2 History Classes + 1 SSC GD Mock Test" onkeydown="if(event.key==='Enter') addPlannerTask()"
                       class="flex-1 bg-white dark:bg-slate-800 border-2 border-sky-200 rounded-xl px-3 py-2.5 text-xs font-semibold outline-none">
                <button onclick="addPlannerTask()" class="btn-watch text-xs">➕ Add Goal</button>
            </div>
            <div class="space-y-2">
                ${tasks.length ? tasks.map(t => `
                    <div class="p-3 rounded-xl bg-white dark:bg-slate-800 border border-sky-200 dark:border-slate-700 flex items-center justify-between gap-2">
                        <label class="flex items-center gap-2.5 cursor-pointer flex-1 text-xs font-bold ${t.done ? "line-through opacity-55" : ""}">
                            <input type="checkbox" ${t.done ? "checked" : ""} onchange="togglePlannerTask('${escHtml(t.id)}')" class="w-4 h-4 accent-emerald-600">
                            <span>${escHtml(t.text)}</span>
                        </label>
                        <button onclick="deletePlannerTask('${escHtml(t.id)}')" class="text-rose-600 font-black bg-transparent border-0 cursor-pointer">✕</button>
                    </div>`).join("") : `<div class="text-center py-8 text-xs font-bold opacity-65">Aaj ka koi study target add nahi hai.</div>`}
            </div>
        </div>`;
}
window.addPlannerTask = function() {
    const inp = document.getElementById("plannerTaskInput");
    const txt = inp ? inp.value.trim() : "";
    if (!txt) return;
    PRO_STORE.planner_tasks.unshift({ id: "pt_" + Date.now(), text: txt, done: false, date: todayKey() });
    saveProStoreLocal(true);
    renderVaultTab("planner");
};
window.togglePlannerTask = function(id) {
    const t = PRO_STORE.planner_tasks.find(x => x.id === id);
    if (t) t.done = !t.done;
    saveProStoreLocal(true);
    renderVaultTab("planner");
};
window.deletePlannerTask = function(id) {
    PRO_STORE.planner_tasks = PRO_STORE.planner_tasks.filter(x => x.id !== id);
    saveProStoreLocal(true);
    renderVaultTab("planner");
};

// 9. Daily 5-Minute Rapid Booster Quiz
let _rapidIdx = 0;
let _rapidScore = 0;
let _rapidAnswered = false;
function renderVaultRapidQuiz(box) {
    const today = todayKey();
    const doneToday = PRO_STORE.daily_quiz_history[today];
    if (doneToday && _rapidIdx === 0 && !_rapidAnswered) {
        box.innerHTML = `
            <div class="max-w-md mx-auto text-center py-8 space-y-3">
                <div class="text-5xl">🏆</div>
                <h3 class="font-black text-xl">Today's Rapid Quiz Completed!</h3>
                <div class="text-2xl font-black text-emerald-600">${doneToday.score} / ${doneToday.total}</div>
                <p class="text-xs opacity-75 font-semibold">Aapki daily study streak safe hai. Practice ke liye dobara khel sakte hain.</p>
                <button onclick="restartRapidQuiz()" class="btn-watch text-xs px-6">🔄 Play Again</button>
            </div>`;
        return;
    }

    const q = DEFAULT_RAPID_QUIZ[_rapidIdx];
    box.innerHTML = `
        <div class="max-w-xl mx-auto space-y-4">
            <div class="flex justify-between items-center">
                <span class="px-3 py-1 rounded-full bg-amber-100 text-amber-900 text-xs font-black">⚡ Rapid Quiz • Q${_rapidIdx + 1}/${DEFAULT_RAPID_QUIZ.length}</span>
                <span class="font-black text-xs text-emerald-600">Score: ${_rapidScore}</span>
            </div>
            <div class="p-4 rounded-2xl bg-sky-50 dark:bg-slate-800 font-extrabold text-sm">${escHtml(q.q)}</div>
            <div id="rapidOpts" class="space-y-2">
                ${q.opts.map((o, idx) => `
                    <button onclick="answerRapidQ(${idx}, this)" class="w-full text-left p-3.5 rounded-xl bg-white dark:bg-slate-900 border-2 border-sky-200 dark:border-slate-700 font-bold text-xs cursor-pointer hover:border-blue-500">
                        ${["A", "B", "C", "D"][idx]}. ${escHtml(o)}
                    </button>`).join("")}
            </div>
            <div id="rapidExp" class="hidden p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 text-xs font-bold text-emerald-800 dark:text-emerald-300"></div>
            <button id="rapidNextBtn" onclick="nextRapidQ()" class="hidden btn-watch w-full text-xs">Next Question ➔</button>
        </div>`;
}
window.restartRapidQuiz = function() {
    _rapidIdx = 0; _rapidScore = 0; _rapidAnswered = false;
    delete PRO_STORE.daily_quiz_history[todayKey()];
    renderVaultTab("rapid_quiz");
};
window.answerRapidQ = function(chosen, btn) {
    if (_rapidAnswered) return;
    _rapidAnswered = true;
    const q = DEFAULT_RAPID_QUIZ[_rapidIdx];
    const btns = document.querySelectorAll("#rapidOpts button");
    btns.forEach((b, i) => {
        if (i === q.ans) b.className = "w-full text-left p-3.5 rounded-xl bg-emerald-100 border-2 border-emerald-500 text-emerald-950 font-black text-xs";
        else if (i === chosen) b.className = "w-full text-left p-3.5 rounded-xl bg-rose-100 border-2 border-rose-500 text-rose-950 font-black text-xs";
    });
    if (chosen === q.ans) _rapidScore++;
    const exp = document.getElementById("rapidExp");
    exp.textContent = "💡 " + q.exp;
    exp.classList.remove("hidden");
    const nxt = document.getElementById("rapidNextBtn");
    nxt.textContent = _rapidIdx === DEFAULT_RAPID_QUIZ.length - 1 ? "🏁 Finish Rapid Quiz" : "Next Question ➔";
    nxt.classList.remove("hidden");
};
window.nextRapidQ = function() {
    _rapidAnswered = false;
    if (_rapidIdx < DEFAULT_RAPID_QUIZ.length - 1) {
        _rapidIdx++;
        renderVaultTab("rapid_quiz");
    } else {
        PRO_STORE.daily_quiz_history[todayKey()] = { score: _rapidScore, total: DEFAULT_RAPID_QUIZ.length };
        addStudyMinutes(5);
        logUserActivity("RAPID_QUIZ", `Scored ${_rapidScore}/${DEFAULT_RAPID_QUIZ.length}`);
        _rapidIdx = 0;
        renderVaultTab("rapid_quiz");
    }
};

// 10. Multi-Device Cloud Sync + JSON Backup / Restore
function renderVaultBackup(box) {
    box.innerHTML = `
        <div class="max-w-xl mx-auto space-y-5">
            <h3 class="font-black text-lg">☁️ Multi-Device Cloud Sync & JSON Backup</h3>
            <p class="text-xs opacity-80 font-semibold leading-relaxed">
                Aapka poora study data (Watch Progress, Notes, Bookmarks, Mistake Bank, Flashcards, Planner, Scorecards) MongoDB Cloud par auto-sync hota hai. Aap offline JSON backup bhi download ya restore kar sakte hain.
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button onclick="pushCloudSyncNow(true)" class="btn-watch py-3 text-xs">⬆️ Push Data to Cloud</button>
                <button onclick="pullCloudSyncData(true)" class="btn-nav bg-emerald-600 text-white border-0 py-3 text-xs">⬇️ Pull Data from Cloud</button>
                <button onclick="exportProStoreJson()" class="btn-nav bg-indigo-600 text-white border-0 py-3 text-xs">📥 Export JSON File</button>
                <label class="btn-nav bg-amber-500 text-white border-0 py-3 text-xs text-center cursor-pointer">
                    📤 Import JSON Backup
                    <input type="file" accept=".json" onchange="importProStoreJson(event)" class="hidden">
                </label>
            </div>
        </div>`;
}

window.exportProStoreJson = function() {
    const blob = new Blob([JSON.stringify(PRO_STORE, null, 2)], { type: "application/json" });
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u;
    a.download = `RWA_Study_Backup_${todayKey()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 10000);
    proToast("📥 Backup JSON Downloaded!", "success");
};

window.importProStoreJson = function(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
        try {
            const parsed = JSON.parse(reader.result);
            PRO_STORE = { ...createEmptyProStore(), ...parsed };
            saveProStoreLocal(true);
            renderHomeDashboard();
            proToast("✅ Backup Successfully Restored!", "success");
        } catch {
            proToast("❌ Invalid JSON Backup file!", "error");
        }
    };
    reader.readAsText(file);
};

// Init Theme & Network Listener
applySavedTheme();
updateNetworkSpeedBadge();
window.addEventListener("online", updateNetworkSpeedBadge);
window.addEventListener("offline", updateNetworkSpeedBadge);

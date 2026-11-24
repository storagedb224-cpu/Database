// =========================================================
// RWA ULTIMATE ASMANI SKY PRO OTT PLAYER ENGINE (player.js)
// Features: Anti-Leak Custom YouTube Unlisted Player (Zero Logo/Copy),
// Multi-Worker HLS Failover, Lock-Screen Media Session, Speed Auto-Memory,
// Auto-Resume, Double-Tap Seek, Hold 2x, Brightness/Volume Swipe,
// A-B Loop, Board Screenshot, Audio-Only, Sleep Timer, Lock & Split-Screen
// =========================================================

const HLS_STREAM_PROXIES = [
    "https://proplayer.allswbatch22.workers.dev/stream?url=",
    "https://test.src22420.workers.dev/?url="
];
const HLS_SEGMENT_PROXIES = [
    "https://proplayer.allswbatch22.workers.dev/proxy?url=",
    "https://test.src22420.workers.dev/?url="
];

let _activeProxyIdx = 0;

const v = document.getElementById("video");
const input = document.getElementById("url");
const bufferLoader = document.getElementById("bufferLoader");
const hlsScreen = document.getElementById("hlsScreen");
const playerControlsBar = document.getElementById("playerControlsBar");

let hls = null;
let cachedToken = "";
let resumeSeekTime = 0;

// Anti-Leak YouTube Engine State
let _isYtMode = false;
let _ytPlayer = null;
let _ytApiReady = false;
let _ytPendingId = null;
let _ytTickInterval = null;

let _isScreenLocked = false;
let _isAudioOnly = false;
let _brightnessLevel = 1.0;
let _abLoop = { a: null, b: null };
let _sleepTimerId = null;
let _autoPlayTimerId = null;
let _lastProgressSaveTs = 0;
let _sessionWatchSec = 0;
let _lastWatchTickTs = 0;
let _normalSpeedBeforeHold = 1.0;
let _holdSpeedActive = false;
let _failoverAttempted = false;

// =========================================================
// UNIFIED MEDIA ADAPTER (CONTROLS BOTH HLS <video> AND YOUTUBE!)
// =========================================================
function getCurTime() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.getCurrentTime === "function") return _ytPlayer.getCurrentTime() || 0;
    return (v && Number.isFinite(v.currentTime)) ? v.currentTime : 0;
}
function getDuration() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.getDuration === "function") return _ytPlayer.getDuration() || 0;
    return (v && Number.isFinite(v.duration)) ? v.duration : 0;
}
function isPaused() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.getPlayerState === "function") return _ytPlayer.getPlayerState() !== 1;
    return !v || v.paused;
}
function mediaPlay() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.playVideo === "function") _ytPlayer.playVideo();
    else if (v) v.play().catch(() => {});
}
function mediaPause() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.pauseVideo === "function") _ytPlayer.pauseVideo();
    else if (v) v.pause();
}
function mediaSeek(sec) {
    const dur = getDuration();
    const target = Math.max(0, dur > 0 ? Math.min(dur, sec) : sec);
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.seekTo === "function") _ytPlayer.seekTo(target, true);
    else if (v) v.currentTime = target;
}
function mediaSetRate(rate) {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.setPlaybackRate === "function") _ytPlayer.setPlaybackRate(rate);
    else if (v) v.playbackRate = rate;
}
function mediaSetMuted(m) {
    if (_isYtMode && _ytPlayer) { m ? _ytPlayer.mute() : _ytPlayer.unMute(); }
    else if (v) v.muted = m;
}
function mediaIsMuted() {
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.isMuted === "function") return _ytPlayer.isMuted();
    return Boolean(v && v.muted);
}
function mediaSetVolume(vol01) {
    const clamped = Math.min(1, Math.max(0, vol01));
    if (_isYtMode && _ytPlayer && typeof _ytPlayer.setVolume === "function") _ytPlayer.setVolume(Math.round(clamped * 100));
    else if (v) v.volume = clamped;
}

// =========================================================
// ANTI-LEAK YOUTUBE IFRAME API MOUNTING (ZERO LOGO / ZERO COPY)
// =========================================================
function ensureYtAntiLeakDom() {
    if (!hlsScreen || document.getElementById("ytAntiLeakWrap")) return;
    const wrap = document.createElement("div");
    wrap.id = "ytAntiLeakWrap";
    wrap.className = "hidden";
    wrap.style.cssText = "position:absolute;inset:0;width:100%;height:100%;background:#000;overflow:hidden;z-index:2;";
    // Oversize iframe slightly vertically so top title bar & bottom YouTube branding are clipped cleanly
    wrap.innerHTML = `
        <div id="ytApiMount" style="position:absolute;top:-54px;left:0;width:100%;height:calc(100% + 108px);pointer-events:none;"></div>
        <div id="ytAntiLeakShield" oncontextmenu="return false;" style="position:absolute;inset:0;z-index:4;background:transparent;"></div>
    `;
    hlsScreen.insertBefore(wrap, hlsScreen.firstChild);
}

function loadYouTubeIframeApi() {
    if (window.YT && window.YT.Player) { _ytApiReady = true; return; }
    if (document.getElementById("yt-iframe-api-script")) return;
    const tag = document.createElement("script");
    tag.id = "yt-iframe-api-script";
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
}
loadYouTubeIframeApi();

window.onYouTubeIframeAPIReady = function() {
    _ytApiReady = true;
    if (_ytPendingId) {
        const id = _ytPendingId;
        _ytPendingId = null;
        mountAntiLeakYouTube(id);
    }
};

function mountAntiLeakYouTube(videoId) {
    ensureYtAntiLeakDom();
    _isYtMode = true;
    document.getElementById("ytScreen")?.classList.add("hidden");
    hlsScreen?.classList.remove("hidden");
    if (v) v.style.visibility = "hidden";
    const wrap = document.getElementById("ytAntiLeakWrap");
    if (wrap) wrap.classList.remove("hidden");

    if (!_ytApiReady || !(window.YT && window.YT.Player)) {
        _ytPendingId = videoId;
        loadYouTubeIframeApi();
        return;
    }

    if (_ytPlayer && typeof _ytPlayer.loadVideoById === "function") {
        _ytPlayer.loadVideoById(videoId);
        startYtProgressTicker();
        return;
    }

    _ytPlayer = new YT.Player("ytApiMount", {
        videoId,
        playerVars: {
            autoplay: 1,
            controls: 0,
            disablekb: 1,
            fs: 0,
            iv_load_policy: 3,
            modestbranding: 1,
            playsinline: 1,
            rel: 0,
            origin: window.location.origin
        },
        events: {
            onReady: () => {
                showLoader(false);
                populateQualitySettings([]);
                applyAutoResumeIfAvailable();
                applySavedPlaybackRate();
                setupLockScreenMediaSession();
                if (typeof state !== "undefined") renderSeekbarNoteMarkers(state.activeKey);
                _ytPlayer.playVideo();
                startYtProgressTicker();
            },
            onStateChange: (ev) => {
                const st = ev.data;
                const toggleBtn = document.getElementById("toggle");
                if (st === 1) {
                    showLoader(false);
                    if (toggleBtn) toggleBtn.textContent = "⏸";
                    _lastWatchTickTs = Date.now();
                    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing";
                } else if (st === 2) {
                    if (toggleBtn) toggleBtn.textContent = "▶";
                    flushWatchSessionMinutes();
                    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused";
                    saveCurrentProgressNow();
                } else if (st === 3) {
                    showLoader(true);
                } else if (st === 0) {
                    flushWatchSessionMinutes();
                    saveCurrentProgressNow(true);
                    triggerAutoPlayNextCountdown();
                }
            },
            onError: () => {
                showLoader(false);
                if (typeof proToast === "function") proToast("⚠️ YouTube stream error — fallback try karein.", "warning");
            }
        }
    });
}

function startYtProgressTicker() {
    if (_ytTickInterval) clearInterval(_ytTickInterval);
    _ytTickInterval = setInterval(() => {
        if (!_isYtMode || !_ytPlayer) return;
        handleUnifiedTimeTick();
    }, 500);
}

function getStreamProxy() { return HLS_STREAM_PROXIES[_activeProxyIdx] || HLS_STREAM_PROXIES[0]; }
function getSegmentProxy() { return HLS_SEGMENT_PROXIES[_activeProxyIdx] || HLS_SEGMENT_PROXIES[0]; }
function showLoader(show) { bufferLoader?.classList.toggle("hidden", !show); }
function showGestureHud(text, autoHideMs = 1200) {
    const hud = document.getElementById("gestureHud"); if (!hud) return;
    hud.textContent = text; hud.classList.remove("hidden");
    clearTimeout(hud._t);
    if (autoHideMs > 0) hud._t = setTimeout(() => hud.classList.add("hidden"), autoHideMs);
}
function valid(u) { try { return ["http:", "https:"].includes(new URL(u).protocol); } catch { return false; } }
function unwrapOriginalUrl(u) {
    if (!u) return "";
    try { const p = new URL(u); if (p.hostname.includes("workers.dev") && p.searchParams.has("url")) return decodeURIComponent(p.searchParams.get("url")); } catch {}
    return u;
}
function manifest(u) {
    const rawUrl = unwrapOriginalUrl(u);
    try { const x = new URL(rawUrl); if (x.pathname.toLowerCase().includes(".m3u8") || x.hostname.includes("classx.co.in") || x.hostname.includes("akamai.net.in")) return getStreamProxy() + encodeURIComponent(rawUrl); } catch {}
    return rawUrl;
}
function segment(u) { return /\.(ts|m4s|mp4|aac|mp3|vtt|webvtt)(\?|$)/i.test(u.split("?")[0]); }

class BackendLoader extends Hls.DefaultConfig.loader {
    load(ctx, cfg, cb) {
        let originalUrl = ctx.url, mainUrl = input ? unwrapOriginalUrl(input.value.trim()) : "";
        let match = mainUrl.match(/(edge-cache-token=[^&]+)/);
        if (match) cachedToken = match[1];
        if (originalUrl.includes("workers.dev")) { ctx.url = originalUrl; super.load(ctx, cfg, cb); return; }
        if (cachedToken && !originalUrl.includes("edge-cache-token=")) originalUrl += (originalUrl.includes("?") ? "&" : "?") + cachedToken;
        if (originalUrl.includes(".m3u8")) ctx.url = getStreamProxy() + encodeURIComponent(originalUrl);
        else if (segment(originalUrl)) ctx.url = getSegmentProxy() + encodeURIComponent(originalUrl);
        else ctx.url = originalUrl;
        super.load(ctx, cfg, cb);
    }
}

function setupLockScreenMediaSession() {
    if (!("mediaSession" in navigator)) return;
    try {
        const info = (typeof state !== "undefined" && state.activeKey && state.mediaMap) ? state.mediaMap[state.activeKey] : null;
        navigator.mediaSession.metadata = new MediaMetadata({
            title: (info && info.title) || "RWA Sky Pro Class",
            artist: (typeof state !== "undefined" && state.courseName) ? state.courseName : "RWA Sky Pro",
            album: "RWA Course Vault",
            artwork: [{ src: (info && info.thumb) || "https://placehold.co/512x512/0284c7/ffffff.png?text=RWA", sizes: "512x512", type: "image/png" }]
        });
        navigator.mediaSession.setActionHandler("play", () => mediaPlay());
        navigator.mediaSession.setActionHandler("pause", () => mediaPause());
        navigator.mediaSession.setActionHandler("seekbackward", () => mediaSeek(getCurTime() - 10));
        navigator.mediaSession.setActionHandler("seekforward", () => mediaSeek(getCurTime() + 10));
        navigator.mediaSession.setActionHandler("nexttrack", () => playNextClassNow());
    } catch {}
}

function getSavedPlaybackRate() {
    const saved = (window.PRO_STORE && PRO_STORE.preferences && Number(PRO_STORE.preferences.playbackRate))
        || Number(localStorage.getItem("rwa_saved_playback_rate") || 1);
    return (saved >= 0.5 && saved <= 2.5) ? saved : 1.0;
}
function applySavedPlaybackRate() {
    const rate = getSavedPlaybackRate();
    mediaSetRate(rate);
    document.querySelectorAll(".spd-option").forEach(o => {
        const val = parseFloat(o.dataset.spd || o.textContent);
        o.classList.toggle("active", Math.abs(val - rate) < 0.01);
    });
}

function saveCurrentProgressNow(forceComplete = false) {
    const dur = getDuration();
    if (typeof state !== "undefined" && state.activeKey && state.mediaMap[state.activeKey] && dur > 0) {
        if (typeof recordWatchProgress === "function") {
            recordWatchProgress(state.mediaMap[state.activeKey], forceComplete ? dur : getCurTime(), dur);
        }
    }
}

function flushWatchSessionMinutes() {
    if (_sessionWatchSec >= 15) {
        const mins = _sessionWatchSec / 60;
        if (typeof addStudyMinutes === "function") addStudyMinutes(mins);
        if (typeof logUserActivity === "function" && typeof state !== "undefined" && state.activeKey) {
            const info = state.mediaMap[state.activeKey];
            logUserActivity("WATCH_VIDEO", info ? info.title : "Class Video", { watch_seconds: Math.round(_sessionWatchSec) });
        }
        _sessionWatchSec = 0;
    }
}

function resetAbLoop() {
    _abLoop = { a: null, b: null };
    document.getElementById("abLoopBadge")?.classList.add("hidden");
    document.getElementById("abLoopBtn")?.classList.remove("active-loop");
}

function stopPlayer() {
    flushWatchSessionMinutes();
    cancelAutoPlayNext();
    resetAbLoop();
    if (_ytTickInterval) { clearInterval(_ytTickInterval); _ytTickInterval = null; }
    if (_ytPlayer && typeof _ytPlayer.stopVideo === "function") { try { _ytPlayer.stopVideo(); } catch {} }
    document.getElementById("ytAntiLeakWrap")?.classList.add("hidden");
    _isYtMode = false;

    if (hls) { try { hls.destroy(); } catch {} hls = null; }
    if (v) { v.style.visibility = "visible"; v.pause(); v.removeAttribute("src"); v.load(); }
    const ytFrame = document.getElementById("ytFrame"); if (ytFrame) ytFrame.src = "";
    showLoader(false);
}

window.closePlayerBox = function() {
    saveCurrentProgressNow(false);
    stopPlayer();
    togglePlayerScreenLock(false);
    document.body.classList.remove("zen-mode");
    const zenBtn = document.getElementById("zenModeBtn"); if (zenBtn) zenBtn.textContent = "🧘 Zen";
    document.getElementById("settingsMenu")?.classList.remove("show");
    if (typeof closeInlinePdfAndReset === "function") closeInlinePdfAndReset();
    if (typeof showSlide === "function") showSlide("slideExplorer");
};

function applyAutoResumeIfAvailable() {
    if (resumeSeekTime > 0) { mediaSeek(resumeSeekTime); resumeSeekTime = 0; return; }
    if (typeof state !== "undefined" && state.activeKey && typeof getWatchProgress === "function") {
        const saved = getWatchProgress(state.activeKey), dur = getDuration();
        if (saved && saved.time > 5 && saved.pct < 96 && dur > 0 && saved.time < dur - 5) {
            mediaSeek(saved.time);
            showGestureHud(`▶ Resumed from ${fmt(saved.time)}`, 1800);
        }
    }
}

function start(isFailoverRetry = false) {
    let raw = input ? input.value.trim() : "";
    if (!raw) return;
    if (!isFailoverRetry) { _activeProxyIdx = 0; _failoverAttempted = false; }

    stopPlayer();
    showLoader(true);

    const cleanRaw = unwrapOriginalUrl(raw);
    const isYT = (!cleanRaw.startsWith("http") && cleanRaw.length >= 10 && cleanRaw.length <= 15) || cleanRaw.includes("youtube.com") || cleanRaw.includes("youtu.be");

    if (isYT) {
        let ytId = cleanRaw;
        if (cleanRaw.includes("v=")) ytId = cleanRaw.split("v=")[1].split("&")[0];
        else if (cleanRaw.includes("youtu.be/")) ytId = cleanRaw.split("youtu.be/")[1].split("?")[0];
        mountAntiLeakYouTube(ytId.trim());
        return;
    }

    document.getElementById("ytScreen")?.classList.add("hidden");
    hlsScreen?.classList.remove("hidden");
    if (!valid(cleanRaw)) { showLoader(false); return; }

    let tokMatch = cleanRaw.match(/(edge-cache-token=[^&]+)/);
    if (tokMatch) cachedToken = tokMatch[1];

    if (cleanRaw.includes(".mp4") && !cleanRaw.includes(".m3u8")) {
        v.src = cleanRaw;
        populateQualitySettings([]);
        v.onloadedmetadata = () => {
            showLoader(false); applyAutoResumeIfAvailable(); applySavedPlaybackRate(); setupLockScreenMediaSession();
            if (typeof state !== "undefined") renderSeekbarNoteMarkers(state.activeKey);
            v.play().catch(() => {});
        };
        return;
    }

    let src = manifest(cleanRaw);
    if (Hls.isSupported()) {
        hls = new Hls({ enableWorker: true, lowLatencyMode: false, backBufferLength: 30, maxBufferLength: 25, loader: BackendLoader });
        hls.on(Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(src));
        hls.on(Hls.Events.MANIFEST_PARSED, (_, data) => {
            showLoader(false);
            populateQualitySettings(data.levels || []);
            v.onloadedmetadata = () => {
                applyAutoResumeIfAvailable(); applySavedPlaybackRate(); setupLockScreenMediaSession();
                if (typeof state !== "undefined") renderSeekbarNoteMarkers(state.activeKey);
            };
            applySavedPlaybackRate(); setupLockScreenMediaSession();
            v.play().catch(() => {});
        });
        hls.on(Hls.Events.ERROR, (_, d) => {
            if (d.fatal) {
                if (d.type === Hls.ErrorTypes.MEDIA_ERROR) { try { hls.recoverMediaError(); } catch {} }
                else if (d.type === Hls.ErrorTypes.NETWORK_ERROR && !_failoverAttempted && HLS_STREAM_PROXIES.length > 1) {
                    _failoverAttempted = true;
                    _activeProxyIdx = (_activeProxyIdx + 1) % HLS_STREAM_PROXIES.length;
                    resumeSeekTime = getCurTime();
                    showGestureHud("🔄 Switching to Backup Stream Worker...", 1800);
                    start(true);
                } else {
                    showLoader(false);
                    if (typeof logPortalError === "function") logPortalError("HLSPlayer", `Fatal ${d.type}: ${d.details}`);
                    if (typeof proToast === "function") proToast("⚠️ Stream weak hai, quality switch karke try karein.", "warning");
                }
            }
        });
        hls.attachMedia(v);
    } else if (v.canPlayType("application/vnd.apple.mpegurl")) {
        v.src = src;
        v.onloadedmetadata = () => {
            showLoader(false); applyAutoResumeIfAvailable(); applySavedPlaybackRate(); setupLockScreenMediaSession();
            if (typeof state !== "undefined") renderSeekbarNoteMarkers(state.activeKey);
            v.play().catch(() => {});
        };
    }
}

window.cycleAbLoop = function() {
    if (getDuration() <= 0) return;
    const badge = document.getElementById("abLoopBadge"), btn = document.getElementById("abLoopBtn");
    const cur = getCurTime();
    if (_abLoop.a === null) {
        _abLoop.a = cur;
        if (badge) { badge.textContent = `🔁 Point A Set: ${fmt(_abLoop.a)} (Click again for B)`; badge.classList.remove("hidden"); }
        if (btn) btn.classList.add("active-loop");
        showGestureHud(`🔁 Loop Point A: ${fmt(_abLoop.a)}`);
    } else if (_abLoop.b === null) {
        if (cur <= _abLoop.a + 1) return proToast("Point B, Point A ke baad hona chahiye.", "warning");
        _abLoop.b = cur;
        if (badge) badge.textContent = `🔁 Looping: ${fmt(_abLoop.a)} ➔ ${fmt(_abLoop.b)}`;
        mediaSeek(_abLoop.a);
        showGestureHud(`🔁 Loop Active (${fmt(_abLoop.a)} - ${fmt(_abLoop.b)})`, 1600);
    } else { resetAbLoop(); showGestureHud("🔁 A-B Loop Cleared"); }
};

window.captureBoardScreenshot = function() {
    if (_isYtMode) return proToast("YouTube mode mein phone ka screenshot use karein.", "info");
    if (!v || !v.videoWidth) return proToast("Video load hone ke baad screenshot lein.", "warning");
    try {
        const canvas = document.createElement("canvas");
        canvas.width = v.videoWidth; canvas.height = v.videoHeight;
        canvas.getContext("2d").drawImage(v, 0, 0, canvas.width, canvas.height);
        const a = document.createElement("a"); a.href = canvas.toDataURL("image/png"); a.download = `RWA_Board_${fmt(getCurTime()).replace(/:/g, "-")}.png`;
        document.body.appendChild(a); a.click(); a.remove();
        showGestureHud("📸 Board Screenshot Saved!", 1400);
    } catch { proToast("Is stream par direct screenshot CORS-protected hai.", "warning"); }
};

window.toggleAudioOnlyMode = function() {
    _isAudioOnly = !_isAudioOnly;
    document.getElementById("audioOnlyBanner")?.classList.toggle("hidden", !_isAudioOnly);
    setupLockScreenMediaSession();
    showGestureHud(_isAudioOnly ? "🎧 Audio-Only Mode ON" : "🎬 Video Mode ON");
};

window.setPlayerSleepTimer = function(minsStr) {
    if (_sleepTimerId) clearTimeout(_sleepTimerId);
    const mins = parseInt(minsStr || "0", 10);
    if (mins <= 0) return proToast("🌙 Sleep Timer OFF", "info");
    _sleepTimerId = setTimeout(() => { mediaPause(); proToast(`🌙 ${mins}m Sleep Timer complete — Paused.`, "info"); }, mins * 60 * 1000);
    proToast(`🌙 Sleep Timer set for ${mins} mins`, "success");
};

window.togglePlayerScreenLock = function(lock) {
    _isScreenLocked = Boolean(lock);
    document.getElementById("screenUnlockOverlay")?.classList.toggle("hidden", !_isScreenLocked);
    playerControlsBar?.classList.toggle("hidden-controls", _isScreenLocked);
    showGestureHud(_isScreenLocked ? "🔒 Screen Locked" : "🔓 Screen Unlocked");
};

window.toggleSplitScreenMode = function() {
    const wrap = document.getElementById("playerSplitContainer"), pdfBox = document.getElementById("inlinePdfBox");
    if (!wrap) return;
    const active = wrap.classList.toggle("split-active");
    if (active && pdfBox && pdfBox.classList.contains("hidden") && typeof openActivePlayerPdf === "function") openActivePlayerPdf(1);
    proToast(active ? "🗔 Split-Screen Mode ON" : "📺 Normal Full-Width Video", "info");
};

window.seekToTimestamp = function(sec) { if (Number.isFinite(sec)) { mediaSeek(sec); mediaPlay(); showGestureHud(`⏩ Jumped to ${fmt(sec)}`); } };
window.renderSeekbarNoteMarkers = function(key) {
    const cont = document.getElementById("seekNotesMarkers"), dur = getDuration();
    if (!cont || dur <= 0) return;
    const notes = (window.PRO_STORE && PRO_STORE.video_notes && PRO_STORE.video_notes[key]) || [];
    cont.innerHTML = notes.map(n => `<span class="note-dot-marker" style="left:${Math.min(99, Math.max(1, (n.time / dur) * 100))}%;" title="${escHtml(n.text)}"></span>`).join("");
};

function triggerAutoPlayNextCountdown() {
    const toggle = document.getElementById("autoPlayNextToggle");
    if (toggle && !toggle.checked) return;
    if (typeof state === "undefined" || !state.currentLectureKeys) return;
    const idx = state.currentLectureKeys.indexOf(state.activeKey);
    if (idx < 0 || idx >= state.currentLectureKeys.length - 1) return;
    const nextKey = state.currentLectureKeys[idx + 1], nextInfo = state.mediaMap[nextKey];
    if (!nextInfo) return;
    const ov = document.getElementById("autoPlayOverlay"), cntEl = document.getElementById("autoPlayCountdown"), titleEl = document.getElementById("autoPlayNextTitle");
    if (!ov) return;
    ov.dataset.nextKey = nextKey;
    if (titleEl) titleEl.textContent = nextInfo.title;
    ov.classList.remove("hidden");
    let left = 5; if (cntEl) cntEl.textContent = left;
    cancelAutoPlayNext(false);
    _autoPlayTimerId = setInterval(() => { left--; if (cntEl) cntEl.textContent = left; if (left <= 0) playNextClassNow(); }, 1000);
}
window.playNextClassNow = function() {
    const ov = document.getElementById("autoPlayOverlay");
    let nextKey = ov ? ov.dataset.nextKey : "";
    if (!nextKey && typeof state !== "undefined" && state.currentLectureKeys) {
        const idx = state.currentLectureKeys.indexOf(state.activeKey);
        if (idx >= 0 && idx < state.currentLectureKeys.length - 1) nextKey = state.currentLectureKeys[idx + 1];
    }
    cancelAutoPlayNext(true);
    if (nextKey && typeof playClassInRwaPlayer === "function") playClassInRwaPlayer(nextKey);
};
window.cancelAutoPlayNext = function(hide = true) {
    if (_autoPlayTimerId) { clearInterval(_autoPlayTimerId); _autoPlayTimerId = null; }
    if (hide) document.getElementById("autoPlayOverlay")?.classList.add("hidden");
};

// UNIFIED GESTURES (WORKS ON BOTH YOUTUBE ANTI-LEAK & HLS!)
(function initProPlayerGestures() {
    if (!hlsScreen) return;
    let lastTapTime = 0, singleTapTimer = null, holdTimer = null, touchStartX = 0, touchStartY = 0, touchStartVol = 1, touchStartBright = 1, swipeMode = null;

    function triggerRipple(side) {
        const el = document.getElementById(side === "left" ? "rippleLeft" : "rippleRight"); if (!el) return;
        el.classList.remove("hidden"); clearTimeout(el._t); el._t = setTimeout(() => el.classList.add("hidden"), 550);
    }
    function startHold2x() {
        if (_isScreenLocked || isPaused()) return;
        _normalSpeedBeforeHold = getSavedPlaybackRate();
        mediaSetRate(2.0); _holdSpeedActive = true;
        showGestureHud("⚡ 2.0x Speed Holding...", 0);
    }
    function endHold2x() {
        if (!_holdSpeedActive) return;
        _holdSpeedActive = false; mediaSetRate(_normalSpeedBeforeHold);
        document.getElementById("gestureHud")?.classList.add("hidden");
    }

    hlsScreen.addEventListener("touchstart", (e) => {
        if (_isScreenLocked || e.target.closest("button") || e.target.closest("input") || e.target.closest("#settingsMenu")) return;
        const t = e.touches[0]; touchStartX = t.clientX; touchStartY = t.clientY;
        touchStartVol = v ? v.volume : 1; touchStartBright = _brightnessLevel; swipeMode = null;
        holdTimer = setTimeout(startHold2x, 480);
    }, { passive: true });

    hlsScreen.addEventListener("touchmove", (e) => {
        if (_isScreenLocked || !e.touches[0]) return;
        const dx = e.touches[0].clientX - touchStartX, dy = touchStartY - e.touches[0].clientY;
        if (Math.abs(dy) > 16 && Math.abs(dy) > Math.abs(dx)) {
            clearTimeout(holdTimer);
            const rect = hlsScreen.getBoundingClientRect(), isLeft = (touchStartX - rect.left) < rect.width / 2, delta = dy / (rect.height * 0.75);
            if (isLeft) {
                swipeMode = "brightness";
                _brightnessLevel = Math.min(1.6, Math.max(0.35, touchStartBright + delta));
                const targetEl = _isYtMode ? document.getElementById("ytAntiLeakWrap") : v;
                if (targetEl) targetEl.style.filter = `brightness(${_brightnessLevel.toFixed(2)})`;
                showGestureHud(`☀️ Brightness ${Math.round(_brightnessLevel * 100)}%`, 900);
            } else {
                swipeMode = "volume";
                const nv = Math.min(1, Math.max(0, touchStartVol + delta));
                mediaSetVolume(nv); mediaSetMuted(nv === 0);
                showGestureHud(`🔊 Volume ${Math.round(nv * 100)}%`, 900);
            }
        }
    }, { passive: true });

    hlsScreen.addEventListener("touchend", () => { clearTimeout(holdTimer); endHold2x(); });
    hlsScreen.addEventListener("mousedown", (e) => {
        if (_isScreenLocked || e.target.closest("button") || e.target.closest("input") || e.target.closest("#settingsMenu")) return;
        holdTimer = setTimeout(startHold2x, 500);
    });
    window.addEventListener("mouseup", () => { clearTimeout(holdTimer); endHold2x(); });

    hlsScreen.addEventListener("click", (e) => {
        if (_isScreenLocked || e.target.closest("button") || e.target.closest("input") || e.target.closest("#settingsMenu")) return;
        if (swipeMode) { swipeMode = null; return; }
        const now = Date.now(), rect = hlsScreen.getBoundingClientRect(), relX = (e.clientX - rect.left) / rect.width;
        if (now - lastTapTime < 280) {
            clearTimeout(singleTapTimer); lastTapTime = 0;
            if (relX < 0.4) { mediaSeek(getCurTime() - 10); triggerRipple("left"); }
            else if (relX > 0.6) { mediaSeek(getCurTime() + 10); triggerRipple("right"); }
            else { isPaused() ? mediaPlay() : mediaPause(); }
            return;
        }
        lastTapTime = now;
        singleTapTimer = setTimeout(() => {
            playerControlsBar?.classList.toggle("hidden-controls");
            document.getElementById("settingsMenu")?.classList.remove("show");
        }, 280);
    });
})();

document.addEventListener("keydown", (e) => {
    if (typeof state === "undefined" || state.currentSlide !== "slidePlayer") return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.code === "Space") { e.preventDefault(); isPaused() ? mediaPlay() : mediaPause(); }
    else if (e.code === "ArrowLeft") { mediaSeek(getCurTime() - 10); showGestureHud("⏪ -10s"); }
    else if (e.code === "ArrowRight") { mediaSeek(getCurTime() + 10); showGestureHud("⏩ +10s"); }
    else if (e.key.toLowerCase() === "m") { const m = !mediaIsMuted(); mediaSetMuted(m); showGestureHud(m ? "🔇 Muted" : "🔊 Unmuted"); }
    else if (e.key.toLowerCase() === "f") { document.getElementById("fs")?.click(); }
});

function populateQualitySettings(hlsLevels) {
    const qList = document.getElementById("qualityList"); if (!qList) return;
    if (_isYtMode) { qList.innerHTML = `<div class="q-option active" onclick="toggleSettingsMenu()">Auto HD (YouTube)</div>`; return; }
    const activeInfo = (typeof state !== "undefined" && state.activeKey && state.mediaMap) ? state.mediaMap[state.activeKey] : null;
    const serverQualsObj = (activeInfo && activeInfo.qualities) ? activeInfo.qualities : {};
    const serverKeys = Object.keys(serverQualsObj);

    let html = "";
    if (serverKeys.length > 0) {
        const currentRaw = unwrapOriginalUrl(input.value);
        serverKeys.forEach((qKey, idx) => {
            const isAct = (currentRaw && unwrapOriginalUrl(serverQualsObj[qKey]) === currentRaw) || (!currentRaw && idx === 0);
            html += `<div class="q-option ${isAct ? "active" : ""}" onclick="switchServerQuality('${qKey.replace(/'/g, "")}', this)">${qKey}</div>`;
        });
    } else if (hlsLevels && hlsLevels.length > 1) {
        html += `<div class="q-option active" onclick="changeHlsLevel(-1, this)">Auto</div>`;
        const seen = new Set();
        hlsLevels.forEach((lvl, idx) => { const lbl = lvl.height ? `${lvl.height}p` : `${idx + 1}p`; if (!seen.has(lbl)) { seen.add(lbl); html += `<div class="q-option" onclick="changeHlsLevel(${idx}, this)">${lbl}</div>`; } });
    } else html = `<div class="q-option active" onclick="toggleSettingsMenu()">720p HD</div>`;
    qList.innerHTML = html;
}

window.changeHlsLevel = function(idx, el) { if (hls) hls.currentLevel = idx; document.querySelectorAll("#qualityList .q-option").forEach(o => o.classList.remove("active")); el?.classList.add("active"); toggleSettingsMenu(); };
window.switchServerQuality = function(qKey, el) { resumeSeekTime = getCurTime(); document.querySelectorAll("#qualityList .q-option").forEach(o => o.classList.remove("active")); el?.classList.add("active"); toggleSettingsMenu(); if (typeof changeLectureQuality === "function") changeLectureQuality(qKey, resumeSeekTime); };
window.changeSpd = function(rate, el) {
    mediaSetRate(rate);
    localStorage.setItem("rwa_saved_playback_rate", String(rate));
    if (window.PRO_STORE && PRO_STORE.preferences) { PRO_STORE.preferences.playbackRate = rate; if (typeof saveProStoreLocal === "function") saveProStoreLocal(false); }
    document.querySelectorAll(".spd-option").forEach(o => o.classList.remove("active"));
    el?.classList.add("active");
    toggleSettingsMenu();
    showGestureHud(`⚡ Speed ${rate}x (Saved)`);
};
window.toggleSettingsMenu = function() { document.getElementById("settingsMenu")?.classList.toggle("show"); };

async function downloadMerged() {
    if (_isYtMode) return proToast("YouTube Cloud Mode mein video streaming ultra-fast hai (Download sirf HLS mode mein available hai).", "info");
    const raw = input ? unwrapOriginalUrl(input.value.trim()) : "";
    if (!valid(raw) || !hls || !hls.levels || !hls.levels.length) return proToast("Video play hone ke baad download click karein.", "warning");

    const box = document.getElementById("downloadBox"), text = document.getElementById("downloadText"), bar = document.getElementById("bar");
    box?.classList.add("show"); if (bar) bar.style.width = "2%"; if (text) text.textContent = "Preparing video segments...";
    try {
        let levelIndex = hls.currentLevel >= 0 ? hls.currentLevel : 0, fragments = hls.levels[levelIndex].details.fragments;
        let downloadedBuffers = [], total = fragments.length, match = raw.match(/(edge-cache-token=[^&]+)/), tokenStr = match ? match[1] : cachedToken;
        if (fragments[0] && fragments[0].initSegment) {
            let iu = fragments[0].initSegment.url;
            if (!iu.includes("workers.dev")) { if (tokenStr && !iu.includes("edge-cache-token=")) iu += (iu.includes("?") ? "&" : "?") + tokenStr; iu = getSegmentProxy() + encodeURIComponent(iu); }
            let r = await fetch(iu); if (r.ok) downloadedBuffers.push(await r.arrayBuffer());
        }
        for (let i = 0; i < total; i++) {
            if (text) text.textContent = `Downloading: ${i + 1} / ${total} (${Math.round(((i + 1) / total) * 100)}%)`;
            let su = fragments[i].url;
            if (!su.includes("workers.dev")) { if (tokenStr && !su.includes("edge-cache-token=")) su += (su.includes("?") ? "&" : "?") + tokenStr; su = getSegmentProxy() + encodeURIComponent(su); }
            let sr = await fetch(su); if (!sr.ok) throw new Error(`Segment ${i + 1}`);
            downloadedBuffers.push(await sr.arrayBuffer());
            if (bar) bar.style.width = Math.round(((i + 1) / total) * 100) + "%";
        }
        const blob = new Blob(downloadedBuffers, { type: "video/mp4" }), url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `RWA_Class_${Math.floor(Math.random() * 10000)}.mp4`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        if (text) text.textContent = "✅ Download Complete!";
        if (typeof logUserActivity === "function") logUserActivity("DOWNLOAD_VIDEO", "Downloaded merged MP4");
        setTimeout(() => box?.classList.remove("show"), 4000);
    } catch (e) { if (text) text.textContent = "⚠️ Download error: " + e.message; }
}

function fmt(x) {
    if (!Number.isFinite(x)) return "00:00";
    x = Math.floor(x);
    let h = Math.floor(x / 3600), m = Math.floor((x % 3600) / 60), s = x % 60;
    return h ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function handleUnifiedTimeTick() {
    const cur = getCurTime(), d = getDuration();
    const seekEl = document.getElementById("seek"), timeEl = document.getElementById("time"), notePill = document.getElementById("noteCurrentTimePill");
    if (d > 0 && seekEl) seekEl.value = (cur / d) * 1000;
    if (timeEl) timeEl.textContent = fmt(cur) + " / " + fmt(d);
    if (notePill) notePill.textContent = "⏱️ " + fmt(cur);

    if (_abLoop.a !== null && _abLoop.b !== null && cur >= _abLoop.b) mediaSeek(_abLoop.a);

    const now = Date.now();
    if (!isPaused() && _lastWatchTickTs > 0) {
        const deltaSec = (now - _lastWatchTickTs) / 1000;
        if (deltaSec > 0 && deltaSec < 5) _sessionWatchSec += deltaSec;
    }
    _lastWatchTickTs = now;

    if (now - _lastProgressSaveTs > 6000 && d > 0) {
        _lastProgressSaveTs = now;
        saveCurrentProgressNow(false);
    }
}

const toggleBtn = document.getElementById("toggle");
if (toggleBtn) toggleBtn.onclick = () => isPaused() ? mediaPlay() : mediaPause();

v.onplay = () => { if (toggleBtn) toggleBtn.textContent = "⏸"; showLoader(false); _lastWatchTickTs = Date.now(); if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing"; };
v.onpause = () => { if (toggleBtn) toggleBtn.textContent = "▶"; flushWatchSessionMinutes(); saveCurrentProgressNow(false); if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused"; };
v.onended = () => { flushWatchSessionMinutes(); saveCurrentProgressNow(true); triggerAutoPlayNextCountdown(); };
v.onwaiting = () => showLoader(true);
v.onplaying = () => showLoader(false);
v.oncanplay = () => showLoader(false);
v.ontimeupdate = () => { if (!_isYtMode) handleUnifiedTimeTick(); };

document.getElementById("back")?.addEventListener("click", () => mediaSeek(getCurTime() - 10));
document.getElementById("next")?.addEventListener("click", () => mediaSeek(getCurTime() + 10));
const muteBtn = document.getElementById("mute");
if (muteBtn) muteBtn.onclick = () => { const m = !mediaIsMuted(); mediaSetMuted(m); muteBtn.textContent = m ? "🔇" : "🔊"; };
document.getElementById("download")?.addEventListener("click", downloadMerged);
document.getElementById("pip")?.addEventListener("click", async () => {
    if (_isYtMode) return;
    try { if (document.pictureInPictureElement) await document.exitPictureInPicture(); else if (v.requestPictureInPicture) await v.requestPictureInPicture(); } catch {}
});
const fsBtn = document.getElementById("fs"), headerBar = document.getElementById("playerHeaderBar");
if (fsBtn && hlsScreen) fsBtn.onclick = async () => { try { if (!document.fullscreenElement) await hlsScreen.requestFullscreen(); else await document.exitFullscreen(); } catch {} };
document.addEventListener("fullscreenchange", () => {
    if (document.fullscreenElement) { headerBar?.classList.add("hidden"); if (fsBtn) fsBtn.textContent = "🗗"; }
    else { headerBar?.classList.remove("hidden"); if (fsBtn) fsBtn.textContent = "⛶"; }
});
const seekEl = document.getElementById("seek");
if (seekEl) seekEl.oninput = (e) => { const d = getDuration(); if (d > 0) mediaSeek((e.target.value / 1000) * d); };

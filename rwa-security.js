// =========================================================
// RWA ULTRA SECURITY CLIENT (rwa-security.js)
// Layer 1: Signed Request (HMAC-SHA256 + Unix Timestamp)
// Layer 2: End-to-End AES-256-CBC Encrypted Tunnel (Request + Response)
// Layer 3: Persistent Device Fingerprint + Console Leak Shield
// =========================================================

(function initRwaSecurityShield() {
    // IMPORTANT: Yeh dono keys aapke Render backend (config.py / Environment) se EXACT match honi chahiye
    const RWA_SIGNING_SECRET = "RWA_HMAC_SHIELD_2026_ULTRA_KEY_22";
    const RWA_TRANSPORT_AES_KEY = "RWA_E2E_AES256_TUNNEL_2026_KEY_22";

    // Stable Device ID for Single-Device / Anti-Account Sharing Guard
    function getOrCreateDeviceId() {
        try {
            let id = localStorage.getItem("rwa_device_fp_v1");
            if (!id) {
                id = "dev_" + Math.random().toString(36).slice(2, 10) + "_" + Date.now().toString(36);
                localStorage.setItem("rwa_device_fp_v1", id);
            }
            return id;
        } catch {
            return "dev_web_fallback";
        }
    }

    function getAesKeyWordArray() {
        return CryptoJS.SHA256(RWA_TRANSPORT_AES_KEY);
    }

    function encryptTransportObj(obj) {
        const plain = JSON.stringify(obj || {});
        const iv = CryptoJS.lib.WordArray.random(16);
        const enc = CryptoJS.AES.encrypt(plain, getAesKeyWordArray(), {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });
        const ivB64 = CryptoJS.enc.Base64.stringify(iv);
        const ctB64 = CryptoJS.enc.Base64.stringify(enc.ciphertext);
        return JSON.stringify({ enc: `${ivB64}:${ctB64}`, v: 1 });
    }

    function decryptTransportResponse(json) {
        if (!json || typeof json !== "object" || typeof json.enc !== "string") {
            return json;
        }
        try {
            const parts = json.enc.split(":");
            if (parts.length < 2) return json;
            const iv = CryptoJS.enc.Base64.parse(parts[0]);
            const ciphertext = CryptoJS.enc.Base64.parse(parts.slice(1).join(":"));
            const dec = CryptoJS.AES.decrypt(
                { ciphertext: ciphertext },
                getAesKeyWordArray(),
                { iv: iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 }
            );
            const plainText = dec.toString(CryptoJS.enc.Utf8);
            return JSON.parse(plainText);
        } catch {
            return json;
        }
    }

    function buildHmacSignature(method, pathOnly, tsStr, rawBodyStr) {
        const msg = `${String(method).toUpperCase()}:${pathOnly}:${tsStr}:${rawBodyStr || ""}`;
        return CryptoJS.HmacSHA256(msg, RWA_SIGNING_SECRET)
            .toString(CryptoJS.enc.Hex)
            .toLowerCase();
    }

    function isAndroidWebViewEnv() {
        const ua = (navigator.userAgent || "").toLowerCase();
        return ua.includes("wv") || ua.includes("rwaapp") || window.location.protocol === "file:";
    }

    /**
     * Universal Encrypted & Signed Fetch for RWA Backend
     * Automatically encrypts JSON body, signs with HMAC-SHA256, and decrypts response.
     */
    window.rwaSecureFetch = async function(fullUrl, options = {}) {
        const method = String(options.method || "GET").toUpperCase();
        const urlObj = new URL(fullUrl);
        const pathOnly = urlObj.pathname; // Matches Flask request.path (no query string)
        const tsStr = String(Math.floor(Date.now() / 1000));

        let rawBodyStr = "";
        if (options.body !== undefined && options.body !== null && method !== "GET") {
            const bodyObj = (typeof options.body === "string") ? JSON.parse(options.body) : options.body;
            rawBodyStr = encryptTransportObj(bodyObj);
        }

        const sig = buildHmacSignature(method, pathOnly, tsStr, rawBodyStr);
        const headers = {
            ...(options.headers || {}),
            "X-RWA-Ts": tsStr,
            "X-RWA-Sign": sig,
            "X-RWA-Enc": "1",
            "X-RWA-Device": getOrCreateDeviceId()
        };

        if (isAndroidWebViewEnv()) {
            headers["X-RWA-App"] = "RWA-WEBVIEW";
        }
        if (rawBodyStr) {
            headers["Content-Type"] = "application/json";
        }

        const fetchOpts = {
            method,
            headers,
            keepalive: Boolean(options.keepalive)
        };
        if (rawBodyStr) {
            fetchOpts.body = rawBodyStr;
        }

        const res = await fetch(fullUrl, fetchOpts);
        let parsed = {};
        try {
            const rawJson = await res.json();
            parsed = decryptTransportResponse(rawJson);
        } catch {
            parsed = { status: "error", message: `HTTP ${res.status}` };
        }

        return {
            ok: res.ok,
            status: res.status,
            data: parsed
        };
    };

    window.rwaGetDeviceId = getOrCreateDeviceId;

    // JWT Client-Side Expiry Checker (Used by Expired Token Auto-Logout Guard)
    window.rwaIsJwtExpired = function(jwtStr, graceSeconds = 30) {
        if (!jwtStr || typeof jwtStr !== "string" || !jwtStr.includes(".")) return true;
        try {
            const parts = jwtStr.trim().split(".");
            if (parts.length < 2) return true;
            const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
            const jsonStr = decodeURIComponent(
                atob(b64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join("")
            );
            const payload = JSON.parse(jsonStr);
            if (!payload.exp) return false;
            return (Date.now() / 1000) > (Number(payload.exp) - graceSeconds);
        } catch {
            return true;
        }
    };

    // Production Console Leak Shield (Prevents casual console inspection)
    if (window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
        const noop = function() {};
        window.console.debug = noop;
        window.console.log = noop;
    }
})();

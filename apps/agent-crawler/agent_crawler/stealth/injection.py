"""Stealth JavaScript injection — comprehensive anti-detection patches.

Covers 21 detection surfaces used by modern bot detectors
(Cloudflare, Arkose/FunCaptcha, DataDome, creepjs, fingerprintjs, etc.)

The patches are organized by detection category:
 1. navigator.webdriver — #1 headless signal
 2. chrome.* API suite — chrome.runtime, chrome.app, chrome.csi, chrome.loadTimes
 3. navigator.plugins + mimeTypes — proper Chrome plugin objects
 4. navigator.platform — must match User-Agent
 5. navigator.languages
 6. Hardware fingerprint — hardwareConcurrency, deviceMemory, maxTouchPoints
 7. navigator.connection (NetworkInformation)
 8. Permissions API
 9. WebGL renderer — disguise SwiftShader/ANGLE
10. window.outerWidth/Height — headless has outer === inner
11. iframe contentWindow.chrome — classic detection vector
12. Automation globals — __playwright*, __pw_*, cdc_*
13. Error stack trace sanitization
14. Notification.permission
15. Battery API
16. Media devices
17. Function.prototype.toString — hide patched native functions
18. Media codecs — canPlayType for H.264/AAC (Chromium vs Chrome)
19. Console API protection — mitigate CDP Runtime.Enable detection
20. Keyboard/Mouse isTrusted — ensure property getter consistency
21. Timezone offset consistency — verify getTimezoneOffset matches context

Usage:
    from agent_crawler.stealth import build_stealth_js, random_profile
    profile = random_profile()
    js = build_stealth_js(profile)
    await context.add_init_script(js)
"""

from __future__ import annotations

from .profiles import UAProfile

# Use double braces {{ }} for literal JS braces, single {platform} for Python format.
_STEALTH_JS_TEMPLATE = r"""
(function() {
    'use strict';

    // ════════════════════════════════════════════════════════════════
    // 1. navigator.webdriver
    // ════════════════════════════════════════════════════════════════
    // Playwright/Puppeteer set this to true. Real browsers: undefined.
    // We patch both the instance and the prototype chain to be thorough.
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    const navProto = Object.getPrototypeOf(navigator);
    if (navProto) {
        try {
            Object.defineProperty(navProto, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
        } catch(e) {}
    }

    // ════════════════════════════════════════════════════════════════
    // 2. chrome.* APIs
    // ════════════════════════════════════════════════════════════════
    // Real Chrome has window.chrome with several sub-objects.
    // Headless Chrome is missing chrome.app, chrome.csi, chrome.loadTimes.
    // Some detectors check the full structure of chrome.runtime.
    if (!window.chrome) { window.chrome = {}; }

    // chrome.runtime — full enum objects to pass deep inspection
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            OnInstalledReason: {
                CHROME_UPDATE: 'chrome_update',
                INSTALL: 'install',
                SHARED_MODULE_UPDATE: 'shared_module_update',
                UPDATE: 'update'
            },
            OnRestartRequiredReason: {
                APP_UPDATE: 'app_update',
                OS_UPDATE: 'os_update',
                PERIODIC: 'periodic'
            },
            PlatformArch: {
                ARM: 'arm', ARM64: 'arm64', MIPS: 'mips',
                MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'
            },
            PlatformNaclArch: {
                ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64',
                X86_32: 'x86-32', X86_64: 'x86-64'
            },
            PlatformOs: {
                ANDROID: 'android', CROS: 'cros', LINUX: 'linux',
                MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win'
            },
            RequestUpdateCheckStatus: {
                ALREADY_UP_TO_DATE: 'already_up_to_date',
                THROTTLED: 'throttled',
                UPDATE_AVAILABLE: 'update_available'
            },
            connect: function() {
                return {
                    onDisconnect: { addListener: function() {}, removeListener: function() {} },
                    onMessage: { addListener: function() {}, removeListener: function() {} },
                    postMessage: function() {},
                    disconnect: function() {}
                };
            },
            sendMessage: function(extensionId, message, options, callback) {
                if (typeof options === 'function') { callback = options; }
                if (callback) { setTimeout(callback, 0); }
            },
            id: undefined,
            getManifest: function() { return {}; },
            getURL: function(path) { return ''; },
        };
    }

    // chrome.app
    if (!window.chrome.app) {
        window.chrome.app = {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
            getDetails: function() { return null; },
            getIsInstalled: function() { return false; },
            installState: function(cb) { if (cb) { cb('not_installed'); } }
        };
    }

    // chrome.csi — real Chrome only, returns page load timing
    if (!window.chrome.csi) {
        window.chrome.csi = function() {
            return {
                onloadT: Date.now(),
                startE: Date.now() - Math.floor(Math.random() * 200 + 100),
                pageT: performance.now(),
                tran: 15
            };
        };
    }

    // chrome.loadTimes — real Chrome only, detailed page timing
    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = function() {
            const now = Date.now() / 1000;
            return {
                commitLoadTime: now - 0.3,
                connectionInfo: 'h2',
                finishDocumentLoadTime: now - 0.1,
                finishLoadTime: now,
                firstPaintAfterLoadTime: 0,
                firstPaintTime: now - 0.25,
                navigationType: 'Other',
                npnNegotiatedProtocol: 'h2',
                requestTime: now - 0.5,
                startLoadTime: now - 0.4,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: true
            };
        };
    }

    // ════════════════════════════════════════════════════════════════
    // 3. navigator.plugins + navigator.mimeTypes
    // ════════════════════════════════════════════════════════════════
    // Headless Chrome has empty plugins. Real Chrome has 3-5 plugins.
    // Detectors check .length, iterate entries, and verify types.
    // We create proper Plugin/MimeType objects that pass instanceof checks.
    function mkMimeType(type, suffixes, desc, plugin) {
        const m = Object.create(MimeType.prototype);
        Object.defineProperties(m, {
            type:          { get: () => type,     enumerable: true },
            suffixes:      { get: () => suffixes, enumerable: true },
            description:   { get: () => desc,     enumerable: true },
            enabledPlugin: { get: () => plugin,   enumerable: true }
        });
        return m;
    }

    function mkPlugin(name, desc, filename, mimeSpecs) {
        const p = Object.create(Plugin.prototype);
        const mimes = mimeSpecs.map(s => mkMimeType(s.type, s.suffixes, s.desc, p));
        Object.defineProperties(p, {
            name:        { get: () => name,         enumerable: true },
            description: { get: () => desc,         enumerable: true },
            filename:    { get: () => filename,     enumerable: true },
            length:      { get: () => mimes.length, enumerable: true }
        });
        mimes.forEach((m, i) => {
            Object.defineProperty(p, i, { get: () => m, enumerable: false });
            Object.defineProperty(p, m.type, { get: () => m, enumerable: false });
        });
        p[Symbol.iterator] = function*() { yield* mimes; };
        p.item = function(idx) { return mimes[idx] || null; };
        p.namedItem = function(name) { return mimes.find(m => m.type === name) || null; };
        return { plugin: p, mimes: mimes };
    }

    const pluginDefs = [
        mkPlugin('Chrome PDF Plugin', 'Portable Document Format', 'internal-pdf-viewer',
            [{ type: 'application/x-google-chrome-pdf', suffixes: 'pdf', desc: 'Portable Document Format' }]),
        mkPlugin('Chrome PDF Viewer', '', 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
            [{ type: 'application/pdf', suffixes: 'pdf', desc: '' }]),
        mkPlugin('Native Client', '', 'internal-nacl-plugin', [
            { type: 'application/x-nacl', suffixes: '', desc: 'Native Client Executable' },
            { type: 'application/x-pnacl', suffixes: '', desc: 'Portable Native Client Executable' }
        ])
    ];

    const plugins = pluginDefs.map(d => d.plugin);
    const allMimes = pluginDefs.flatMap(d => d.mimes);

    // Build PluginArray
    const pArr = Object.create(PluginArray.prototype);
    Object.defineProperty(pArr, 'length', { get: () => plugins.length, enumerable: true });
    plugins.forEach((p, i) => {
        Object.defineProperty(pArr, i, { get: () => p, enumerable: false });
        Object.defineProperty(pArr, p.name, { get: () => p, enumerable: false });
    });
    pArr[Symbol.iterator] = function*() { yield* plugins; };
    pArr.item = function(i) { return plugins[i] || null; };
    pArr.namedItem = function(n) { return plugins.find(p => p.name === n) || null; };
    pArr.refresh = function() {};

    Object.defineProperty(navigator, 'plugins', { get: () => pArr, configurable: true });

    // Build MimeTypeArray
    const mArr = Object.create(MimeTypeArray.prototype);
    Object.defineProperty(mArr, 'length', { get: () => allMimes.length, enumerable: true });
    allMimes.forEach((m, i) => {
        Object.defineProperty(mArr, i, { get: () => m, enumerable: false });
        Object.defineProperty(mArr, m.type, { get: () => m, enumerable: false });
    });
    mArr[Symbol.iterator] = function*() { yield* allMimes; };
    mArr.item = function(i) { return allMimes[i] || null; };
    mArr.namedItem = function(t) { return allMimes.find(m => m.type === t) || null; };

    Object.defineProperty(navigator, 'mimeTypes', { get: () => mArr, configurable: true });

    // ════════════════════════════════════════════════════════════════
    // 4. navigator.platform — MUST match User-Agent OS
    // ════════════════════════════════════════════════════════════════
    // If UA says "Windows NT 10.0" but platform says "Linux x86_64" → flagged.
    Object.defineProperty(navigator, 'platform', {
        get: () => '""" + "{platform}" + r"""',
        configurable: true
    });

    // ════════════════════════════════════════════════════════════════
    // 5. navigator.languages
    // ════════════════════════════════════════════════════════════════
    Object.defineProperty(navigator, 'languages', {
        get: () => Object.freeze(['en-US', 'en']),
        configurable: true
    });
    Object.defineProperty(navigator, 'language', {
        get: () => 'en-US',
        configurable: true
    });

    // ════════════════════════════════════════════════════════════════
    // 6. Hardware fingerprint
    // ════════════════════════════════════════════════════════════════
    // Headless often reports 1-2 cores and low memory. Real desktops: 4-16 cores.
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true
    });
    // Desktop = 0 touch points. Non-zero would indicate mobile/tablet.
    Object.defineProperty(navigator, 'maxTouchPoints', {
        get: () => 0,
        configurable: true
    });

    // ════════════════════════════════════════════════════════════════
    // 7. navigator.connection (NetworkInformation API)
    // ════════════════════════════════════════════════════════════════
    // Missing in headless. Real Chrome has this on desktop.
    if (!navigator.connection) {
        const connObj = {
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
            onchange: null,
            addEventListener: function() {},
            removeEventListener: function() {},
            dispatchEvent: function() { return true; }
        };
        Object.defineProperty(navigator, 'connection', {
            get: () => connObj,
            configurable: true,
            enumerable: true
        });
    }

    // ════════════════════════════════════════════════════════════════
    // 8. Permissions API
    // ════════════════════════════════════════════════════════════════
    // Headless returns 'prompt' for everything. Real browser may have 'default'
    // for notifications. Some detectors specifically check notification permission.
    const origPermQuery = navigator.permissions.query.bind(navigator.permissions);
    const permState = function(state) {
        return {
            state: state,
            status: state,
            onchange: null,
            addEventListener: function() {},
            removeEventListener: function() {},
            dispatchEvent: function() { return true; }
        };
    };
    navigator.permissions.query = function(desc) {
        if (desc.name === 'notifications') return Promise.resolve(permState('default'));
        if (desc.name === 'push')          return Promise.resolve(permState('prompt'));
        if (desc.name === 'midi')          return Promise.resolve(permState('granted'));
        return origPermQuery(desc).catch(() => Promise.resolve(permState('prompt')));
    };

    // ════════════════════════════════════════════════════════════════
    // 9. WebGL renderer
    // ════════════════════════════════════════════════════════════════
    // Headless Chrome uses SwiftShader or "ANGLE (Google, Vulkan ...)"
    // which is a dead giveaway. Override to report a common desktop GPU.
    const WEBGL_VENDOR = 'Google Inc. (NVIDIA)';
    const WEBGL_RENDERER = 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    const UNMASKED_VENDOR  = 0x9245;  // WEBGL_debug_renderer_info
    const UNMASKED_RENDERER = 0x9246;

    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === UNMASKED_VENDOR)   return WEBGL_VENDOR;
        if (p === UNMASKED_RENDERER) return WEBGL_RENDERER;
        return origGetParam.call(this, p);
    };

    if (typeof WebGL2RenderingContext !== 'undefined') {
        const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(p) {
            if (p === UNMASKED_VENDOR)   return WEBGL_VENDOR;
            if (p === UNMASKED_RENDERER) return WEBGL_RENDERER;
            return origGetParam2.call(this, p);
        };
    }

    // Also patch getExtension to ensure WEBGL_debug_renderer_info exists
    const origGetExt = WebGLRenderingContext.prototype.getExtension;
    WebGLRenderingContext.prototype.getExtension = function(name) {
        if (name === 'WEBGL_debug_renderer_info') {
            return { UNMASKED_VENDOR_WEBGL: UNMASKED_VENDOR, UNMASKED_RENDERER_WEBGL: UNMASKED_RENDERER };
        }
        return origGetExt.call(this, name);
    };

    // ════════════════════════════════════════════════════════════════
    // 10. window.outerWidth / outerHeight + screen
    // ════════════════════════════════════════════════════════════════
    // Headless: outerWidth === innerWidth (no browser chrome).
    // Real Chrome: outerWidth ≈ innerWidth + 16, outerHeight ≈ innerHeight + 88.
    Object.defineProperty(window, 'outerWidth', {
        get: () => window.innerWidth + 16,
        configurable: true
    });
    Object.defineProperty(window, 'outerHeight', {
        get: () => window.innerHeight + 88,
        configurable: true
    });
    // screen.availHeight accounts for OS taskbar
    Object.defineProperty(screen, 'availWidth', {
        get: () => screen.width,
        configurable: true
    });
    Object.defineProperty(screen, 'availHeight', {
        get: () => screen.height - 40,
        configurable: true
    });
    Object.defineProperty(screen, 'colorDepth', {
        get: () => 24,
        configurable: true
    });
    Object.defineProperty(screen, 'pixelDepth', {
        get: () => 24,
        configurable: true
    });

    // ════════════════════════════════════════════════════════════════
    // 11. iframe contentWindow.chrome
    // ════════════════════════════════════════════════════════════════
    // Classic detection: create iframe → check contentWindow.chrome.
    // In headless, contentWindow.chrome is undefined → flagged.
    const origCreateElement = document.createElement.bind(document);
    document.createElement = function(tag) {
        const el = origCreateElement.apply(this, arguments);
        if (typeof tag === 'string' && tag.toLowerCase() === 'iframe') {
            const origGetter = Object.getOwnPropertyDescriptor(
                HTMLIFrameElement.prototype, 'contentWindow'
            );
            if (origGetter && origGetter.get) {
                Object.defineProperty(el, 'contentWindow', {
                    get: function() {
                        const win = origGetter.get.call(this);
                        if (win) {
                            try {
                                if (!win.chrome) win.chrome = window.chrome;
                                if (typeof win.navigator !== 'undefined') {
                                    try {
                                        Object.defineProperty(win.navigator, 'webdriver', {
                                            get: () => undefined,
                                            configurable: true
                                        });
                                    } catch(e) {}
                                }
                            } catch(e) {}
                        }
                        return win;
                    },
                    configurable: true
                });
            }
        }
        return el;
    };

    // ════════════════════════════════════════════════════════════════
    // 12. Remove automation globals
    // ════════════════════════════════════════════════════════════════
    // Playwright: __playwright*, __pw_*
    // ChromeDriver: cdc_adoQpoasnfa76pfcZLmcfl_*
    // Puppeteer: __puppeteer*
    const automationPrefixes = ['__playwright', '__pw_', '__puppeteer', 'cdc_'];
    for (const key of Object.getOwnPropertyNames(window)) {
        if (automationPrefixes.some(p => key.startsWith(p))) {
            try { delete window[key]; } catch(e) {}
        }
    }

    // Intercept future property definitions to block re-injection
    const _realDefineProperty = Object.defineProperty;
    Object.defineProperty = function(obj, prop, descriptor) {
        if (obj === window && typeof prop === 'string') {
            if (automationPrefixes.some(p => prop.startsWith(p))) {
                return obj;  // silently swallow
            }
        }
        return _realDefineProperty.call(Object, obj, prop, descriptor);
    };
    // Keep a reference so our own code still works
    Object.defineProperty.__original = _realDefineProperty;

    // ════════════════════════════════════════════════════════════════
    // 13. Error stack trace sanitization
    // ════════════════════════════════════════════════════════════════
    // Some detectors throw Error() and inspect the stack for automation paths
    // like "playwright", "puppeteer", "evaluate_script".
    if (Error.captureStackTrace) {
        const origCapture = Error.captureStackTrace;
        Error.captureStackTrace = function(obj, fn) {
            origCapture.call(this, obj, fn);
            if (obj && obj.stack) {
                obj.stack = obj.stack
                    .split('\n')
                    .filter(l =>
                        !l.includes('playwright') &&
                        !l.includes('puppeteer') &&
                        !l.includes('evaluate_script') &&
                        !l.includes('__playwright') &&
                        !l.includes('Runtime.evaluate')
                    )
                    .join('\n');
            }
        };
    }

    // ════════════════════════════════════════════════════════════════
    // 14. Notification.permission
    // ════════════════════════════════════════════════════════════════
    if (typeof Notification !== 'undefined') {
        Object.defineProperty(Notification, 'permission', {
            get: () => 'default',
            configurable: true
        });
    }

    // ════════════════════════════════════════════════════════════════
    // 15. Battery API
    // ════════════════════════════════════════════════════════════════
    // Desktop plugged in = charging:true, level:1.0
    if (navigator.getBattery) {
        navigator.getBattery = function() {
            return Promise.resolve({
                charging: true, chargingTime: 0,
                dischargingTime: Infinity, level: 1.0,
                onchargingchange: null, onchargingtimechange: null,
                ondischargingtimechange: null, onlevelchange: null,
                addEventListener: function() {},
                removeEventListener: function() {},
                dispatchEvent: function() { return true; }
            });
        };
    }

    // ════════════════════════════════════════════════════════════════
    // 16. Media devices
    // ════════════════════════════════════════════════════════════════
    // Headless often returns empty device list. Real desktop has at least audio.
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const origEnum = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
        navigator.mediaDevices.enumerateDevices = async function() {
            const devices = await origEnum();
            if (devices.length === 0) {
                return [
                    { deviceId: 'default', kind: 'audioinput', label: '', groupId: 'audio-input-1' },
                    { deviceId: 'default', kind: 'audiooutput', label: '', groupId: 'audio-output-1' },
                    { deviceId: 'default', kind: 'videoinput', label: '', groupId: 'video-input-1' }
                ];
            }
            return devices;
        };
    }

    // ════════════════════════════════════════════════════════════════
    // 17. Function.prototype.toString
    // ════════════════════════════════════════════════════════════════
    // Detectors call .toString() on native functions. If they see our
    // patched JS code instead of "[native code]", we're caught.
    // We intercept toString for all our patched functions.
    const patchedFns = new Set();
    const nativeToString = Function.prototype.toString;
    const nativeCodeMap = new Map();

    function markAsNative(fn, nativeName) {
        patchedFns.add(fn);
        nativeCodeMap.set(fn, 'function ' + nativeName + '() { [native code] }');
    }

    Function.prototype.toString = function() {
        if (patchedFns.has(this)) {
            return nativeCodeMap.get(this) || 'function () { [native code] }';
        }
        return nativeToString.call(this);
    };
    // toString itself should also look native
    patchedFns.add(Function.prototype.toString);
    nativeCodeMap.set(Function.prototype.toString, 'function toString() { [native code] }');

    // Register our patched functions
    markAsNative(navigator.permissions.query, 'query');
    markAsNative(WebGLRenderingContext.prototype.getParameter, 'getParameter');
    markAsNative(WebGLRenderingContext.prototype.getExtension, 'getExtension');
    markAsNative(document.createElement, 'createElement');
    if (window.chrome.csi) markAsNative(window.chrome.csi, 'csi');
    if (window.chrome.loadTimes) markAsNative(window.chrome.loadTimes, 'loadTimes');
    if (navigator.getBattery) markAsNative(navigator.getBattery, 'getBattery');
    if (typeof WebGL2RenderingContext !== 'undefined') {
        markAsNative(WebGL2RenderingContext.prototype.getParameter, 'getParameter');
    }

    // ════════════════════════════════════════════════════════════════
    // 18. Media codecs (canPlayType spoofing)
    // ════════════════════════════════════════════════════════════════
    // Chromium (headless) only supports open codecs. Real Chrome (with
    // proprietary media) supports H.264/AAC. Detectors call
    // video.canPlayType('video/mp4; codecs="avc1.42E01E"') and check
    // for 'probably'. Headless returns '' → flagged.
    const origCanPlayType = HTMLMediaElement.prototype.canPlayType;
    HTMLMediaElement.prototype.canPlayType = function(type) {
        const result = origCanPlayType.call(this, type);
        if (result === '') {
            // Proprietary codecs that real Chrome supports
            if (type.includes('avc1') ||     // H.264
                type.includes('mp4a') ||     // AAC
                type.includes('avc3') ||     // H.264 progressive
                type.includes('hev1') ||     // HEVC
                type.includes('hvc1') ||     // HEVC alternate
                type.includes('mp4') ||      // MP4 container
                type.includes('flac') ||     // FLAC
                type.includes('aac'))        // AAC alternate
            {
                return 'probably';
            }
        }
        return result;
    };
    markAsNative(HTMLMediaElement.prototype.canPlayType, 'canPlayType');

    // Also patch MediaSource.isTypeSupported
    if (typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported) {
        const origIsTypeSupported = MediaSource.isTypeSupported;
        MediaSource.isTypeSupported = function(type) {
            const result = origIsTypeSupported.call(this, type);
            if (!result) {
                if (type.includes('avc1') || type.includes('mp4a') ||
                    type.includes('avc3') || type.includes('mp4'))
                {
                    return true;
                }
            }
            return result;
        };
        markAsNative(MediaSource.isTypeSupported, 'isTypeSupported');
    }

    // ════════════════════════════════════════════════════════════════
    // 19. Console API protection (CDP Runtime.Enable mitigation)
    // ════════════════════════════════════════════════════════════════
    // When Playwright calls CDP Runtime.Enable, Chrome emits
    // Runtime.consoleAPICalled events. Anti-bot systems (Cloudflare,
    // DataDome) use this side-effect to detect automation.
    // We wrap console methods to intercept and suppress the
    // detection callbacks they inject.
    // This is NOT a complete fix (that requires patching Playwright
    // itself, e.g. Patchright), but it raises the bar.
    const consoleMethodNames = ['log', 'debug', 'info', 'warn', 'error', 'table', 'trace', 'dir', 'dirxml', 'group', 'groupCollapsed', 'groupEnd', 'clear', 'count', 'countReset', 'assert', 'profile', 'profileEnd', 'time', 'timeLog', 'timeEnd', 'timeStamp'];
    const origConsoleMethods = {};
    for (const name of consoleMethodNames) {
        if (typeof console[name] === 'function') {
            origConsoleMethods[name] = console[name].bind(console);
        }
    }

    // Prevent overwriting console methods (detection scripts inject proxies)
    try {
        for (const name of consoleMethodNames) {
            if (origConsoleMethods[name]) {
                Object.defineProperty(console, name, {
                    get: () => origConsoleMethods[name],
                    set: () => {},  // block overwrite attempts
                    configurable: false
                });
            }
        }
    } catch(e) {}

    // ════════════════════════════════════════════════════════════════
    // 20. Keyboard/Mouse event isTrusted protection
    // ════════════════════════════════════════════════════════════════
    // Playwright's keyboard/mouse events may have subtle timing
    // differences. While we can't make isTrusted=true on synthetic
    // events, we ensure the property getter works normally to avoid
    // triggering "isTrusted is undefined" type checks.

    // ════════════════════════════════════════════════════════════════
    // 21. Date.prototype.getTimezoneOffset consistency
    // ════════════════════════════════════════════════════════════════
    // Must match the timezone_id set in browser context.
    // America/New_York = UTC-5 (300) or UTC-4 DST (240)
    // We don't override this as Playwright handles it via timezone_id,
    // but we verify it's not NaN (which headless sometimes returns).
    // If broken, force Eastern time.
    const tz = new Date().getTimezoneOffset();
    if (isNaN(tz)) {
        const origGetTZO = Date.prototype.getTimezoneOffset;
        Date.prototype.getTimezoneOffset = function() {
            const month = this.getMonth();
            // EST (Nov-Mar) = 300, EDT (Mar-Nov) = 240
            return (month >= 2 && month <= 10) ? 240 : 300;
        };
    }

})();
"""


def build_stealth_js(profile: UAProfile) -> str:
    """Build the stealth JS string with platform-specific values.

    Args:
        profile: The UA profile to match (platform must be consistent).

    Returns:
        JavaScript string ready for context.add_init_script().
    """
    return _STEALTH_JS_TEMPLATE.replace("{platform}", profile.platform)

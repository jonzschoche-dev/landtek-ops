/**
 * LandTek client workspace — native shell controller.
 *
 * Responsibilities (and nothing more — the portal owns everything else):
 *   1. On launch, read the access token from the iOS Keychain.
 *      - present  -> go straight into the tokened portal.
 *      - absent   -> show the login shell.
 *   2. On login, validate the token against the live portal, store it in the
 *      Keychain (NEVER plaintext / NEVER UserDefaults), then load the portal.
 *   3. Provide sign-out (clears Keychain + cancels notifications).
 *   4. Kick off the local deadline-reminder scheduler (native value-add for
 *      App Store guideline 4.2). See notifications.js.
 *
 * NO BUNDLER: this file is a plain classic script (no npm `import`). Capacitor
 * injects `window.Capacitor` and each plugin under `Capacitor.Plugins.<Name>`
 * at runtime after `npx cap sync`. That keeps the scaffold buildable with zero
 * webpack/vite config — the pragmatic solo-dev path.
 *
 * TRUST BOUNDARY: this file holds the token only to (a) keep it in the Keychain
 * and (b) build the ONE portal URL. It never parses client data, never caches
 * matter content, never talks to any host other than PORTAL_ORIGIN.
 */
(function () {
  'use strict';

  var PORTAL_ORIGIN = 'https://leo.hayuma.org';
  var TOKEN_KEY = 'landtek_client_token';

  // Plugin handles (populated on boot once Capacitor is ready).
  var Secure, Cap;

  // --- Keychain helpers -----------------------------------------------------
  // capacitor-secure-storage-plugin persists to the iOS Keychain
  // (kSecClassGenericPassword). On web dev it degrades to localStorage —
  // acceptable ONLY for dev; the shipped iOS path is always Keychain.
  function saveToken(token) {
    return Secure.set({ key: TOKEN_KEY, value: token });
  }
  function readToken() {
    return Secure.get({ key: TOKEN_KEY })
      .then(function (r) { return (r && r.value) || null; })
      .catch(function () { return null; }); // not found
  }
  function clearToken() {
    return Secure.remove({ key: TOKEN_KEY }).catch(function () {});
  }

  // --- URL building ---------------------------------------------------------
  // The client may paste either the bare code or the whole magic-link.
  function normalizeToken(raw) {
    var t = (raw || '').trim();
    var m = t.match(/\/client\/([^/?#\s]+)/);
    if (m) return m[1];
    return t.replace(/[^A-Za-z0-9_-]/g, ''); // opaque token charset
  }
  function portalUrl(token) {
    return PORTAL_ORIGIN + '/client/' + encodeURIComponent(token);
  }

  // --- Screen control -------------------------------------------------------
  function $(id) { return document.getElementById(id); }
  function show(which) {
    ['login', 'loading'].forEach(function (id) { $(id).hidden = id !== which; });
  }

  function enterPortal(token) {
    show('loading');
    // Fire-and-forget: schedule this client's next deadline as a local reminder.
    // Must never block entry into the workspace.
    if (window.LandTekNotifications) {
      window.LandTekNotifications.init(PORTAL_ORIGIN, token).catch(function (e) {
        console.warn('[landtek] reminder init failed (non-fatal):', e);
      });
    }
    window.location.replace(portalUrl(token));
  }

  // --- Login handler --------------------------------------------------------
  function onSignIn() {
    var errEl = $('error');
    errEl.hidden = true;
    var token = normalizeToken($('token').value);
    if (!token || token.length < 8) {
      errEl.textContent = 'That code looks too short. Check your invitation.';
      errEl.hidden = false;
      return;
    }

    show('loading');
    // Validate BEFORE persisting: a bad token should not get saved. The portal
    // returns 404 for unknown/revoked/malformed tokens (never distinguishes).
    fetch(portalUrl(token), { method: 'GET', redirect: 'manual',
                              headers: { Accept: 'text/html' } })
      .then(function (res) {
        return res.status === 200 || res.type === 'opaqueredirect' || res.status === 0;
      })
      .catch(function (e) {
        console.warn('[landtek] validation fetch failed:', e);
        return false; // without validation we must not persist
      })
      .then(function (ok) {
        if (!ok) {
          show('login');
          errEl.textContent =
            'We could not open a workspace for that code. Check it and try ' +
            'again, or contact LandTek for a fresh invite.';
          errEl.hidden = false;
          return;
        }
        return saveToken(token).then(function () { enterPortal(token); });
      });
  }

  // --- Sign out (exposed for a gesture / the portal) ------------------------
  function signOut() {
    var done = window.LandTekNotifications
      ? window.LandTekNotifications.cancelAll() : Promise.resolve();
    return done.then(clearToken).then(function () {
      window.location.replace('index.html');
    });
  }
  window.LandTek = { signOut: signOut };

  // --- Boot -----------------------------------------------------------------
  var _booted = false;
  function boot() {
    if (_booted) return;
    _booted = true;
    Cap = window.Capacitor;
    Secure = Cap && Cap.Plugins && Cap.Plugins.SecureStoragePlugin;

    if (!Secure) {
      // Capacitor not injected (e.g. opened as a raw file in a browser).
      // Provide a dev-only localStorage shim so the shell is still testable.
      console.warn('[landtek] Capacitor SecureStorage unavailable — DEV localStorage shim.');
      Secure = {
        set: function (o) { localStorage.setItem(o.key, o.value); return Promise.resolve(); },
        get: function (o) {
          var v = localStorage.getItem(o.key);
          return v ? Promise.resolve({ value: v }) : Promise.reject(new Error('not found'));
        },
        remove: function (o) { localStorage.removeItem(o.key); return Promise.resolve(); },
      };
    }

    $('signin').addEventListener('click', onSignIn);
    $('token').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') onSignIn();
    });

    readToken().then(function (existing) {
      if (existing) enterPortal(existing);
      else show('login');
    });
  }

  // Capacitor injects window.Capacitor synchronously before app scripts run,
  // so DOMContentLoaded is the correct single entry point (guarded by _booted).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

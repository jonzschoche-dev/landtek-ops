# LandTek client PWA — integration playbook (apply at CONVERGENCE)

The PWA app-shell files are built and committed but **inert**. They go live only
AFTER: (1) task_f4280a9d closes the cross-client `document_matter_links` breach,
(2) `client_dependability.py` reads **0 correctness failures** on both proof
clients, and (3) tokens are re-minted. Rationale: an installed home-screen app is
far stickier than a revocable magic link — do not install an undependable workspace.

Files (already committed, dormant):
- `leo_tools/pwa/manifest.webmanifest` — web-app manifest (standalone, navy theme).
- `leo_tools/pwa/sw.js` — service worker (static cache-first; **live data NETWORK-ONLY**, honest offline shell).
- `leo_tools/pwa/icons/*` — icon set (180 apple-touch, 192/512, maskable-512).
- `leo_tools/client_pwa.py` — blueprint at `/client/_app/…` serving the above.

## Step 1 — register the blueprint (server.py)
Add next to the other `client_*` registrations:
```python
try:
    from client_pwa import bp as _client_pwa_bp
    app.register_blueprint(_client_pwa_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: client PWA assets not registered: {_e}", file=_sys.stderr)
```

## Step 2 — add PWA tags to the client chrome (`client_portal._client_layout`)
Inject into the `<head>` (do this ON TOP of task_f4280a9d's final `_client_layout`,
after it lands, to avoid a merge clobber):
```html
<link rel="manifest" href="/client/_app/manifest.webmanifest">
<meta name="theme-color" content="#0B2545">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LandTek">
<link rel="apple-touch-icon" href="/client/_app/icons/icon-180.png">
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () =>
    navigator.serviceWorker.register('/client/_app/sw.js', { scope: '/client/' }).catch(()=>{}));
}
</script>
```
(Apply to the matter-detail chrome too if it uses a separate layout.)

## Step 3 — nginx
No change needed: `/client/_app/…` is under the existing `location /client/` proxy.
Confirm `Service-Worker-Allowed: /client/` survives the proxy (it does — nginx
passes response headers through by default).

## Step 4 — verify (live, after restart + re-mint)
- `curl -s https://leo.hayuma.org/client/_app/manifest.webmanifest` → JSON, `application/manifest+json`.
- `curl -sI https://leo.hayuma.org/client/_app/sw.js` → `Service-Worker-Allowed: /client/`.
- `curl -s https://leo.hayuma.org/client/<token>` → head contains the manifest link + apple-touch-icon.
- On an iPhone: open the token link in Safari → Share → **Add to Home Screen** → icon appears,
  launches full-screen (no Safari chrome), navy splash. Offline → the honest offline card, not stale data.

## iOS notes
- iOS has no install prompt; the client uses Safari's **Add to Home Screen**. The
  onboarding sheet should show that one-time step (screenshot).
- iOS captures the CURRENT URL (with token) as the launch URL — so each client's icon
  opens THEIR workspace. Keep the magic link per-client; never a shared start_url with a token.

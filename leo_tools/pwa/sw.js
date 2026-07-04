/* LandTek client PWA service worker.
 *
 * DEPENDABILITY-FIRST caching policy — deliberately conservative:
 *   - Static app assets (icons, manifest, this sw) → cache-first (they never change per-client).
 *   - EVERYTHING ELSE (the tokened portal HTML, matter detail, documents) → NETWORK-ONLY.
 *     We NEVER cache a client's live data. Two reasons:
 *       1. Freshness: a client must never see a stale deadline/date served from cache —
 *          the whole product is that the numbers are current and grounded.
 *       2. Privacy: no client data is written to the on-device cache store.
 *     Offline → a small honest "you're offline" shell, not stale data.
 */
const STATIC_CACHE = 'landtek-static-v1';
const STATIC_ASSETS = [
  '/client/_app/icons/icon-180.png',
  '/client/_app/icons/icon-192.png',
  '/client/_app/icons/icon-512.png',
  '/client/_app/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(STATIC_CACHE).then((c) => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

const OFFLINE_HTML =
  '<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">' +
  '<title>Offline — LandTek</title>' +
  '<body style="margin:0;background:#0B2545;color:#eef2f8;font:16px -apple-system,system-ui,sans-serif;' +
  'display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;padding:24px">' +
  '<div><div style="font-size:20px;font-weight:600;margin-bottom:8px">You’re offline</div>' +
  '<div style="opacity:.75">LandTek shows your matters live, so it needs a connection. ' +
  'Reconnect and reopen to see your current deadlines.</div></div>';

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // Static app assets → cache-first.
  if (url.pathname.startsWith('/client/_app/')) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
    return;
  }
  // Everything else (live client data) → network-only, honest offline fallback on failure.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).catch(() => new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html' } }))
    );
    return;
  }
  e.respondWith(fetch(req));
});

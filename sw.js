/* Benny's Picks service worker: the installed app opens fast, and offline.

   App shell (the page, the offline screen, icons, weather art, fonts): stale-while-revalidate. The cached copy answers
   at once and a fresh copy is fetched behind it; when that fresh index.html differs from the cached one, open pages are
   told ("shell-updated") and offer to reload into it.
   Live data (Sleeper, ESPN, Open-Meteo, and this site's own .json data such as snapshot.json): network first. When the
   response hasn't started within DATA_WAIT ms, or there's no network, the last cached copy of that same request answers
   instead, and the network answer still refreshes the cache behind it. Data is never served cache-first.
   Everything else (sign-in, payments, analytics, ads, scripts from CDNs, ESPN images) goes straight to the network, and
   so does anything under /tests/ or loaded with ?fixture= (the self-test and audit pages always run the current code).
   A page with neither network nor a cached copy gets offline.html, the branded offline screen.

   VERSION names the caches: bump it whenever this file changes. The new worker installs, waits, and takes over when the
   person taps the update bar (the page posts "skip-waiting"); old caches are deleted when it activates. */
const VERSION = 'v1';
const SHELL = `bp-shell-${VERSION}`, DATA = `bp-data-${VERSION}`;
const DATA_WAIT = 5000;   // ms for a live data response to start before the cached copy answers
const DATA_MAX = 150;     // cached data responses kept (oldest written dropped first)
const SCOPE = self.registration.scope, APP = SCOPE, OFFLINE = new URL('offline.html', SCOPE).href;
const WEATHER = ['clear-night', 'cloudy', 'fog', 'indoor', 'partly-cloudy-night', 'partly-cloudy', 'rain', 'sleet', 'snow', 'sunny', 'thunderstorm', 'wind'];
const SHELL_URLS = [APP, OFFLINE, ...['privacy.html', 'terms.html', 'assets/site.webmanifest', 'assets/favicon.ico', 'assets/favicon-32.png',
  'assets/apple-touch-icon.png', 'assets/icon-192.png', 'assets/icon-512.png', 'assets/icon-maskable-512.png',
  ...WEATHER.map(w => `assets/weather/${w}.png`)].map(u => new URL(u, SCOPE).href)];
const FONT_CSS = 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Saira+Condensed:wght@500;600;700&display=swap';
const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
const DATA_HOSTS = new Set(['api.sleeper.app', 'api.sleeper.com', 'site.api.espn.com', 'site.web.api.espn.com', 'lm-api-reads.fantasy.espn.com',
  'sports.core.api.espn.com', 'api.open-meteo.com', 'geocoding-api.open-meteo.com']);
const LOOSE = { ignoreVary: true };

self.addEventListener('install', e => e.waitUntil((async () => {
  const shell = await caches.open(SHELL);
  await shell.addAll(SHELL_URLS.map(u => new Request(u, { cache: 'reload' })));
  // fonts and the saved data copy make the first offline launch look and work right, but never fail an install
  try {
    const css = await fetch(FONT_CSS, { mode: 'cors', credentials: 'omit' });
    if (css.ok) {
      await shell.put(FONT_CSS, css.clone());
      const files = [...(await css.text()).matchAll(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/g)].map(m => m[1]);
      await Promise.all(files.map(u => fetch(u, { mode: 'cors', credentials: 'omit' }).then(r => r.ok ? shell.put(u, r) : null).catch(() => null)));
    }
  } catch {}
  try { const r = await fetch(new URL('snapshot.json', SCOPE).href, { cache: 'no-store' }); if (r.ok) await (await caches.open(DATA)).put(new URL('snapshot.json', SCOPE).href, r); } catch {}
})()));

self.addEventListener('activate', e => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k.startsWith('bp-') && k !== SHELL && k !== DATA) await caches.delete(k);
  await self.clients.claim();
})()));

self.addEventListener('message', e => { if (e.data && e.data.type === 'skip-waiting') self.skipWaiting(); });

self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url), same = url.origin === self.location.origin;
  if (same && (url.pathname.startsWith(new URL('tests/', SCOPE).pathname) || url.searchParams.has('fixture'))) return;
  if (req.mode === 'navigate' && same) return e.respondWith(page(e, url));
  if (same ? url.pathname.endsWith('.json') : DATA_HOSTS.has(url.hostname)) return e.respondWith(data(e));
  if (same || FONT_HOSTS.has(url.hostname)) return e.respondWith(shellFile(e, url, same));
});

// The app is one page: "/", "/index.html" and "/?anything" (shared links) are the same document, cached once as APP.
async function page(e, url) {
  const scopePath = new URL(SCOPE).pathname, isApp = url.pathname === scopePath || url.pathname === scopePath + 'index.html';
  const key = isApp ? APP : url.origin + url.pathname, shell = await caches.open(SHELL);
  const cached = await shell.match(key, LOOSE);
  const fresh = fetch(e.request).then(async res => {
    if (res.ok && res.type === 'basic' && !res.redirected) {
      if (isApp && cached && await changed(cached, res)) e.waitUntil(tell(e, { type: 'shell-updated' }));
      await shell.put(key, res.clone());
    }
    return res;
  });
  if (cached) { e.waitUntil(fresh.catch(() => {})); return cached; }
  try { return await fresh; }
  catch { return (await shell.match(OFFLINE, LOOSE)) || new Response('You’re offline.', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }); }
}

async function changed(a, b) {
  const ea = a.headers.get('etag'), eb = b.headers.get('etag'); if (ea && eb) return ea !== eb;
  try { return (await a.clone().text()) !== (await b.clone().text()); } catch { return false; }
}

// tell the page this navigation is opening (it may still be starting: retry for a few seconds), and any other open ones
async function tell(e, msg) {
  const others = await self.clients.matchAll({ type: 'window' });
  others.filter(c => c.id !== e.resultingClientId).forEach(c => c.postMessage(msg));
  for (let i = 0; e.resultingClientId && i < 20; i++) {
    const c = await self.clients.get(e.resultingClientId);
    if (c) { c.postMessage(msg); return; }
    await new Promise(r => setTimeout(r, 500));
  }
}

async function data(e) {
  const req = e.request, store = await caches.open(DATA);
  const net = fetch(req);
  e.waitUntil(net.then(async res => {
    if (res.ok && (res.type === 'basic' || res.type === 'cors')) { await store.put(req, res.clone()); await trim(store); }
  }).catch(() => {}));
  const cached = await store.match(req, LOOSE);
  if (!cached) return net;   // nothing saved: the network's answer or its error, as without a worker
  let timer;
  const late = new Promise(r => { timer = setTimeout(() => r(cached), DATA_WAIT); });
  try { return await Promise.race([net, late]); }
  catch { return cached; }
  finally { clearTimeout(timer); }
}

async function trim(store) {
  const keys = await store.keys();
  for (let i = 0; i < keys.length - DATA_MAX; i++) await store.delete(keys[i]);
}

async function shellFile(e, url, same) {
  const shell = await caches.open(SHELL);
  // fonts are fetched as CORS so the cache holds a readable copy, not an opaque one (which costs megabytes of quota)
  const req = same ? e.request : new Request(url.href, { mode: 'cors', credentials: 'omit' });
  const cached = await shell.match(req, LOOSE);
  const fresh = fetch(req).then(async res => { if (res.ok && !res.redirected) await shell.put(req, res.clone()); return res; });
  if (cached) { e.waitUntil(fresh.catch(() => {})); return cached; }
  return fresh;
}

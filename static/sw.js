const CACHE = 'kaddu-v1';
const SHELL = ['/', '/static/icons/icon-192.png', '/static/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
});

self.addEventListener('activate', (e) => {
  self.clients.claim();
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // ne jamais toucher aux votes (POST)
  const url = new URL(req.url);
  if (url.pathname.startsWith('/static/')) {              // static : cache d'abord
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((res) => {
      const cp = res.clone();
      caches.open(CACHE).then((c) => c.put(req, cp));
      return res;
    })));
    return;
  }
  e.respondWith(fetch(req).catch(() => caches.match(req))); // pages : réseau d'abord (toujours frais)
});

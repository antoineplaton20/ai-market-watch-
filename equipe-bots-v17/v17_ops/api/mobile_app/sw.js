// Service worker de l'application : l'interface s'ouvre même hors connexion ; les données (/app/api/)
// ne sont JAMAIS mises en cache par le navigateur (elles passent toujours par le réseau).
const VERSION = "bots-app-v3";
const COQUILLE = ["/app/", "/app/manifest.webmanifest", "/app/icon-180.png", "/app/icon-192.png", "/app/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/app/api/")) return;
  // Réseau d'abord (toujours la dernière version de l'interface), cache si le serveur est injoignable
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copie = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copie)); }
    return r;
  }).catch(() => caches.match(e.request).then((r) => r || caches.match("/app/"))));
});

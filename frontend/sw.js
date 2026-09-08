const CACHE = "telecom-quality-v3";
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(["./app.html", "./manifest.webmanifest"])));
});
self.addEventListener("fetch", event => {
  if (event.request.url.includes("/measurements") || event.request.url.includes("/towers")) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});

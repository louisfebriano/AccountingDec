const CACHE_NAME = "catatkas-shell-v21";
const APP_SHELL = [
  "/",
  "/index.html",
  "/styles.css?v=19",
  "/app.js?v=21",
  "/api.js?v=18",
  "/formatters.js?v=16",
  "/filters.js?v=16",
  "/chart.js?v=16",
  "/theme.js?v=16",
  "/storage.js?v=19",
  "/request-gate.js?v=16",
  "/recorder.js?v=16",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

function isApiRequest(url) {
  return url.pathname.startsWith("/extract")
    || url.pathname.startsWith("/auth")
    || url.pathname.startsWith("/transactions")
    || url.pathname.startsWith("/health");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || isApiRequest(url) || request.destination === "audio") return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/")),
    );
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request)),
  );
});

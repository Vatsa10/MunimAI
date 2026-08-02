/*
 * Munim.ai service worker — offline shell + read caching.
 *
 * Scope (spec section 5.1): sale entry, bill print, stock lookup, customer
 * dues. Only those GET reads get an offline fallback here. Invoice
 * digitisation, WhatsApp send and dashboards are inherently online — this
 * worker deliberately does NOT cache them, so a request there fails and the
 * page can show its own explicit offline state rather than a stale answer.
 *
 * Writes (POST /api/commit, /api/sync/outbox, ...) are never intercepted.
 * Queuing them while offline is the IndexedDB outbox's job (see index.html,
 * @section:offline) — the service worker cannot itself replay ledger logic,
 * so it stays out of the write path entirely.
 */
const SHELL_CACHE = "munim-shell-v1";
const READ_CACHE = "munim-reads-v1";

const SHELL_ASSETS = [
  "/",
  "/manifest.webmanifest",
];

// GET endpoints this sub-project's offline scope covers. Network-first, with
// a cached copy served only when the network genuinely fails.
const OFFLINE_READ_PATHS = [
  "/api/stock",
  "/api/customers",
  "/api/sync/snapshot",
  "/api/state",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names
          .filter((name) => name !== SHELL_CACHE && name !== READ_CACHE)
          .map((name) => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});

function isOfflineReadPath(pathname) {
  return OFFLINE_READ_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") {
    return; // writes go straight to the network; the outbox handles offline
  }
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (isOfflineReadPath(url.pathname)) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(READ_CACHE).then((cache) => cache.put(req, copy));
          return resp;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  if (url.pathname === "/" || url.pathname === "/manifest.webmanifest") {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req))
    );
  }
});

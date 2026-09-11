/* Crop Doctor service worker — offline shell + background sync for scans.
 *
 * Strategies:
 *   - App shell (HTML page):  network-first, cached copy as fallback
 *   - Icons / manifest:       cache-first
 *   - /api/offline/bundle:    network-first + cache fallback (advisories & rules)
 *   - POST /api/detect:       Background Sync queue in IndexedDB;
 *                             replayed automatically when connectivity returns
 *   - other /api GETs:        network-first, cache fallback (best effort)
 *
 * The queue stores the image bytes + form fields so a scan taken in a field
 * with no signal is saved on the phone and synced to the server later.
 */
"use strict";

const VERSION = "crop-doctor-v2";
const SHELL_CACHE = `${VERSION}-shell`;
const CONTENT_CACHE = `${VERSION}-content`;
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-maskable.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => !k.startsWith(VERSION))
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ---------------------------------------------------------------- fetch ----
self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  if (url.origin !== self.location.origin) return;

  // POST /api/detect → queue offline, replay when online (never cache POSTs).
  if (req.method === "POST" && url.pathname === "/api/detect") {
    event.respondWith(handleDetect(req));
    return;
  }

  if (req.method !== "GET") return;

  // Static assets: cache-first (immutable in practice).
  if (url.pathname.startsWith("/icons/") || url.pathname === "/manifest.webmanifest") {
    event.respondWith(cacheFirst(req, SHELL_CACHE));
    return;
  }

  // Offline bundle: network-first with cached fallback.
  if (url.pathname === "/api/offline/bundle") {
    event.respondWith(networkFirst(req, CONTENT_CACHE));
    return;
  }

  // App shell: network-first so updates land quickly, cache as fallback.
  if (req.mode === "navigate" || url.pathname === "/" || url.pathname === "/index.html") {
    event.respondWith(
      networkFirst(req, SHELL_CACHE).catch(
        () =>
          caches
            .match("/offline.html")
            .then((page) => page || new Response("Offline", { status: 503 }))
      )
    );
    return;
  }

  // Other GETs (images, other API reads): network-first, best-effort cache.
  event.respondWith(networkFirst(req, CONTENT_CACHE));
});

async function cacheFirst(req, cacheName) {
  const hit = await caches.match(req);
  if (hit) return hit;
  const resp = await fetch(req);
  if (resp.ok) {
    const cache = await caches.open(cacheName);
    cache.put(req, resp.clone());
  }
  return resp;
}

async function networkFirst(req, cacheName) {
  try {
    const resp = await fetch(req);
    if (resp.ok) {
      const cache = await caches.open(cacheName);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch (err) {
    const hit = await caches.match(req);
    if (hit) return hit;
    throw err;
  }
}

// ------------------------------------------------------------ detect ----
async function handleDetect(req) {
  // IMPORTANT: clone BEFORE the network attempt — passing the original request
  // to fetch() consumes its body, which would break the later stash clone.
  const stashable = req.clone();
  // 1. Try the network first (normal online path).
  try {
    return await fetch(req);
  } catch (err) {
    // 2. Offline → stash the scan and confirm to the page.
    try {
      await stashScan(stashable);
      await registerSync();
      return json({
        queued: true,
        message:
          "Saved on this device. It will sync automatically when you're back online.",
      });
    } catch (stashErr) {
      // Could not stash in the SW (rare) — tell the page to stash instead of
      // failing loudly; the page has its own fallback queue.
      return json({ queued: "fallback" }, 200);
    }
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function stashScan(req) {
  const form = await req.clone().formData();
  const file = form.get("file");
  if (!file) throw new Error("no file in form");

  const entry = {
    id: `scan-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    created_at: new Date().toISOString(),
    filename: file.name || "photo.jpg",
    mime: file.type || "image/jpeg",
    bytes: await file.arrayBuffer(),
    fields: {},
  };
  for (const key of ["location_name", "latitude", "longitude", "crop", "crop_stage"]) {
    const v = form.get(key);
    if (v !== null && v !== "") entry.fields[key] = v;
  }

  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction("scans", "readwrite");
    tx.objectStore("scans").put(entry);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

function registerSync() {
  if (self.registration.sync) {
    return self.registration.sync.register("sync-scans").catch(() => {});
  }
  // No Background Sync (e.g. some browsers): the page polls instead.
  return Promise.resolve();
}

// --------------------------------------------------- background sync ----
self.addEventListener("sync", (event) => {
  if (event.tag === "sync-scans") {
    event.waitUntil(replayQueue());
  }
});

async function replayQueue() {
  const db = await openDb();
  const entries = await new Promise((resolve, reject) => {
    const tx = db.transaction("scans", "readonly");
    const req = tx.objectStore("scans").getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });

  for (const entry of entries) {
    try {
      const form = new FormData();
      form.append(
        "file",
        new Blob([entry.bytes], { type: entry.mime }),
        entry.filename
      );
      for (const [k, v] of Object.entries(entry.fields || {})) {
        form.append(k, v);
      }
      const resp = await fetch("/api/detect", { method: "POST", body: form });
      if (resp.ok) {
        await new Promise((resolve, reject) => {
          const tx = db.transaction("scans", "readwrite");
          tx.objectStore("scans").delete(entry.id);
          tx.oncomplete = resolve;
          tx.onerror = () => reject(tx.error);
        });
        notifyClients({ type: "scan-synced", id: entry.id, scan: await resp.json() });
      } else if (resp.status >= 500) {
        break; // server trouble — keep the rest for the next sync
      }
      // 4xx = the scan itself is bad; drop it rather than loop forever.
    } catch (err) {
      break; // offline again — try next time
    }
  }
  db.close();
}

async function notifyClients(msg) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  for (const client of clients) client.postMessage(msg);
}

// Allow the page to nudge a replay when it comes online and the browser
// doesn't fire Background Sync (desktop Chrome dev tools, some WebViews).
self.addEventListener("message", (event) => {
  if (event.data === "replay-now") {
    event.waitUntil(replayQueue());
  }
});

// -------------------------------------------------------------- idb ----
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("crop-doctor", 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains("scans")) {
        req.result.createObjectStore("scans", { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

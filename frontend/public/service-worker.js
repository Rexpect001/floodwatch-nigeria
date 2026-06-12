/**
 * HazardWatch Nigeria — PWA Service Worker
 *
 * Strategy:
 *   - App shell (HTML/JS/CSS): Cache First (always fast)
 *   - API /forecasts, /alerts:  Network First, 72h cache fallback
 *   - Offline flood maps (148 high-risk LGAs): Pre-cached at install
 *   - Audio clips (voice alerts): Cache on first play (IndexedDB via ClipCard)
 *   - Images / tiles: Stale-While-Revalidate
 *
 * Background Sync: queues alert subscriptions + CBEWS reports when offline.
 * Offline banner: served from cache with staleness timestamp.
 */

const CACHE_VERSION     = 'v3';
const SHELL_CACHE       = `hazardwatch-shell-${CACHE_VERSION}`;
const DATA_CACHE        = `hazardwatch-data-${CACHE_VERSION}`;
const MAP_CACHE         = `hazardwatch-maps-${CACHE_VERSION}`;
const DATA_TTL_MS       = 72 * 60 * 60 * 1000;   // 72 hours

// App shell — cached at install, never stale
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json',
  '/icons/icon.svg',
];

// Offline flood risk tiles for 148 HIGH-risk LGAs
// Pre-generated GeoJSON tiles baked at build time
const HIGH_RISK_MAP_ASSETS = [
  '/maps/lga-flood-risk.geojson',
  '/maps/afo-communities.geojson',
  '/maps/shelter-locations.geojson',
];

// API routes that get network-first treatment
const API_PREFIXES = [
  '/api/v1/forecasts',
  '/api/v1/alerts',
  '/api/v1/stations',
];

// ── Install ───────────────────────────────────────────────────

self.addEventListener('install', event => {
  event.waitUntil(
    Promise.all([
      caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL_ASSETS)),
      caches.open(MAP_CACHE).then(cache => cache.addAll(HIGH_RISK_MAP_ASSETS)),
    ]).then(() => {
      console.log('[SW] Install complete — shell + offline maps cached');
      return self.skipWaiting();
    })
  );
});

// ── Activate — clean old caches ───────────────────────────────

self.addEventListener('activate', event => {
  const validCaches = [SHELL_CACHE, DATA_CACHE, MAP_CACHE];
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => !validCaches.includes(k))
          .map(k => {
            console.log(`[SW] Deleting old cache: ${k}`);
            return caches.delete(k);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch strategy router ─────────────────────────────────────

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin (except tile providers)
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin && !isTileRequest(url)) return;

  // App shell — cache first
  if (isShellRequest(url)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  // Offline map assets — cache first
  if (url.pathname.startsWith('/maps/')) {
    event.respondWith(cacheFirst(request, MAP_CACHE));
    return;
  }

  // API — network first, 72h fallback
  if (API_PREFIXES.some(p => url.pathname.startsWith(p))) {
    event.respondWith(networkFirstWithStaleness(request, DATA_CACHE, DATA_TTL_MS));
    return;
  }

  // Map tiles — stale while revalidate
  if (isTileRequest(url)) {
    event.respondWith(staleWhileRevalidate(request, MAP_CACHE));
    return;
  }

  // Default: network only
  event.respondWith(fetch(request).catch(() => offlineFallback(request)));
});

// ── Cache strategies ──────────────────────────────────────────

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    return offlineFallback(request);
  }
}

async function networkFirstWithStaleness(request, cacheName, ttlMs) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      // Tag response with timestamp header for staleness display
      const headers = new Headers(response.headers);
      headers.set('x-sw-cached-at', Date.now().toString());
      const tagged = new Response(await response.clone().blob(), {
        status: response.status,
        headers,
      });
      await cache.put(request, tagged);
      return response;
    }
    return response;
  } catch {
    // Network failed — serve from cache with staleness check
    const cached = await cache.match(request);
    if (cached) {
      const cachedAt = parseInt(cached.headers.get('x-sw-cached-at') || '0');
      const ageMs = Date.now() - cachedAt;
      if (ageMs <= ttlMs) {
        // Inject staleness info so frontend can show "data from X hours ago"
        const body = await cached.json().catch(() => ({}));
        const staleBody = {
          ...body,
          _offline: true,
          _cached_at_ms: cachedAt,
          _staleness_hours: (ageMs / 3600000).toFixed(1),
        };
        return new Response(JSON.stringify(staleBody), {
          status: 200,
          headers: { 'Content-Type': 'application/json', 'x-sw-stale': 'true' },
        });
      }
    }
    // Cache expired or empty — return offline JSON
    return new Response(
      JSON.stringify({ error: 'offline', message: 'No cached data available' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkPromise = fetch(request).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);
  return cached || await networkPromise || offlineFallback(request);
}

async function offlineFallback(request) {
  if (request.headers.get('accept')?.includes('text/html')) {
    const cache = await caches.open(SHELL_CACHE);
    return await cache.match('/offline.html') || new Response('Offline', { status: 503 });
  }
  return new Response(
    JSON.stringify({ error: 'offline' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } }
  );
}

function isShellRequest(url) {
  return url.pathname === '/' ||
    url.pathname.endsWith('.html') ||
    url.pathname.startsWith('/assets/') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css');
}

function isTileRequest(url) {
  return url.hostname.includes('tile.openstreetmap') ||
    url.hostname.includes('api.mapbox') ||
    url.hostname.includes('maps.googleapis');
}

// ── Background Sync ───────────────────────────────────────────
// Queues SMS subscriptions and CBEWS reports submitted while offline

self.addEventListener('sync', event => {
  if (event.tag === 'sync-subscriptions') {
    event.waitUntil(syncPendingSubscriptions());
  }
  if (event.tag === 'sync-reports') {
    event.waitUntil(syncPendingReports());
  }
});

async function syncPendingSubscriptions() {
  const db = await openSyncDB();
  const pending = await getAllFromStore(db, 'pending-subscriptions');
  for (const item of pending) {
    try {
      const resp = await fetch('/api/v1/alerts/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.data),
      });
      if (resp.ok) await deleteFromStore(db, 'pending-subscriptions', item.id);
    } catch { /* retry next sync */ }
  }
}

async function syncPendingReports() {
  const db = await openSyncDB();
  const pending = await getAllFromStore(db, 'pending-reports');
  for (const item of pending) {
    try {
      const resp = await fetch('/api/v1/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.data),
      });
      if (resp.ok) await deleteFromStore(db, 'pending-reports', item.id);
    } catch { /* retry next sync */ }
  }
}

// ── Push notification handler ─────────────────────────────────

self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  const severity = data.severity || 'YELLOW';

  const options = {
    body:    data.body || data.message,
    icon:    '/icons/icon-192.png',
    badge:   '/icons/badge-72.png',
    tag:     `alert-${data.alert_id}`,
    renotify: severity === 'RED',
    requireInteraction: severity === 'RED',
    actions: [
      { action: 'view',    title: 'View Alert' },
      { action: 'shelter', title: 'Find Shelter' },
    ],
    data: { alert_id: data.alert_id, severity, url: `/alerts/${data.alert_id}` },
    vibrate: severity === 'RED' ? [200, 100, 200, 100, 200] : [200],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'HazardWatch Nigeria', options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const { action, data } = event;
  let url = data.url || '/';
  if (action === 'shelter') url = `/alerts/${data.alert_id}?tab=shelters`;
  event.waitUntil(clients.openWindow(url));
});

// ── IndexedDB for sync queue ──────────────────────────────────

function openSyncDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('floodwatch-sync', 1);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending-subscriptions'))
        db.createObjectStore('pending-subscriptions', { keyPath: 'id', autoIncrement: true });
      if (!db.objectStoreNames.contains('pending-reports'))
        db.createObjectStore('pending-reports', { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

function getAllFromStore(db, storeName) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = () => reject(req.error);
  });
}

function deleteFromStore(db, storeName, id) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(storeName, 'readwrite');
    const req = tx.objectStore(storeName).delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = () => reject(req.error);
  });
}

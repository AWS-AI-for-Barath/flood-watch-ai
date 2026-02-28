/* ============================================================
   FloodWatch PWA — Service Worker
   Offline caching · Background Sync · Cache-first shell
   ============================================================ */

const CACHE_NAME = 'floodwatch-v1';
const BG_SYNC_TAG = 'floodwatch-upload-sync';

// App shell assets to pre-cache on install
const SHELL_ASSETS = [
    './',
    './index.html',
    './style.css',
    './app.js',
    './upload.js',
    './manifest.json'
];

// ---- INSTALL ----
self.addEventListener('install', (event) => {
    console.log('[SW] Install');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(SHELL_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// ---- ACTIVATE ----
self.addEventListener('activate', (event) => {
    console.log('[SW] Activate');
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key !== CACHE_NAME)
                    .map(key => {
                        console.log('[SW] Deleting old cache:', key);
                        return caches.delete(key);
                    })
            )
        ).then(() => self.clients.claim())
    );
});

// ---- FETCH ----
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests (uploads, API calls)
    if (event.request.method !== 'GET') return;

    // Skip cross-origin requests (fonts, CDN) — let them go to network
    if (url.origin !== self.location.origin) {
        // Try network first for external resources, fall back to cache
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // App shell: cache-first
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;

            return fetch(event.request).then(response => {
                // Cache successful responses for offline use
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            });
        }).catch(() => {
            // Fallback for navigation requests
            if (event.request.mode === 'navigate') {
                return caches.match('./index.html');
            }
        })
    );
});

// ---- BACKGROUND SYNC ----
self.addEventListener('sync', (event) => {
    if (event.tag === BG_SYNC_TAG) {
        console.log('[SW] Background sync triggered');
        event.waitUntil(processUploadQueue());
    }
});

/**
 * Process the IndexedDB upload queue from the service worker context.
 * Re-implements minimal IndexedDB + upload logic since SW cannot import ES modules.
 */
async function processUploadQueue() {
    const DB_NAME = 'floodwatch-db';
    const DB_VERSION = 1;
    const STORE_NAME = 'pending-uploads';
    const API_BASE_URL = 'https://481hzpqaq3.execute-api.us-east-1.amazonaws.com';
    const MAX_RETRIES = 5;

    function openDB() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id' });
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    try {
        const db = await openDB();

        const entries = await new Promise((resolve, reject) => {
            const tx = db.transaction(STORE_NAME, 'readonly');
            const req = tx.objectStore(STORE_NAME).getAll();
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });

        for (const entry of entries) {
            if ((entry.retries || 0) >= MAX_RETRIES) continue;

            try {
                const ext = entry.metadata.media_type === 'video' ? 'mp4' : 'jpg';
                const mediaFilename = `${entry.id}.${ext}`;
                const metadataFilename = `${entry.id}.json`;

                // Get pre-signed URLs
                const presignResp = await fetch(`${API_BASE_URL}/presign`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mediaKey: `media/${mediaFilename}`,
                        metadataKey: `metadata/${metadataFilename}`
                    })
                });

                if (!presignResp.ok) throw new Error(`Pre-sign failed: ${presignResp.status}`);
                const { url: mediaUrl, metadataUrl } = await presignResp.json();

                // Upload media
                const mediaContentType = entry.metadata.media_type === 'video' ? 'video/mp4' : 'image/jpeg';
                const mediaResp = await fetch(mediaUrl, {
                    method: 'PUT',
                    headers: { 'Content-Type': mediaContentType },
                    body: entry.mediaBlob
                });
                if (!mediaResp.ok) throw new Error(`Media upload failed: ${mediaResp.status}`);

                // Upload metadata
                const metaBlob = new Blob([JSON.stringify(entry.metadata)], { type: 'application/json' });
                const metaResp = await fetch(metadataUrl, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: metaBlob
                });
                if (!metaResp.ok) throw new Error(`Metadata upload failed: ${metaResp.status}`);

                // Success — remove from queue
                await new Promise((resolve, reject) => {
                    const tx = db.transaction(STORE_NAME, 'readwrite');
                    tx.objectStore(STORE_NAME).delete(entry.id);
                    tx.oncomplete = () => resolve();
                    tx.onerror = () => reject(tx.error);
                });

                console.log(`[SW] Uploaded ${entry.id}`);

            } catch (err) {
                console.warn(`[SW] Upload failed for ${entry.id}:`, err.message);
                entry.retries = (entry.retries || 0) + 1;
                await new Promise((resolve, reject) => {
                    const tx = db.transaction(STORE_NAME, 'readwrite');
                    tx.objectStore(STORE_NAME).put(entry);
                    tx.oncomplete = () => resolve();
                    tx.onerror = () => reject(tx.error);
                });
            }
        }

        // Notify clients to refresh UI
        const clients = await self.clients.matchAll();
        clients.forEach(client => client.postMessage({ type: 'SYNC_COMPLETE' }));

    } catch (err) {
        console.error('[SW] Background sync error:', err);
    }
}

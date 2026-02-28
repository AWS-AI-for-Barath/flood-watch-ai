/* ============================================================
   FloodWatch PWA — Upload Manager
   Pre-signed URL uploads · Retry · Background Sync · Queue
   ============================================================ */

// ---- Configuration ----
// Replace with your actual API Gateway / Lambda endpoint that returns pre-signed URLs.
const API_BASE_URL = 'https://481hzpqaq3.execute-api.us-east-1.amazonaws.com';  // FloodWatch API Gateway

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1000;
const BG_SYNC_TAG = 'floodwatch-upload-sync';

// ---- IndexedDB Helpers ----
const DB_NAME = 'floodwatch-db';
const DB_VERSION = 1;
const STORE_NAME = 'pending-uploads';

/** Open (or create) the IndexedDB database. */
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

/** Add an upload entry to the queue. */
async function enqueue(entry) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(entry);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

/** Remove an upload entry from the queue by ID. */
async function dequeue(id) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(id);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

/** Get all pending upload entries. */
async function getAllPending() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

/** Update an existing entry (e.g. retry count, status). */
async function updateEntry(entry) {
    return enqueue(entry); // put() upserts
}

// ---- Upload Logic ----

/**
 * Request a pre-signed PUT URL from the backend.
 * Expected response: { "url": "https://s3.../...", "metadataUrl": "https://s3.../..." }
 *
 * In production, replace this with your API Gateway endpoint that invokes
 * a Lambda to generate S3 pre-signed PUT URLs for both media and metadata.
 */
async function getPresignedUrls(filename, metadataFilename) {
    const resp = await fetch(`${API_BASE_URL}/presign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mediaKey: `media/${filename}`,
            metadataKey: `metadata/${metadataFilename}`
        })
    });

    if (!resp.ok) {
        throw new Error(`Pre-sign request failed: ${resp.status}`);
    }

    return resp.json();
}

/**
 * Upload a blob to S3 using a pre-signed PUT URL.
 * Handles progress tracking if a callback is provided.
 */
function uploadToS3(presignedUrl, blob, contentType, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', presignedUrl, true);
        xhr.setRequestHeader('Content-Type', contentType);

        if (onProgress) {
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) onProgress(e.loaded / e.total);
            };
        }

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve();
            } else {
                reject(new Error(`S3 upload failed: ${xhr.status}`));
            }
        };

        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.ontimeout = () => reject(new Error('Upload timed out'));
        xhr.timeout = 120000; // 2 minutes

        xhr.send(blob);
    });
}

/** Exponential backoff with jitter. */
function backoffDelay(attempt) {
    const delay = BASE_DELAY_MS * Math.pow(2, attempt);
    const jitter = delay * 0.3 * Math.random();
    return delay + jitter;
}

/**
 * Attempt to upload a single queue entry with retries.
 * Returns true on success, false on exhausted retries.
 */
async function uploadEntry(entry, onStatusChange) {
    const retries = entry.retries || 0;

    for (let attempt = retries; attempt < MAX_RETRIES; attempt++) {
        try {
            if (onStatusChange) onStatusChange(entry.id, 'uploading');

            // 1. Get pre-signed URLs
            const ext = entry.metadata.media_type === 'video' ? 'mp4' : 'jpg';
            const mediaFilename = `${entry.id}.${ext}`;
            const metadataFilename = `${entry.id}.json`;
            const { url: mediaUrl, metadataUrl } = await getPresignedUrls(mediaFilename, metadataFilename);

            // 2. Upload media blob
            const mediaContentType = entry.metadata.media_type === 'video' ? 'video/mp4' : 'image/jpeg';
            await uploadToS3(mediaUrl, entry.mediaBlob, mediaContentType, (progress) => {
                if (onStatusChange) onStatusChange(entry.id, 'uploading', progress);
            });

            // 3. Upload metadata JSON
            const metadataBlob = new Blob([JSON.stringify(entry.metadata)], { type: 'application/json' });
            await uploadToS3(metadataUrl, metadataBlob, 'application/json');

            // 4. Success — remove from queue
            await dequeue(entry.id);
            if (onStatusChange) onStatusChange(entry.id, 'done');
            return true;

        } catch (err) {
            console.warn(`[Upload] Attempt ${attempt + 1}/${MAX_RETRIES} failed for ${entry.id}:`, err.message);

            // Update retry count in IndexedDB
            entry.retries = attempt + 1;
            await updateEntry(entry);

            if (attempt + 1 < MAX_RETRIES) {
                const delay = backoffDelay(attempt);
                console.log(`[Upload] Retrying in ${Math.round(delay)}ms...`);
                await new Promise(r => setTimeout(r, delay));
            }
        }
    }

    // Exhausted retries
    if (onStatusChange) onStatusChange(entry.id, 'failed');
    return false;
}

// ---- Upload Manager (public API) ----

class UploadManager {
    constructor() {
        this._processing = false;
        this._listeners = new Set();
    }

    /** Subscribe to upload status changes: callback(id, status, progress?) */
    onStatusChange(callback) {
        this._listeners.add(callback);
        return () => this._listeners.delete(callback);
    }

    _notify(id, status, progress) {
        this._listeners.forEach(cb => cb(id, status, progress));
    }

    /**
     * Save a capture to the local queue and attempt upload.
     * @param {string} id - UUID
     * @param {Blob} mediaBlob - Image or video blob
     * @param {object} metadata - Telemetry + metadata object
     */
    async save(id, mediaBlob, metadata) {
        const entry = {
            id,
            mediaBlob,
            metadata,
            retries: 0,
            createdAt: Date.now()
        };

        await enqueue(entry);
        this._notify(id, 'pending');

        // Attempt immediate upload if online
        if (navigator.onLine) {
            this.processQueue();
        } else {
            // Register background sync
            this._registerSync();
        }
    }

    /** Process all pending uploads in the queue. */
    async processQueue() {
        if (this._processing) return;
        this._processing = true;

        try {
            const entries = await getAllPending();
            for (const entry of entries) {
                if (!navigator.onLine) {
                    this._registerSync();
                    break;
                }
                await uploadEntry(entry, (id, status, progress) => this._notify(id, status, progress));
            }
        } catch (err) {
            console.error('[UploadManager] Queue processing error:', err);
        } finally {
            this._processing = false;
        }
    }

    /** Get current queue count. */
    async getQueueCount() {
        const entries = await getAllPending();
        return entries.length;
    }

    /** Get all queue entries (for UI display). */
    async getQueueEntries() {
        return getAllPending();
    }

    /** Register for background sync if supported. */
    _registerSync() {
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            navigator.serviceWorker.ready.then(reg => {
                return reg.sync.register(BG_SYNC_TAG);
            }).catch(err => {
                console.warn('[UploadManager] Background sync registration failed:', err);
            });
        }
    }
}

// ---- Exports ----
export {
    UploadManager,
    DB_NAME,
    DB_VERSION,
    STORE_NAME,
    BG_SYNC_TAG,
    getAllPending,
    uploadEntry
};

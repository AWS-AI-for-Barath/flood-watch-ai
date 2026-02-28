/* ============================================================
   FloodWatch PWA — App Controller
   Media capture · Telemetry · IndexedDB · UI Orchestration
   ============================================================ */

import { UploadManager } from './upload.js';

// ================================================================
//  CONSTANTS
// ================================================================
const MAX_VIDEO_DURATION_S = 10;
const JPEG_QUALITY = 0.85;

// ================================================================
//  STATE
// ================================================================
let captureMode = 'photo';          // 'photo' | 'video'
let isRecording = false;
let mediaStream = null;
let mediaRecorder = null;
let recordedChunks = [];
let recordingTimerInterval = null;
let recordingStartTime = 0;

const telemetry = {
    lat: null,
    lon: null,
    heading: null,
    pitch: null,
    yaw: null
};

const uploadManager = new UploadManager();

// ================================================================
//  DOM REFS
// ================================================================
const $ = (id) => document.getElementById(id);

const dom = {
    app: $('app'),
    permOverlay: $('permissionOverlay'),
    btnGrant: $('btnGrantPermission'),
    cameraFeed: $('cameraFeed'),
    snapshotCanvas: $('snapshotCanvas'),
    cameraPlaceholder: $('cameraPlaceholder'),
    viewfinder: $('viewfinder'),
    vfFlash: $('vfFlash'),
    captureSuccess: $('captureSuccess'),
    offlineBanner: $('offlineBanner'),
    liveIndicator: $('liveIndicator'),
    statusDot: $('statusDot'),
    statusText: $('statusText'),
    shutterRipple: $('shutterRipple'),
    recIndicator: $('recIndicator'),
    recTimer: $('recTimer'),
    btnPhoto: $('btnPhoto'),
    btnVideo: $('btnVideo'),
    btnShutter: $('btnShutter'),
    queueBadge: $('queueBadge'),
    queueCount: $('queueCount'),
    queuePanel: $('queuePanel'),
    queuePanelHeader: $('queuePanelHeader'),
    queuePanelBadge: $('queuePanelBadge'),
    queueList: $('queueList'),
    toastContainer: $('toastContainer'),
    // Telemetry cells
    chipGps: $('chipGps'),
    chipHeading: $('chipHeading'),
    chipPitch: $('chipPitch'),
    chipYaw: $('chipYaw'),
    gpsValue: $('gpsValue'),
    hdgValue: $('hdgValue'),
    pitchValue: $('pitchValue'),
    yawValue: $('yawValue'),
};

// ================================================================
//  UTILITIES
// ================================================================

/** Generate UUID v4 (crypto-native with fallback). */
function generateUUID() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
}

/** Format seconds to MM:SS. */
function formatTime(seconds) {
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(Math.floor(seconds % 60)).padStart(2, '0');
    return `${m}:${s}`;
}

/** Format bytes to human-readable. */
function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
}

// ================================================================
//  TOAST NOTIFICATIONS
// ================================================================

const TOAST_ICONS = { success: '✓', error: '⚠', info: 'ℹ' };

function showToast(message, type = 'info', durationMs = 3500) {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `<span class="toast__icon">${TOAST_ICONS[type] || 'ℹ'}</span> ${message}`;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        toast.addEventListener('animationend', () => toast.remove());
    }, durationMs);
}

// ================================================================
//  CONNECTIVITY
// ================================================================

function updateConnectivityUI() {
    const online = navigator.onLine;
    // LIVE indicator
    if (dom.liveIndicator) {
        dom.liveIndicator.classList.toggle('offline', !online);
    }
    dom.statusText.textContent = online ? 'LIVE' : 'OFFLINE';
    // Offline banner
    if (dom.offlineBanner) {
        dom.offlineBanner.classList.toggle('visible', !online);
    }
}

window.addEventListener('online', () => {
    updateConnectivityUI();
    showToast('Connection restored — uploading queued reports', 'success');
    uploadManager.processQueue();
});

window.addEventListener('offline', () => {
    updateConnectivityUI();
    showToast('You are offline — captures will be queued', 'info');
});

// ================================================================
//  TELEMETRY: GPS
// ================================================================

function startGPS() {
    if (!('geolocation' in navigator)) {
        console.warn('[Telemetry] Geolocation not available');
        return;
    }

    const options = { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 };

    navigator.geolocation.watchPosition(
        (pos) => {
            telemetry.lat = pos.coords.latitude;
            telemetry.lon = pos.coords.longitude;
            updateTelemetryUI();
        },
        (err) => {
            console.warn('[Telemetry] GPS error:', err.message);
            telemetry.lat = null;
            telemetry.lon = null;
        },
        options
    );
}

// ================================================================
//  TELEMETRY: DEVICE ORIENTATION
// ================================================================

function startOrientation() {
    // iOS 13+ requires permission request
    if (typeof DeviceOrientationEvent !== 'undefined' &&
        typeof DeviceOrientationEvent.requestPermission === 'function') {
        DeviceOrientationEvent.requestPermission()
            .then(state => {
                if (state === 'granted') {
                    window.addEventListener('deviceorientation', handleOrientation, true);
                }
            })
            .catch(err => console.warn('[Telemetry] Orientation permission denied:', err));
    } else if ('DeviceOrientationEvent' in window) {
        window.addEventListener('deviceorientation', handleOrientation, true);
    } else {
        console.warn('[Telemetry] DeviceOrientationEvent not supported');
    }
}

function handleOrientation(e) {
    telemetry.heading = (e.alpha !== null) ? Math.round(e.alpha * 10) / 10 : null;
    telemetry.pitch = (e.beta !== null) ? Math.round(e.beta * 10) / 10 : null;
    telemetry.yaw = (e.gamma !== null) ? Math.round(e.gamma * 10) / 10 : null;
    updateTelemetryUI();
}

// ================================================================
//  TELEMETRY UI
// ================================================================

function updateTelemetryUI() {
    // GPS
    if (telemetry.lat !== null && telemetry.lon !== null) {
        dom.gpsValue.textContent = `${telemetry.lat.toFixed(4)}, ${telemetry.lon.toFixed(4)}`;
        dom.chipGps.classList.add('active');
    }

    // Heading
    if (telemetry.heading !== null) {
        dom.hdgValue.textContent = `${telemetry.heading}°`;
        dom.chipHeading.classList.add('active');
    }

    // Pitch
    if (telemetry.pitch !== null) {
        dom.pitchValue.textContent = `${telemetry.pitch}°`;
        dom.chipPitch.classList.add('active');
    }

    // Yaw
    if (telemetry.yaw !== null) {
        dom.yawValue.textContent = `${telemetry.yaw}°`;
        dom.chipYaw.classList.add('active');
    }
}

// ================================================================
//  CAMERA
// ================================================================

async function startCamera() {
    try {
        const constraints = {
            video: {
                facingMode: { ideal: 'environment' },
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            },
            audio: captureMode === 'video'
        };

        mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        dom.cameraFeed.srcObject = mediaStream;
        dom.cameraFeed.classList.remove('hidden');
        dom.cameraPlaceholder.classList.add('hidden');
        dom.permOverlay.classList.add('hidden');

        return true;
    } catch (err) {
        console.error('[Camera] Access denied or unavailable:', err);
        dom.cameraFeed.classList.add('hidden');
        dom.cameraPlaceholder.classList.remove('hidden');
        showToast('Camera access denied. Please enable in browser settings.', 'error');
        return false;
    }
}

function stopCamera() {
    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }
}

// ================================================================
//  PHOTO CAPTURE
// ================================================================

function capturePhoto() {
    const video = dom.cameraFeed;
    const canvas = dom.snapshotCanvas;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    return new Promise((resolve) => {
        canvas.toBlob((blob) => resolve(blob), 'image/jpeg', JPEG_QUALITY);
    });
}

// ================================================================
//  VIDEO CAPTURE
// ================================================================

function startVideoRecording() {
    recordedChunks = [];

    // Determine supported MIME type
    const mimeTypes = [
        'video/webm;codecs=vp9,opus',
        'video/webm;codecs=vp8,opus',
        'video/webm',
        'video/mp4'
    ];
    let selectedMime = '';
    for (const mt of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mt)) { selectedMime = mt; break; }
    }

    const options = selectedMime ? { mimeType: selectedMime } : {};
    mediaRecorder = new MediaRecorder(mediaStream, options);

    mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: selectedMime || 'video/webm' });
        await handleCapture(blob, 'video');
        recordedChunks = [];
    };

    mediaRecorder.start(500); // timeslice: 500ms chunks
    isRecording = true;
    recordingStartTime = Date.now();

    // UI
    dom.recIndicator.classList.add('active');
    dom.recTimer.classList.add('active');
    dom.btnShutter.classList.add('recording');

    // Timer countdown
    recordingTimerInterval = setInterval(() => {
        const elapsed = (Date.now() - recordingStartTime) / 1000;
        dom.recTimer.textContent = formatTime(elapsed);

        // Auto-stop at max duration
        if (elapsed >= MAX_VIDEO_DURATION_S) {
            stopVideoRecording();
        }
    }, 250);
}

function stopVideoRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;

    // UI
    clearInterval(recordingTimerInterval);
    dom.recIndicator.classList.remove('active');
    dom.recTimer.classList.remove('active');
    dom.recTimer.textContent = '00:00';
    dom.btnShutter.classList.remove('recording');
}

// ================================================================
//  CAPTURE ORCHESTRATION
// ================================================================

/** Trigger haptic feedback if available. */
function haptic(pattern = [15]) {
    if ('vibrate' in navigator) {
        try { navigator.vibrate(pattern); } catch (_) { /* silent */ }
    }
}

/** Show capture flash + success checkmark on viewfinder. */
function showCaptureConfirmation() {
    // Flash layer
    if (dom.vfFlash) {
        dom.viewfinder.classList.add('flash');
        setTimeout(() => dom.viewfinder.classList.remove('flash'), 300);
    }
    // Success checkmark
    if (dom.captureSuccess) {
        dom.captureSuccess.classList.remove('show');
        void dom.captureSuccess.offsetWidth;
        dom.captureSuccess.classList.add('show');
        setTimeout(() => dom.captureSuccess.classList.remove('show'), 800);
    }
    // Shutter ripple
    if (dom.shutterRipple) {
        dom.shutterRipple.classList.remove('animate');
        void dom.shutterRipple.offsetWidth;
        dom.shutterRipple.classList.add('animate');
        setTimeout(() => dom.shutterRipple.classList.remove('animate'), 600);
    }
    // Haptic
    haptic([12, 50, 12]);
}

async function handleCapture(blob, mediaType) {
    const id = generateUUID();
    const ext = mediaType === 'video' ? 'mp4' : 'jpg';
    const timestamp = new Date().toISOString();

    const metadata = {
        timestamp,
        lat: telemetry.lat,
        lon: telemetry.lon,
        heading: telemetry.heading,
        pitch: telemetry.pitch,
        yaw: telemetry.yaw,
        device: 'mobile',
        filename: `${id}.${ext}`,
        media_type: mediaType === 'video' ? 'video' : 'image'
    };

    // Visual + haptic confirmation
    showCaptureConfirmation();

    // Save to upload manager (IndexedDB + attempt upload)
    await uploadManager.save(id, blob, metadata);
    await refreshQueueUI();

    const sizeStr = formatBytes(blob.size);
    showToast(`${mediaType === 'video' ? 'Video' : 'Photo'} captured (${sizeStr})`, 'success');
}

// ================================================================
//  SHUTTER BUTTON
// ================================================================

async function onShutterPress() {
    if (!mediaStream) {
        const started = await startCamera();
        if (!started) return;
    }

    if (captureMode === 'photo') {
        haptic([10]);
        const blob = await capturePhoto();
        if (blob) await handleCapture(blob, 'image');
    } else {
        // Video toggle
        if (isRecording) {
            stopVideoRecording();
        } else {
            // Restart stream with audio
            if (!mediaStream.getAudioTracks().length) {
                stopCamera();
                await startCamera();
            }
            startVideoRecording();
        }
    }
}

// ================================================================
//  MODE TOGGLE
// ================================================================

function setMode(mode) {
    captureMode = mode;

    // Stop any active recording on mode switch
    if (isRecording) stopVideoRecording();

    dom.btnPhoto.classList.toggle('active', mode === 'photo');
    dom.btnVideo.classList.toggle('active', mode === 'video');

    // Restart camera to include/exclude audio
    if (mediaStream) {
        stopCamera();
        startCamera();
    }
}

// ================================================================
//  UPLOAD QUEUE UI
// ================================================================

async function refreshQueueUI() {
    const entries = await uploadManager.getQueueEntries();
    const count = entries.length;

    dom.queueCount.textContent = count;
    dom.queueBadge.dataset.count = count;
    dom.queuePanelBadge.textContent = `${count} pending`;
    dom.queuePanelBadge.dataset.count = count;

    if (count === 0) {
        dom.queueList.innerHTML = `
        <div class="queue-console__empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          ALL REPORTS TRANSMITTED
        </div>`;
    } else {
        dom.queueList.innerHTML = entries.map(entry => {
            const icon = entry.metadata.media_type === 'video' ? '🎬' : '📷';
            const size = formatBytes(entry.mediaBlob?.size || 0);
            return `
            <div class="q-item" data-id="${entry.id}" role="listitem">
              <span class="q-item__dot q-item__dot--pending"></span>
              <span class="q-item__icon">${icon}</span>
              <div class="q-item__info">
                <div class="q-item__name">${entry.metadata.filename}</div>
                <div class="q-item__meta">${size} · ${new Date(entry.metadata.timestamp).toLocaleTimeString()}</div>
              </div>
            </div>`;
        }).join('');
    }
}

function updateQueueItemStatus(id, status) {
    const item = dom.queueList.querySelector(`[data-id="${id}"]`);
    if (!item) return;

    const dot = item.querySelector('.q-item__dot');
    dot.className = `q-item__dot q-item__dot--${status}`;

    if (status === 'done') {
        setTimeout(() => {
            item.style.opacity = '0';
            item.style.transform = 'translateX(20px)';
            setTimeout(() => { item.remove(); refreshQueueUI(); }, 300);
        }, 800);
    }
}

// ================================================================
//  EVENT WIRING
// ================================================================

function init() {
    // Connectivity
    updateConnectivityUI();

    // Permission overlay
    dom.btnGrant.addEventListener('click', async () => {
        const ok = await startCamera();
        if (ok) {
            startGPS();
            startOrientation();
        }
    });

    // Shutter
    dom.btnShutter.addEventListener('click', onShutterPress);

    // Mode toggle
    dom.btnPhoto.addEventListener('click', () => setMode('photo'));
    dom.btnVideo.addEventListener('click', () => setMode('video'));

    // Queue panel toggle
    dom.queuePanelHeader.addEventListener('click', () => {
        const isOpen = dom.queuePanel.classList.toggle('open');
        dom.queuePanelHeader.setAttribute('aria-expanded', isOpen);
    });

    // Keyboard support for queue panel header
    dom.queuePanelHeader.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            dom.queuePanelHeader.click();
        }
    });

    // Upload status listener
    uploadManager.onStatusChange((id, status) => {
        updateQueueItemStatus(id, status);
        refreshQueueUI();
    });

    // Initial queue render
    refreshQueueUI();

    // Auto-start camera if permission already granted (no overlay needed)
    navigator.mediaDevices.enumerateDevices().then(devices => {
        const hasCamera = devices.some(d => d.kind === 'videoinput' && d.label);
        if (hasCamera) {
            dom.permOverlay.classList.add('hidden');
            startCamera();
            startGPS();
            startOrientation();
        }
    });
}

// Boot
document.addEventListener('DOMContentLoaded', init);

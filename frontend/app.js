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

// Upload View State
let selectedUploadFile = null;
let uploadMediaType = null; // 'image' | 'video'

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
    captureSuccess: $('captureSuccess'),
    offlineBanner: $('offlineBanner'),
    recIndicator: $('recIndicator'),
    recTimer: $('recTimer'),
    btnPhoto: $('btnPhoto'),
    btnVideo: $('btnVideo'),
    btnShutter: $('btnShutter'),
    statusDot: $('statusDot'),
    statusText: $('statusText'),
    queueBadge: $('queueBadge'),
    queueCount: $('queueCount'),
    queuePanel: $('queuePanel'),
    queuePanelHeader: $('queuePanelHeader'),
    queuePanelBadge: $('queuePanelBadge'),
    queueList: $('queueList'),
    toastContainer: $('toastContainer'),
    chipGps: $('chipGps'),
    chipHeading: $('chipHeading'),
    chipPitch: $('chipPitch'),
    chipYaw: $('chipYaw'),

    // View Switching
    tabCapture: $('tabCapture'),
    tabUpload: $('tabUpload'),
    captureView: $('captureView'),
    uploadView: $('uploadView'),

    // Upload Zone
    dropZone: $('dropZone'),
    fileInput: $('fileInput'),
    btnBrowse: $('btnBrowse'),
    uploadPrompt: $('uploadPrompt'),
    uploadPreviewContainer: $('uploadPreviewContainer'),
    previewMediaBox: $('previewMediaBox'),
    btnClearFile: $('btnClearFile'),
    btnSubmitUpload: $('btnSubmitUpload'),
    uploadError: $('uploadError'),
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
    dom.statusDot.className = `status-dot ${online ? 'status-dot--online' : 'status-dot--offline'}`;
    dom.statusText.textContent = online ? 'Online' : 'Offline';
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
        dom.chipGps.innerHTML = `
        <div class="telemetry-label">LOCATION</div>
        <div class="telemetry-value">${telemetry.lat.toFixed(4)}, ${telemetry.lon.toFixed(4)}</div>`;
    }

    // Heading
    if (telemetry.heading !== null) {
        dom.chipHeading.innerHTML = `
        <div class="telemetry-label">HEADING</div>
        <div class="telemetry-value">${telemetry.heading}°</div>`;
    }

    // Pitch
    if (telemetry.pitch !== null) {
        dom.chipPitch.innerHTML = `
        <div class="telemetry-label">PITCH</div>
        <div class="telemetry-value">${telemetry.pitch}°</div>`;
    }

    // Yaw
    if (telemetry.yaw !== null) {
        dom.chipYaw.innerHTML = `
        <div class="telemetry-label">YAW</div>
        <div class="telemetry-value">${telemetry.yaw}°</div>`;
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
    // Flash
    if (dom.viewfinder) {
        dom.viewfinder.classList.add('flash');
        setTimeout(() => dom.viewfinder.classList.remove('flash'), 350);
    }
    // Success checkmark
    if (dom.captureSuccess) {
        dom.captureSuccess.classList.remove('show');
        void dom.captureSuccess.offsetWidth; // force reflow
        dom.captureSuccess.classList.add('show');
        setTimeout(() => dom.captureSuccess.classList.remove('show'), 900);
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

    // Render list items (or empty state)
    if (count === 0) {
        dom.queueList.innerHTML = `
        <div class="queue-panel__empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          All reports uploaded
        </div>`;
    } else {
        dom.queueList.innerHTML = entries.map(entry => {
            const isVid = entry.metadata.media_type === 'video';
            const iconSvg = isVid
                ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>`
                : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`;

            const size = formatBytes(entry.mediaBlob?.size || 0);
            return `
            <div class="queue-item" data-id="${entry.id}" role="listitem">
              <span class="queue-item__status queue-item__status--pending"></span>
              <div class="queue-item__icon-wrapper">${iconSvg}</div>
              <div class="queue-item__info">
                <div class="queue-item__name">${entry.metadata.filename}</div>
                <div class="queue-item__meta">${size} · ${new Date(entry.metadata.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
              </div>
            </div>`;
        }).join('');
    }
}

function updateQueueItemStatus(id, status) {
    const item = dom.queueList.querySelector(`[data-id="${id}"]`);
    if (!item) return;

    const dot = item.querySelector('.queue-item__status');
    dot.className = `queue-item__status queue-item__status--${status}`;

    // Remove completed items after a beat
    if (status === 'done') {
        setTimeout(() => {
            item.style.opacity = '0';
            item.style.transform = 'translateX(20px)';
            setTimeout(() => { item.remove(); refreshQueueUI(); }, 300);
        }, 800);
    }
}

// ================================================================
//  VIEW ORCHESTRATION (CAPTURE VS UPLOAD)
// ================================================================

function switchMainView(view) {
    if (view === 'upload') {
        // Stop camera to save battery while in gallery mode
        if (!isRecording) stopCamera();

        dom.tabCapture.classList.remove('active');
        dom.tabCapture.setAttribute('aria-selected', 'false');
        dom.tabUpload.classList.add('active');
        dom.tabUpload.setAttribute('aria-selected', 'true');

        dom.captureView.classList.add('hidden');
        dom.uploadView.classList.remove('hidden');
    } else {
        // Switch back to Capture
        dom.tabUpload.classList.remove('active');
        dom.tabUpload.setAttribute('aria-selected', 'false');
        dom.tabCapture.classList.add('active');
        dom.tabCapture.setAttribute('aria-selected', 'true');

        dom.uploadView.classList.add('hidden');
        dom.captureView.classList.remove('hidden');

        // Restart camera
        startCamera();
    }
}

// ================================================================
//  FILE UPLOAD & VALIDATION
// ================================================================

function showUploadError(message) {
    dom.uploadError.textContent = message;
    dom.uploadError.classList.remove('hidden');
    dom.btnSubmitUpload.disabled = true;
    dom.btnSubmitUpload.classList.add('disabled');
}

function clearUploadError() {
    dom.uploadError.textContent = '';
    dom.uploadError.classList.add('hidden');
}

function clearUploadSelection() {
    selectedUploadFile = null;
    uploadMediaType = null;
    dom.fileInput.value = '';
    dom.previewMediaBox.innerHTML = '';

    dom.uploadPreviewContainer.classList.add('hidden');
    dom.uploadPrompt.classList.remove('hidden');
    dom.dropZone.classList.remove('dragover');

    clearUploadError();
    dom.btnSubmitUpload.disabled = true;
    dom.btnSubmitUpload.classList.add('disabled');
}

async function handleFileSelect(file) {
    clearUploadError();

    if (!file) {
        clearUploadSelection();
        return;
    }

    // 1. Basic Type Validation
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');

    if (!isImage && !isVideo) {
        showUploadError('Invalid format. Please select an image or MP4/QuickTime video.');
        clearUploadSelection();
        return;
    }

    // 2. Size Validation (e.g. 50MB max)
    const MAX_SIZE = 50 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
        showUploadError('File is too large. Maximum size is 50MB.');
        clearUploadSelection();
        return;
    }

    // 3. Video Specific Validation
    if (isVideo) {
        try {
            const url = URL.createObjectURL(file);
            const video = document.createElement('video');
            video.src = url;
            video.preload = 'metadata';

            await new Promise((resolve, reject) => {
                video.onloadedmetadata = resolve;
                video.onerror = reject;
                // Timeout fallback
                setTimeout(reject, 5000);
            });

            // Allow up to 10.5 seconds for tiny overhead/rounding leeway
            if (video.duration > 10.5) {
                showUploadError('Video must be 10 seconds or shorter.');
                URL.revokeObjectURL(url);
                clearUploadSelection();
                return;
            }

            // Render Preview
            dom.previewMediaBox.innerHTML = `<video src="${url}" controls muted style="width:100%; height:100%; object-fit:contain; border-radius:12px;"></video>`;
        } catch (err) {
            console.error('[Upload] Video validation failed:', err);
            showUploadError('Could not process video file.');
            clearUploadSelection();
            return;
        }
    } else {
        // Image Preview
        const url = URL.createObjectURL(file);
        dom.previewMediaBox.innerHTML = `<img src="${url}" alt="Selected media" style="width:100%; height:100%; object-fit:contain; border-radius:12px;">`;
    }

    // Validated Successfully
    selectedUploadFile = file;
    uploadMediaType = isVideo ? 'video' : 'image';

    dom.uploadPrompt.classList.add('hidden');
    dom.uploadPreviewContainer.classList.remove('hidden');

    dom.btnSubmitUpload.disabled = false;
    dom.btnSubmitUpload.classList.remove('disabled');
}

// Drag functionality
function bindDragEvents() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dom.dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

    ['dragenter', 'dragover'].forEach(eventName => {
        dom.dropZone.addEventListener(eventName, () => dom.dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dom.dropZone.addEventListener(eventName, () => dom.dropZone.classList.remove('dragover'), false);
    });

    dom.dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length) {
            handleFileSelect(files[0]);
        }
    }, false);
}

async function submitUploadFlow() {
    if (!selectedUploadFile || !uploadMediaType) return;

    // Construct fake metadata for uploaded files based on current telemetry
    const id = generateUUID();
    const timestamp = new Date().toISOString();

    // Cleanup name string (remove path, whitespace)
    const cleanName = selectedUploadFile.name ? selectedUploadFile.name.replace(/[^a-zA-Z0-9.\-]/g, '_') : 'uploaded_file';

    const metadata = {
        timestamp,
        lat: telemetry.lat,
        lon: telemetry.lon,
        heading: telemetry.heading,
        pitch: telemetry.pitch,
        yaw: telemetry.yaw,
        device: 'mobile-upload',
        filename: `${id}-${cleanName}`,
        media_type: uploadMediaType
    };

    dom.btnSubmitUpload.disabled = true;
    dom.btnSubmitUpload.innerHTML = `<span>Processing...</span>`;

    try {
        // Save/Upload
        await uploadManager.save(id, selectedUploadFile, metadata);
        await refreshQueueUI();

        showToast(`${uploadMediaType === 'video' ? 'Video' : 'Photo'} queued for upload`, 'success');

        // Reset and return to capture
        clearUploadSelection();
        dom.btnSubmitUpload.innerHTML = `<span>Queue to Upload</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
        switchMainView('capture');
    } catch (err) {
        console.error('[Upload] Flow failed', err);
        showUploadError('Error queuing file. Please try again.');
        dom.btnSubmitUpload.disabled = false;
        dom.btnSubmitUpload.classList.remove('disabled');
        dom.btnSubmitUpload.innerHTML = `<span>Queue to Upload</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
    }
}

// ================================================================
//  PLATFORM SHELL NAVIGATION
// ================================================================

function setupPlatformNavigation() {
    const navItems = document.querySelectorAll('.bottom-nav .nav-item');
    const platformViews = document.querySelectorAll('.platform-view');

    navItems.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            if (btn.classList.contains('active')) return; // Already there

            // Highlight nav
            navItems.forEach(n => n.classList.remove('active'));
            btn.classList.add('active');

            // Switch view
            platformViews.forEach(view => {
                if (view.id === targetId) {
                    view.classList.remove('hidden');
                    // Micro-haptic for premium feel
                    haptic([5]);
                } else {
                    view.classList.add('hidden');
                }
            });

            // Optimization: Pause camera to save battery when not in capture view
            if (targetId !== 'platformViewCapture' && !isRecording) {
                stopCamera();
            } else if (targetId === 'platformViewCapture') {
                // If returning to capture and we're looking at the Capture Segment (not Upload Segment), restart
                if (dom.tabCapture.classList.contains('active') && !mediaStream) {
                    startCamera();
                }
            }
        });
    });
}

// ================================================================
//  EVENT WIRING
// ================================================================

function init() {
    setupPlatformNavigation();

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

    // View Switching (Capture vs Upload)
    dom.tabCapture.addEventListener('click', () => switchMainView('capture'));
    dom.tabUpload.addEventListener('click', () => switchMainView('upload'));

    // Upload Flow Wiring
    dom.btnBrowse.addEventListener('click', () => dom.fileInput.click());
    dom.fileInput.addEventListener('change', (e) => handleFileSelect(e.target.files[0]));
    dom.btnClearFile.addEventListener('click', clearUploadSelection);
    dom.btnSubmitUpload.addEventListener('click', submitUploadFlow);
    bindDragEvents();

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

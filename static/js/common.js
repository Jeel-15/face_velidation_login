/**
 * Common JavaScript utilities for face verification system
 */

// Configuration
let CONFIG = {};

/**
 * Initialize configuration from backend
 */
async function initializeConfig() {
    try {
        const response = await fetch('/api/config');
        CONFIG = await response.json();
    } catch (e) {
        console.error('Failed to load config:', e);
        CONFIG = {
            frame_width: 640,
            frame_height: 480,
            enrollment_target_samples: 10,
            enrollment_min_samples: 8,
            login_capture_duration: 2,
            login_min_frames: 20
        };
    }
}

initializeConfig();

/**
 * Get webcam stream with constraints
 */
async function getWebcamStream() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: CONFIG.frame_width || 640 },
                height: { ideal: CONFIG.frame_height || 480 },
                facingMode: 'user'
            },
            audio: false
        });
        return stream;
    } catch (error) {
        console.error('Error accessing webcam:', error);
        throw new Error('Could not access webcam. Please check permissions and try again.');
    }
}

/**
 * Convert canvas frame to base64 for transmission
 */
function canvasToBase64(canvas) {
    return canvas.toDataURL('image/jpeg', 0.8);
}

/**
 * Capture a frame from video element to canvas.
 * Downsamples to max 320px wide to reduce payload and server processing time.
 */
function captureFrame(videoElement, canvasElement) {
    const MAX_WIDTH = 320;
    const srcW = videoElement.videoWidth;
    const srcH = videoElement.videoHeight;
    const scale = srcW > MAX_WIDTH ? MAX_WIDTH / srcW : 1;
    canvasElement.width = Math.round(srcW * scale);
    canvasElement.height = Math.round(srcH * scale);
    const ctx = canvasElement.getContext('2d');
    ctx.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
    return canvasToBase64(canvasElement);
}

/**
 * Show error message
 */
function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = message;
        element.style.display = 'block';
    }
}

/**
 * Hide error message
 */
function hideError(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

/**
 * Show status message
 */
function showStatus(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = message;
        element.style.display = 'block';
    }
}

/**
 * Hide status message
 */
function hideStatus(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

/**
 * Show/hide step elements
 */
function showStep(stepId) {
    document.querySelectorAll('.step').forEach(el => {
        el.classList.remove('active');
        el.style.display = 'none';
    });
    const step = document.getElementById(stepId);
    if (step) {
        step.classList.add('active');
        step.style.display = 'block';
    }

    // Widen login layout only for challenge step so users can keep
    // instructions and camera preview visible side by side.
    const container = document.querySelector('.container');
    const loginCard = document.querySelector('.login-card');
    const challengeMode = stepId === 'step-challenge';
    if (container && loginCard) {
        container.classList.toggle('challenge-mode', challengeMode);
        loginCard.classList.toggle('challenge-mode', challengeMode);
    }
}

/**
 * Make API POST request
 */
async function apiPost(endpoint, data) {
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        return {
            ok: response.ok,
            status: response.status,
            data: result
        };
    } catch (error) {
        console.error(`API error at ${endpoint}:`, error);
        return {
            ok: false,
            status: 0,
            error: error.message
        };
    }
}

/**
 * Stop video stream
 */
function stopStream(stream) {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
}

/**
 * Sleep utility
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Format date
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

console.log('Common utilities loaded');

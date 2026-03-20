/**
 * Face Enrollment Logic
 * Handles the enrollment flow: credentials -> face capture -> completion
 */

let enrollmentState = {
    sessionId: null,
    targetSamples: CONFIG.enrollment_target_samples || 10,
    minSamples: CONFIG.enrollment_min_samples || 8,
    collectedSamples: 0,
    isCapturing: false,
    stream: null,
    uploadInProgress: false
};

document.addEventListener('DOMContentLoaded', () => {
    initializeEnrollmentUI();
});

function initializeEnrollmentUI() {
    const enrollmentForm = document.getElementById('enrollmentForm');
    const captureBtn     = document.getElementById('captureBtn');
    const cancelEnrollBtn = document.getElementById('cancelEnrollBtn');

    if (enrollmentForm) {
        enrollmentForm.addEventListener('submit', handleEnrollmentStart);
    }

    if (captureBtn) {
        captureBtn.addEventListener('click', autoCapureLoop);
    }

    if (cancelEnrollBtn) {
        cancelEnrollBtn.addEventListener('click', handleEnrollmentCancel);
    }

    const params = new URLSearchParams(window.location.search);
    const prefUserId = params.get('user_id');
    if (prefUserId) {
        const userIdInput = document.getElementById('enrollUserId');
        if (userIdInput && !userIdInput.value) {
            userIdInput.value = prefUserId;
        }
    }
}

/**
 * Step 1: Start enrollment with credentials
 */
async function handleEnrollmentStart(event) {
    event.preventDefault();
    
    const userId = document.getElementById('enrollUserId').value.trim();
    const password = document.getElementById('enrollPassword').value.trim();
    
    if (!userId || !password) {
        showError('enrollError', 'User ID and password are required');
        return;
    }
    
    hideError('enrollError');
    
    // Call backend to start enrollment
    const result = await apiPost('/api/enrollment/start', {
        user_id: userId,
        password: password
    });
    
    if (!result.ok) {
        // 409 = already enrolled
        if (result.status === 409) {
            const el = document.getElementById('enrollError');
            if (el) {
                el.innerHTML = (result.data.error || 'Already enrolled.') +
                    ' Contact your admin to reset enrollment.';
                el.style.display = 'block';
            }
        } else {
            showError('enrollError', result.data.error || 'Failed to start enrollment');
        }
        return;
    }
    
    // Save session
    enrollmentState.sessionId = result.data.session_id;
    enrollmentState.targetSamples = result.data.target_samples;
    enrollmentState.minSamples = result.data.min_samples;
    enrollmentState.collectedSamples = 0;
    
    // Move to capture step
    showStep('step-capture');
    
    // Initialize webcam
    await initializeEnrollmentWebcam();
}

/**
 * Initialize webcam for enrollment
 */
async function initializeEnrollmentWebcam() {
    try {
        const videoElement = document.getElementById('webcamEnroll');
        if (!videoElement) return;
        
        if (enrollmentState.stream) {
            stopStream(enrollmentState.stream);
        }
        
        enrollmentState.stream = await getWebcamStream();
        videoElement.srcObject = enrollmentState.stream;

        // Wait for video to load, then show feed — user clicks Start Capture to begin
        videoElement.onloadedmetadata = () => {
            videoElement.play().catch(e => console.error('Play error:', e));
        };

        console.log('Enrollment webcam initialized');
    } catch (error) {
        showError('captureError', error.message);
    }
}

/**
 * Continuously capture rounds until target samples collected.
 */
async function autoCapureLoop() {
    const captureBtn = document.getElementById('captureBtn');
    if (captureBtn) captureBtn.style.display = 'none'; // hide manual button during auto-loop

    while (enrollmentState.collectedSamples < enrollmentState.targetSamples) {
        if (!enrollmentState.sessionId) break; // cancelled
        await startEnrollmentCapture();
        if (enrollmentState.collectedSamples < enrollmentState.targetSamples) {
            await sleep(600); // short pause between rounds
        }
    }
}

/**
 * Start enrollment capture (multiple 3-second sessions)
 */
async function startEnrollmentCapture() {
    const startBtn = document.getElementById('captureBtn');
    const videoElement = document.getElementById('webcamEnroll');
    const canvasElement = document.getElementById('enrollCaptureCanvas');
    const progressMsg = document.getElementById('progressMessage');
    
    if (!videoElement.srcObject) {
        showError('captureError', 'Webcam not ready');
        return;
    }

    hideError('captureError');

    if (enrollmentState.uploadInProgress) {
        showStatus('enrollStatus', 'Upload in progress, please wait...');
        return;
    }
    
    // Capture for 3 seconds
    const captureDuration = 3000; // 3 seconds
    const fps = 20;
    const frameDuration = 1000 / fps;
    const expectedFrames = Math.floor(captureDuration / frameDuration);
    
    enrollmentState.isCapturing = true;
    startBtn.disabled = true;
    progressMsg.textContent = 'Capturing frames...';
    showStatus('enrollStatus', '');
    
    const frames = [];
    const startTime = Date.now();
    
    while (enrollmentState.isCapturing && Date.now() - startTime < captureDuration) {
        try {
            const frameData = captureFrame(videoElement, canvasElement);
            frames.push(frameData);
        } catch (e) {
            console.error('Frame capture error:', e);
        }
        
        await sleep(frameDuration);
    }
    
    enrollmentState.isCapturing = false;
    startBtn.disabled = false;
    
    if (frames.length === 0) {
        showError('captureError', 'Failed to capture frames');
        progressMsg.textContent = 'Capture failed, try again';
        return;
    }
    
    // Upload frames to server
    progressMsg.textContent = 'Processing frames...';
    enrollmentState.uploadInProgress = true;
    showStatus('enrollStatus', 'Processing captured frames...');
    
    const result = await apiPost('/api/enrollment/capture', {
        session_id: enrollmentState.sessionId,
        frames: frames
    });
    
    enrollmentState.uploadInProgress = false;
    
    if (!result.ok) {
        const error = result.data.error || 'Failed to process frames';
        showError('captureError', error);
        progressMsg.textContent = 'Processing failed, try again';
        return;
    }
    
    // Update progress
    const newSamples = result.data.new_samples;
    enrollmentState.collectedSamples = result.data.total_samples;
    const totalCollected = result.data.total_samples;
    const targetSamples = result.data.target_samples;
    const isComplete = result.data.is_complete;
    
    updateEnrollmentProgress(totalCollected, targetSamples);
    progressMsg.textContent = result.data.message;
    
    hideStatus('enrollStatus');
    
    if (isComplete) {
        // Auto-complete enrollment
        await completeEnrollment();
    }
}

/**
 * Update enrollment progress bar
 */
function updateEnrollmentProgress(collected, target) {
    const progressFill = document.getElementById('progressFill');
    const sampleCount = document.getElementById('sampleCount');
    const targetCount = document.getElementById('targetCount');
    
    if (progressFill) {
        const percentage = (collected / target) * 100;
        progressFill.style.width = percentage + '%';
    }
    
    if (sampleCount) sampleCount.textContent = collected;
    if (targetCount) targetCount.textContent = target;
}

/**
 * Complete enrollment
 */
async function completeEnrollment() {
    if (!enrollmentState.sessionId) return;
    
    const result = await apiPost('/api/enrollment/complete', {
        session_id: enrollmentState.sessionId
    });
    
    if (!result.ok) {
        const error = result.data.error || 'Failed to complete enrollment';
        showError('enrollError', error);
        document.getElementById('startEnrollBtn').disabled = false;
        return;
    }
    
    // Show completion screen
    if (enrollmentState.stream) {
        stopStream(enrollmentState.stream);
    }
    
    showStep('step-result');
    const resultContent = document.getElementById('enrollResultContent');
    resultContent.innerHTML = `
        <h3 style="color: var(--success-color);">✓ Enrollment Complete!</h3>
        <p>Your face has been successfully enrolled.</p>
        <p><strong>User:</strong> ${result.data.user_id}</p>
        <p><strong>Samples:</strong> ${enrollmentState.collectedSamples} face samples registered</p>
        <p>You can now login using your face. Click the button below to go to login.</p>
    `;
    
    console.log('Enrollment completed successfully');
}

/**
 * Cancel enrollment
 */
async function handleEnrollmentCancel() {
    if (enrollmentState.stream) {
        stopStream(enrollmentState.stream);
    }
    
    enrollmentState.isCapturing = false;
    enrollmentState.sessionId = null;
    enrollmentState.collectedSamples = 0;
    
    showStep('step-credentials');
    document.getElementById('enrollmentForm').reset();
    hideError('enrollError');
    hideStatus('enrollStatus');
}

console.log('Enrollment script loaded');

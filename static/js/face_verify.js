// /**
//  * Face Verification Login Logic
//  * Handles two-step login: credentials -> face verification
//  */

// let verificationState = {
//     verifySessionId: null,
//     isCapturing: false,
//     stream: null,
//     uploadInProgress: false,
//     cancelled: false,
//     attemptCount: 0,
//     maxAttempts: 3
// };

// document.addEventListener('DOMContentLoaded', () => {
//     initializeLoginUI();
// });

// function initializeLoginUI() {
//     const loginForm = document.getElementById('loginForm');
//     const startCaptureBtn = document.getElementById('startCaptureBtn');
//     const cancelVerifyBtn = document.getElementById('cancelVerifyBtn');
//     const retryBtn = document.getElementById('retryBtn');
    
//     if (loginForm) {
//         loginForm.addEventListener('submit', handleLoginCredentials);
//     }
    
//     if (startCaptureBtn) {
//         startCaptureBtn.addEventListener('click', startFaceVerificationCapture);
//     }
    
//     if (cancelVerifyBtn) {
//         cancelVerifyBtn.addEventListener('click', handleVerificationCancel);
//     }
    
//     if (retryBtn) {
//         retryBtn.addEventListener('click', handleVerificationRetry);
//     }
// }

// /**
//  * Step 1: Verify credentials
//  */
// async function handleLoginCredentials(event) {
//     event.preventDefault();
    
//     const userId = document.getElementById('userId').value.trim();
//     const password = document.getElementById('password').value.trim();
    
//     if (!userId || !password) {
//         showError('credError', 'User ID and password are required.');
//         return;
//     }

//     hideError('credError');

//     // Call backend to verify credentials and start verification session
//     const result = await apiPost('/api/auth/login', {
//         user_id: userId,
//         password: password
//     });

//     if (!result.ok) {
//         const errMsg = (result.data && result.data.error) || 'Login failed.';
//         // If user is not yet enrolled, show helpful enroll link
//         if (result.status === 403 && errMsg.toLowerCase().includes('enroll')) {
//             const el = document.getElementById('credError');
//             if (el) {
//                 el.innerHTML = errMsg + ' <a href="/enroll" style="color:#2563eb;font-weight:600">Go to Enrollment →</a>';
//                 el.style.display = 'block';
//             }
//         } else {
//             showError('credError', errMsg);
//         }
//         return;
//     }
    
//     // Save session ID
//     verificationState.verifySessionId = result.data.verify_session_id;
//     verificationState.attemptCount = 0;

//     // Remember user ID for admin panel header
//     localStorage.setItem('user_id', userId);

//     // Move to webcam step
//     showStep('step-webcam');
    
//     // Initialize webcam
//     await initializeVerificationWebcam();
// }

// /**
//  * Initialize webcam for verification
//  */
// async function initializeVerificationWebcam() {
//     try {
//         const videoElement = document.getElementById('webcam');
//         if (!videoElement) return;
        
//         if (verificationState.stream) {
//             stopStream(verificationState.stream);
//         }
        
//         verificationState.stream = await getWebcamStream();
//         videoElement.srcObject = verificationState.stream;
        
//         // Wait for video to load
//         videoElement.onloadedmetadata = () => {
//             videoElement.play().catch(e => console.error('Play error:', e));
//         };
        
//         hideError('webcamError');
//         hideStatus('captureStatus');
        
//         console.log('Verification webcam initialized');
//     } catch (error) {
//         showError('webcamError', error.message);
//     }
// }

// /**
//  * Start face verification capture
//  * Captures ~1.5-2 seconds of video for face matching
//  */
// async function startFaceVerificationCapture() {
//     const startBtn = document.getElementById('startCaptureBtn');
//     const videoElement = document.getElementById('webcam');
//     const canvasElement = document.getElementById('captureCanvas');
//     const frameCounter = document.getElementById('frameCounter');
    
//     if (!videoElement.srcObject) {
//         showError('webcamError', 'Webcam not ready');
//         return;
//     }
    
//     const minFramesRequired = CONFIG.login_min_frames || 8;
//     const captureDuration = (CONFIG.login_capture_duration || 2) * 1000;
//     const fps = CONFIG.login_capture_fps || 15;
//     const frameDuration = 1000 / fps;
    
//     hideError('webcamError');
//     hideStatus('captureStatus');
    
//     if (verificationState.uploadInProgress) {
//         showStatus('captureStatus', 'Processing previous capture, please wait...');
//         return;
//     }
    
//     // Start counting frames
//     verificationState.isCapturing = true;
//     startBtn.disabled = true;
//     frameCounter.style.display = 'block';
    
//     const frames = [];
//     const startTime = Date.now();
//     let frameCount = 0;
//     let captureIndex = 0;  // total frames captured (including skipped)
//     console.log(`[TIMING] camera capture started`);
    
//     // Countdown with blink instruction - alternates to keep user's attention
//     const totalSeconds = Math.ceil(captureDuration / 1000);
//     let blinkPhase = true;
//     const captureStatusEl = document.getElementById('captureStatus');
//     const countdownInterval = setInterval(() => {
//         const elapsed = Date.now() - startTime;
//         const remaining = Math.ceil((captureDuration - elapsed) / 1000);
//         if (remaining > 0 && verificationState.isCapturing && captureStatusEl) {
//             blinkPhase = !blinkPhase;
//             captureStatusEl.style.display = 'block';
//             if (blinkPhase) {
//                 captureStatusEl.innerHTML =
//                     `<span style="font-size:16px;font-weight:bold;color:#e74c3c;">👁️ Blink once naturally</span> <span style="font-size:13px;color:#555;">(${remaining}s)</span>`;
//             } else {
//                 captureStatusEl.innerHTML = `📷 Look directly at the camera... (${remaining}s)`;
//             }
//         }
//     }, 400);
    
//     while (verificationState.isCapturing && Date.now() - startTime < captureDuration) {
//         captureIndex++;
//         // Send every 2nd frame to server — halves payload while keeping 7.5fps
//         // which is enough for blink detection (blinks last 300ms = 2+ frames at 7.5fps)
//         if (captureIndex % 2 === 0) {
//             try {
//                 const frameData = captureFrame(videoElement, canvasElement);
//                 frames.push(frameData);
//                 frameCount++;
//                 frameCounter.textContent = `Frames: ${frameCount}`;
//             } catch (e) {
//                 console.error('Frame capture error:', e);
//             }
//         }
        
//         await sleep(frameDuration);
//     }
    
//     console.log(`[TIMING] capture done: ${frameCount} frames sent in ${Date.now()-startTime}ms`);
    
//     clearInterval(countdownInterval);
//     verificationState.isCapturing = false;
//     frameCounter.style.display = 'none';
//     startBtn.disabled = false;
    
//     console.log(`Captured ${frameCount} frames in ${captureDuration}ms`);
    
//     // Stop here if cancelled before we even get to upload
//     if (verificationState.cancelled) {
//         showStatus('captureStatus', '');
//         return;
//     }

//     if (frames.length < minFramesRequired) {
//         showError('webcamError', 
//             `Insufficient frames: got ${frames.length}, need ${minFramesRequired}`);
//         showStatus('captureStatus', '');
//         return;
//     }
    
//     // Snapshot the session ID at the moment we start uploading.
//     // If cancel is pressed and user re-logs in, verifySessionId changes.
//     // When the old apiPost returns, session IDs won't match => result is discarded.
//     const uploadSessionId = verificationState.verifySessionId;
//     if (!uploadSessionId) {
//         // Session was cleared by cancel before we even started uploading
//         return;
//     }

//     // Upload frames for verification
//     verificationState.uploadInProgress = true;
//     showStatus('captureStatus', '🔍 Verifying...');
    
//     const t_verify = Date.now();
//     console.log(`[TIMING] verification started (${frames.length} frames)`);
    
//     const result = await apiPost('/api/auth/verify-face', {
//         frames: frames
//     });
    
//     console.log(`[TIMING] verification finished: ${Date.now() - t_verify}ms server time`);
//     console.log(`[TIMING] total from capture start: ${Date.now() - startTime}ms`);
//     verificationState.uploadInProgress = false;
    
//     // Discard result if the session changed (user cancelled and re-logged in)
//     if (verificationState.verifySessionId !== uploadSessionId) {
//         return;
//     }
    
//     if (!result.ok) {
//         verificationState.attemptCount++;
        
//         const error = result.data.error || 'Verification failed';
//         const shouldRetry = result.data.retry !== false;
//         const blinkDetected = result.data.blink_detected;
        
//         // Provide specific feedback for blink failure
//         let displayMessage = error;
//         if (blinkDetected === false) {
//             displayMessage = '👁️ No blink detected. Please blink naturally during verification to prove you\'re real (not a photo).';
//         }
        
//         // Show result
//         showVerificationResult(displayMessage, false, shouldRetry);
        
//         // Check if max attempts exceeded
//         if (verificationState.attemptCount >= verificationState.maxAttempts) {
//             showError('webcamError', `Maximum attempts (${verificationState.maxAttempts}) exceeded`);
//             document.getElementById('startCaptureBtn').disabled = true;
//         } else if (!shouldRetry) {
//             showError('webcamError', error);
//         }
        
//         return;
//     }
    
//     // Success!
//         // Face verification passed!
//     hideStatus('captureStatus');
    
//     // Check if server wants us to do a liveness challenge next
//     if (result.data.next_step === 'challenge') {
//         // Face matched — now do active liveness challenge
//         // Do NOT stop webcam stream — challenge needs it
//         console.log('Face verified. Starting liveness challenge...');
//         showStatus('captureStatus', '✓ Face matched! Starting liveness challenge...');
        
//         // Small delay so user sees the success message
//         setTimeout(() => {
//             hideStatus('captureStatus');
//             startChallenge();  // defined in login.html script block
//         }, 1000);
//         return;
//     }
    
//     // No challenge required (fallback for old flow)
//     const blinkOk = result.data.blink_confirmed;
//     const blinkLine = blinkOk
//         ? '<p style="color:var(--success-color);font-size:13px;">👁️ Blink confirmed ✓</p>'
//         : '';
//     showVerificationResult(result.data.message, true, false, blinkLine);
    
//     // Stop stream
//     if (verificationState.stream) {
//         stopStream(verificationState.stream);
//     }
    
//     // Redirect to dashboard after delay
//     setTimeout(() => {
//         window.location.href = '/dashboard';
//     }, 2000);

// /**
//  * Show verification result
//  */
// function showVerificationResult(message, success, canRetry, extraHtml = '') {
//     showStep('step-result');
//     const resultContent = document.getElementById('resultContent');
//     const retryBtn = document.getElementById('retryBtn');
    
//     if (success) {
//         resultContent.innerHTML = `
//             <h3 style="color: var(--success-color);">✓ Face Verified!</h3>
//             ${extraHtml}
//             <p>${message}</p>
//             <p>Redirecting to dashboard...</p>
//         `;
//         retryBtn.style.display = 'none';
//     } else {
//         const attemptNum = verificationState.attemptCount;
//         const maxAttempts = verificationState.maxAttempts;
        
//         resultContent.innerHTML = `
//             <h3 style="color: var(--warning-color);">✗ Verification Failed</h3>
//             <p>${message}</p>
//             <p style="font-size: 13px; color: #666;">Attempt ${attemptNum} of ${maxAttempts}</p>
//         `;
        
//         if (canRetry && attemptNum < maxAttempts) {
//             retryBtn.style.display = 'block';
//             resultContent.innerHTML += `<p style="font-size: 13px; margin-top: 10px;">
//                 <strong>Tips:</strong><br>
//                 • Ensure good lighting and keep your face clearly visible<br>
//                 • Look at the camera and <strong>blink once naturally</strong><br>
//                 • Don't use photos, videos, or screens
//             </p>`;
//         } else {
//             retryBtn.style.display = 'none';
//         }
//     }
// }

// /**
//  * Retry verification
//  */
// async function handleVerificationRetry() {
//     if (verificationState.stream && verificationState.stream.active) {
//         showStep('step-webcam');
//         return;
//     }
    
//     // Reinitialize webcam
//     showStep('step-webcam');
//     await initializeVerificationWebcam();
// }

// /**
//  * Cancel verification and go back to credentials
//  */
// async function handleVerificationCancel() {
//     if (verificationState.stream) {
//         stopStream(verificationState.stream);
//     }
    
//     // Stop challenge if it is running
//     if (typeof challengeHandler !== 'undefined' && challengeHandler) {
//         challengeHandler.stop();
//         challengeHandler = null;
//     }
    
//     // Hide challenge section if visible
//     var challengeSection = document.getElementById('challenge-section');
//     if (challengeSection) {
//         challengeSection.style.display = 'none';
//     }
    
//     // Clear the session ID immediately - this is the key guard that prevents
//     // an in-flight apiPost from completing after cancel
//     verificationState.cancelled = true;
//     verificationState.isCapturing = false;
//     verificationState.verifySessionId = null;
//     verificationState.uploadInProgress = false;
//     verificationState.attemptCount = 0;
    
//     showStep('step-credentials');
//     document.getElementById('loginForm').reset();
//     hideError('credentialsError');
//     hideError('webcamError');
//     hideStatus('captureStatus');
// }

// console.log('Face verification script loaded');


/**
 * Face Verification Login Logic
 * Handles two-step login: credentials -> face verification -> challenge
 */

let verificationState = {
    verifySessionId: null,
    isCapturing: false,
    stream: null,
    uploadInProgress: false,
    cancelled: false,
    attemptCount: 0,
    maxAttempts: 3
};

document.addEventListener('DOMContentLoaded', function() {
    initializeLoginUI();
});

function initializeLoginUI() {
    var loginForm = document.getElementById('loginForm');
    var startCaptureBtn = document.getElementById('startCaptureBtn');
    var cancelVerifyBtn = document.getElementById('cancelVerifyBtn');
    var retryBtn = document.getElementById('retryBtn');
    
    if (loginForm) {
        loginForm.addEventListener('submit', handleLoginCredentials);
    }
    
    if (startCaptureBtn) {
        startCaptureBtn.addEventListener('click', startFaceVerificationCapture);
    }
    
    if (cancelVerifyBtn) {
        cancelVerifyBtn.addEventListener('click', handleVerificationCancel);
    }
    
    if (retryBtn) {
        retryBtn.addEventListener('click', handleVerificationRetry);
    }
}

/**
 * Step 1: Verify credentials
 */
async function handleLoginCredentials(event) {
    event.preventDefault();
    
    var userId = document.getElementById('userId').value.trim();
    var password = document.getElementById('password').value.trim();
    
    if (!userId || !password) {
        showError('credError', 'User ID and password are required.');
        return;
    }

    hideError('credError');

    // Call backend to verify credentials and start verification session
    var result = await apiPost('/api/auth/login', {
        user_id: userId,
        password: password
    });

    if (!result.ok) {
        var errMsg = (result.data && result.data.error) || 'Login failed.';
        // If user is not yet enrolled, show helpful enroll link
        if (result.status === 403 && errMsg.toLowerCase().includes('enroll')) {
            var el = document.getElementById('credError');
            if (el) {
                el.innerHTML = errMsg + ' <a href="/enroll" style="color:#2563eb;font-weight:600">Go to Enrollment →</a>';
                el.style.display = 'block';
            }
        } else {
            showError('credError', errMsg);
        }
        return;
    }

    // Password-only path: admin has disabled biometric requirement for this user.
    if (result.data && result.data.password_only) {
        localStorage.setItem('user_id', userId);
        window.location.href = result.data.redirect || '/dashboard';
        return;
    }
    
    // Save session ID
    verificationState.verifySessionId = result.data.verify_session_id;
    verificationState.attemptCount = 0;

    // Remember user ID for admin panel header
    localStorage.setItem('user_id', userId);

    // Move to webcam step
    showStep('step-webcam');
    
    // Initialize webcam
    await initializeVerificationWebcam();
}

/**
 * Initialize webcam for verification
 */
async function initializeVerificationWebcam() {
    try {
        var videoElement = document.getElementById('webcam');
        if (!videoElement) return;
        
        if (verificationState.stream) {
            stopStream(verificationState.stream);
        }
        
        verificationState.stream = await getWebcamStream();
        videoElement.srcObject = verificationState.stream;
        
        // Wait for video to load
        videoElement.onloadedmetadata = function() {
            videoElement.play().catch(function(e) { console.error('Play error:', e); });
        };
        
        hideError('webcamError');
        hideStatus('captureStatus');
        
        console.log('Verification webcam initialized');
    } catch (error) {
        showError('webcamError', error.message);
    }
}

/**
 * Start face verification capture
 * Captures ~1.5-2 seconds of video for face matching
 */
async function startFaceVerificationCapture() {
    var startBtn = document.getElementById('startCaptureBtn');
    var videoElement = document.getElementById('webcam');
    var canvasElement = document.getElementById('captureCanvas');
    var frameCounter = document.getElementById('frameCounter');
    
    if (!videoElement.srcObject) {
        showError('webcamError', 'Webcam not ready');
        return;
    }
    
    var minFramesRequired = CONFIG.login_min_frames || 8;
    var captureDuration = (CONFIG.login_capture_duration || 2) * 1000;
    var fps = CONFIG.login_capture_fps || 15;
    var frameDuration = 1000 / fps;
    
    hideError('webcamError');
    hideStatus('captureStatus');
    
    if (verificationState.uploadInProgress) {
        showStatus('captureStatus', 'Processing previous capture, please wait...');
        return;
    }
    
    // Start counting frames
    verificationState.isCapturing = true;
    startBtn.disabled = true;
    frameCounter.style.display = 'block';
    
    var frames = [];
    var startTime = Date.now();
    var frameCount = 0;
    var captureIndex = 0;
    console.log('[TIMING] camera capture started');
    
    // Countdown with blink instruction
    var totalSeconds = Math.ceil(captureDuration / 1000);
    var blinkPhase = true;
    var captureStatusEl = document.getElementById('captureStatus');
    var countdownInterval = setInterval(function() {
        var elapsed = Date.now() - startTime;
        var remaining = Math.ceil((captureDuration - elapsed) / 1000);
        if (remaining > 0 && verificationState.isCapturing && captureStatusEl) {
            blinkPhase = !blinkPhase;
            captureStatusEl.style.display = 'block';
            if (blinkPhase) {
                captureStatusEl.innerHTML =
                    '<span style="font-size:16px;font-weight:bold;color:#e74c3c;">👁️ Blink once naturally</span> <span style="font-size:13px;color:#555;">(' + remaining + 's)</span>';
            } else {
                captureStatusEl.innerHTML = '📷 Look directly at the camera... (' + remaining + 's)';
            }
        }
    }, 400);
    
    while (verificationState.isCapturing && Date.now() - startTime < captureDuration) {
        captureIndex++;
        if (captureIndex % 2 === 0) {
            try {
                var frameData = captureFrame(videoElement, canvasElement);
                frames.push(frameData);
                frameCount++;
                frameCounter.textContent = 'Frames: ' + frameCount;
            } catch (e) {
                console.error('Frame capture error:', e);
            }
        }
        
        await sleep(frameDuration);
    }
    
    console.log('[TIMING] capture done: ' + frameCount + ' frames sent in ' + (Date.now() - startTime) + 'ms');
    
    clearInterval(countdownInterval);
    verificationState.isCapturing = false;
    frameCounter.style.display = 'none';
    startBtn.disabled = false;
    
    console.log('Captured ' + frameCount + ' frames in ' + captureDuration + 'ms');
    
    // Stop here if cancelled before upload
    if (verificationState.cancelled) {
        showStatus('captureStatus', '');
        return;
    }

    if (frames.length < minFramesRequired) {
        showError('webcamError', 
            'Insufficient frames: got ' + frames.length + ', need ' + minFramesRequired);
        showStatus('captureStatus', '');
        return;
    }
    
    // Snapshot the session ID at the moment we start uploading
    var uploadSessionId = verificationState.verifySessionId;
    if (!uploadSessionId) {
        return;
    }

    // Upload frames for verification
    verificationState.uploadInProgress = true;
    showStatus('captureStatus', '🔍 Verifying...');
    
    var t_verify = Date.now();
    console.log('[TIMING] verification started (' + frames.length + ' frames)');
    
    var result = await apiPost('/api/auth/verify-face', {
        frames: frames
    });
    
    console.log('[TIMING] verification finished: ' + (Date.now() - t_verify) + 'ms server time');
    console.log('[TIMING] total from capture start: ' + (Date.now() - startTime) + 'ms');
    verificationState.uploadInProgress = false;
    
    // Discard result if the session changed (user cancelled and re-logged in)
    if (verificationState.verifySessionId !== uploadSessionId) {
        return;
    }
    
    if (!result.ok) {
        verificationState.attemptCount++;
        
        var error = result.data.error || 'Verification failed';
        var shouldRetry = result.data.retry !== false;
        var blinkDetected = result.data.blink_detected;
        
        // Provide specific feedback for blink failure
        var displayMessage = error;
        if (blinkDetected === false) {
            displayMessage = '👁️ No blink detected. Please blink naturally during verification to prove you\'re real (not a photo).';
        }
        
        // Show result
        showVerificationResult(displayMessage, false, shouldRetry);
        
        // Check if max attempts exceeded
        if (verificationState.attemptCount >= verificationState.maxAttempts) {
            showError('webcamError', 'Maximum attempts (' + verificationState.maxAttempts + ') exceeded');
            document.getElementById('startCaptureBtn').disabled = true;
        } else if (!shouldRetry) {
            showError('webcamError', error);
        }
        
        return;
    }
    
    // ══════════════════════════════════════════════════════
    // FACE VERIFICATION PASSED — Check what's next
    // ══════════════════════════════════════════════════════
    
    hideStatus('captureStatus');
    
    // Check if server wants us to do a liveness challenge next
    if (result.data.next_step === 'challenge') {
        // Face matched — now do active liveness challenge
        // Do NOT stop webcam stream — challenge needs it
        console.log('Face verified. Starting liveness challenge...');
        showStatus('captureStatus', '✓ Face matched! Starting liveness challenge...');
        
        // Small delay so user sees the success message
        setTimeout(function() {
            hideStatus('captureStatus');
            startChallenge();  // defined in login.html script block
        }, 1000);
        return;
    }
    
    // No challenge required (fallback for old flow)
    var blinkOk = result.data.blink_confirmed;
    var blinkLine = blinkOk
        ? '<p style="color:var(--success-color);font-size:13px;">👁️ Blink confirmed ✓</p>'
        : '';
    showVerificationResult(result.data.message, true, false, blinkLine);
    
    // Stop stream
    if (verificationState.stream) {
        stopStream(verificationState.stream);
    }
    
    // Redirect to dashboard after delay
    setTimeout(function() {
        window.location.href = '/dashboard';
    }, 2000);
}

/**
 * Show verification result
 */
function showVerificationResult(message, success, canRetry, extraHtml) {
    if (typeof extraHtml === 'undefined') {
        extraHtml = '';
    }
    
    showStep('step-result');
    var resultContent = document.getElementById('resultContent');
    var retryBtn = document.getElementById('retryBtn');
    
    if (success) {
        resultContent.innerHTML = 
            '<h3 style="color: var(--success-color);">✓ Face Verified!</h3>' +
            extraHtml +
            '<p>' + message + '</p>' +
            '<p>Redirecting to dashboard...</p>';
        retryBtn.style.display = 'none';
    } else {
        var attemptNum = verificationState.attemptCount;
        var maxAttempts = verificationState.maxAttempts;
        
        resultContent.innerHTML = 
            '<h3 style="color: var(--warning-color);">✗ Verification Failed</h3>' +
            '<p>' + message + '</p>' +
            '<p style="font-size: 13px; color: #666;">Attempt ' + attemptNum + ' of ' + maxAttempts + '</p>';
        
        if (canRetry && attemptNum < maxAttempts) {
            retryBtn.style.display = 'block';
            resultContent.innerHTML += '<p style="font-size: 13px; margin-top: 10px;">' +
                '<strong>Tips:</strong><br>' +
                '• Ensure good lighting and keep your face clearly visible<br>' +
                '• Look at the camera and <strong>blink once naturally</strong><br>' +
                '• Don\'t use photos, videos, or screens' +
                '</p>';
        } else {
            retryBtn.style.display = 'none';
        }
    }
}

/**
 * Retry verification
 */
async function handleVerificationRetry() {
    if (verificationState.stream && verificationState.stream.active) {
        showStep('step-webcam');
        return;
    }
    
    // Reinitialize webcam
    showStep('step-webcam');
    await initializeVerificationWebcam();
}

/**
 * Cancel verification and go back to credentials
 */
async function handleVerificationCancel() {
    if (verificationState.stream) {
        stopStream(verificationState.stream);
    }
    
    // Stop challenge if it is running
    if (typeof challengeHandler !== 'undefined' && challengeHandler) {
        challengeHandler.stop();
        challengeHandler = null;
    }
    
    // Hide challenge section if visible
    var challengeSection = document.getElementById('challenge-section');
    if (challengeSection) {
        challengeSection.style.display = 'none';
    }
    
    // Clear the session ID immediately - this is the key guard that prevents
    // an in-flight apiPost from completing after cancel
    verificationState.cancelled = true;
    verificationState.isCapturing = false;
    verificationState.verifySessionId = null;
    verificationState.uploadInProgress = false;
    verificationState.attemptCount = 0;
    
    showStep('step-credentials');
    document.getElementById('loginForm').reset();
    hideError('credentialsError');
    hideError('webcamError');
    hideStatus('captureStatus');
}

console.log('Face verification script loaded');
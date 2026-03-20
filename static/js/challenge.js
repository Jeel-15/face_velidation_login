class LivenessChallenge {

    constructor(videoElement, callbacks) {
        this.video = videoElement;
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');

        // Callbacks
        this.onPass = (callbacks && callbacks.onPass) ? callbacks.onPass : function() {};
        this.onFail = (callbacks && callbacks.onFail) ? callbacks.onFail : function() {};
        this.onStatus = (callbacks && callbacks.onStatus) ? callbacks.onStatus : function() {};

        // State
        this.challenge = null;
        this.token = null;
        this.running = false;
        this.sending = false;

        // Timers
        this._frameTimer = null;
        this._tickTimer = null;
        this._remaining = 0;

        // Performance tracking
        this._framesSent = 0;
        this._startTime = 0;
        this._lastLatency = 0;

        // ── Identity tracking ────────────────────────────────────
        this._identityInfo = null;    // latest identity check result from server
        this._identityFails = 0;      // consecutive face_mismatch count

        // Optimized settings
        this.FPS = 4;              // 4 frames per second (reliable, no queue buildup)
        this.MAX_WIDTH = 420;      // Balance: big enough for face detection, small enough for speed
        this.JPEG_QUALITY = 0.65;  // Lower quality = smaller payload = faster upload
    }

    /**
     * Start the challenge flow.
     */
    async start() {
        this.onStatus({
            phase: 'requesting',
            message: 'Getting challenge...'
        });

        this._framesSent = 0;
        this._startTime = Date.now();
        this._identityInfo = null;
        this._identityFails = 0;

        var success = await this._requestChallenge();
        if (!success) {
            return;
        }

        this._showChallenge();
        this._startStreaming();
        this._startCountdown();
    }

    /**
     * Stop everything.
     */
    stop() {
        this.running = false;
        if (this._frameTimer) {
            clearInterval(this._frameTimer);
            this._frameTimer = null;
        }
        if (this._tickTimer) {
            clearInterval(this._tickTimer);
            this._tickTimer = null;
        }
    }

    /**
     * Retry the challenge (request a new one).
     */
    retry() {
        this.stop();
        this.start();
    }

    /**
     * Request a challenge from the server.
     */
    async _requestChallenge() {
        try {
            var resp = await fetch('/api/get_challenge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin'
            });

            var data = await resp.json();

            if (!data.success) {
                this.onFail(data.error || 'Could not get challenge.');
                return false;
            }

            this.challenge = data.challenge;
            this.token = data.challenge.token;
            this._remaining = data.challenge.timeout;
            return true;

        } catch (err) {
            this.onFail('Network error: ' + err.message);
            return false;
        }
    }

    /**
     * Tell the UI to show the challenge instruction.
     */
    _showChallenge() {
        this.onStatus({
            phase: 'challenge_start',
            type: this.challenge.type,
            instruction: this.challenge.instruction,
            detail: this.challenge.detail || '',
            icon: this.challenge.icon,
            timeout: this.challenge.timeout,
            remaining: this._remaining
        });
    }

    /**
     * Start capturing and sending frames.
     */
    _startStreaming() {
        this.running = true;
        var self = this;
        this._frameTimer = setInterval(function() {
            self._captureAndSend();
        }, 1000 / this.FPS);
    }

    /**
     * Capture one frame and send it to the server.
     * Optimized: skips if previous frame still being processed.
     */
    async _captureAndSend() {
        // CRITICAL: Skip if previous frame still processing
        // This prevents request queue buildup which causes lag
        if (!this.running || this.sending) {
            return;
        }
        this.sending = true;

        try {
            var vw = this.video.videoWidth;
            var vh = this.video.videoHeight;

            if (vw === 0 || vh === 0) {
                this.sending = false;
                return;
            }

            // Resize frame for speed
            var scale = Math.min(this.MAX_WIDTH / vw, 1);
            this.canvas.width = Math.round(vw * scale);
            this.canvas.height = Math.round(vh * scale);
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

            // Lower JPEG quality = smaller payload = faster upload
            var frameData = this.canvas.toDataURL('image/jpeg', this.JPEG_QUALITY);

            // Track latency
            var sendTime = Date.now();

            // Send to server
            var resp = await fetch('/api/verify_challenge_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    frame: frameData,
                    token: this.token
                })
            });

            var result = await resp.json();

            // Track performance
            this._lastLatency = Date.now() - sendTime;
            this._framesSent++;

            // ── Track identity info from server ──────────────────
            if (result.identity) {
                this._identityInfo = result.identity;
            }

            // Handle results
            if (result.status === 'passed') {
                this.stop();
                this.onPass(result);
                return;
            }

            if (result.status === 'expired') {
                this.stop();
                this.onFail('No worries! Let\'s try again. Click Retry below.');
                return;
            }

            // ── Handle: FACE MISMATCH ────────────────────────────
            // Two types:
            //   1. Identity failure (terminal) — wrong person, session killed
            //   2. Transient detection issue — just a warning, keep going
            if (result.status === 'face_mismatch') {
                var msg = (result.message || '').toLowerCase();
                var isIdentityFailure = msg.includes('identity') || msg.includes('enrolled');

                if (isIdentityFailure) {
                    // ── Terminal: wrong person detected ───────────
                    this.stop();
                    this.onFail(result.message);
                    return;
                }

                // ── Transient: face detection hiccup ─────────────
                this._identityFails++;

                // If too many transient mismatches, something is wrong
                if (this._identityFails >= 10) {
                    this.stop();
                    this.onFail('Face could not be verified. Please try again.');
                    return;
                }

                this.onStatus({
                    phase: 'warning',
                    message: result.message,
                    progress: 0,
                    identity: this._identityInfo
                });
                return;
            }

            // ── Handle: Session expired (403) ────────────────────
            if (resp.status === 403) {
                this.stop();
                this.onFail(result.error || 'Session expired. Please login again.');
                return;
            }

            if (!result.success && result.error) {
                // Don't stop on server errors — just log and continue
                console.warn('Challenge frame error:', result.error);
                return;
            }

            // ── Reset consecutive fail counter on good frame ─────
            this._identityFails = 0;

            // Progress update — smooth UI
            this.onStatus({
                phase: 'verifying',
                status: result.status,
                message: result.message,
                progress: result.progress || 0,
                remaining: result.remaining,
                identity: this._identityInfo
            });

        } catch (err) {
            // Network error — don't stop, server might be briefly slow
            console.error('Challenge frame network error:', err);
        } finally {
            this.sending = false;
        }
    }

    /**
     * Start the countdown timer.
     */
    _startCountdown() {
        var self = this;
        this._tickTimer = setInterval(function() {
            self._remaining = Math.max(0, self._remaining - 1);

            self.onStatus({
                phase: 'tick',
                remaining: self._remaining,
                identity: self._identityInfo
            });

            if (self._remaining <= 0) {
                self.stop();
                self.onFail('No worries! Let\'s try again. Click Retry below.');
            }
        }, 1000);
    }
}

// /**
//  * challenge.js - Active Liveness Challenge Frontend
//  * 
//  * Handles:
//  * 1. Requesting a random challenge from the server
//  * 2. Displaying the instruction to the user
//  * 3. Streaming webcam frames to the server for verification
//  * 4. Showing progress, timer, and results
//  */

// class LivenessChallenge {

//     constructor(videoElement, callbacks) {
//         this.video = videoElement;
//         this.canvas = document.createElement('canvas');
//         this.ctx = this.canvas.getContext('2d');

//         // Callbacks
//         this.onPass = (callbacks && callbacks.onPass) ? callbacks.onPass : function() {};
//         this.onFail = (callbacks && callbacks.onFail) ? callbacks.onFail : function() {};
//         this.onStatus = (callbacks && callbacks.onStatus) ? callbacks.onStatus : function() {};

//         // State
//         this.challenge = null;
//         this.token = null;
//         this.running = false;
//         this.sending = false;

//         // Timers
//         this._frameTimer = null;
//         this._tickTimer = null;
//         this._remaining = 0;

//         // Settings
//         this.FPS = 4;
//         this.MAX_WIDTH = 480;
//     }

//     /**
//      * Start the challenge flow.
//      * Call this after blink detection passes.
//      */
//     async start() {
//         this.onStatus({
//             phase: 'requesting',
//             message: 'Getting challenge...'
//         });

//         var success = await this._requestChallenge();
//         if (!success) {
//             return;
//         }

//         this._showChallenge();
//         this._startStreaming();
//         this._startCountdown();
//     }

//     /**
//      * Stop everything.
//      */
//     stop() {
//         this.running = false;
//         if (this._frameTimer) {
//             clearInterval(this._frameTimer);
//             this._frameTimer = null;
//         }
//         if (this._tickTimer) {
//             clearInterval(this._tickTimer);
//             this._tickTimer = null;
//         }
//     }

//     /**
//      * Retry the challenge (request a new one).
//      */
//     retry() {
//         this.stop();
//         this.start();
//     }

//     /**
//      * Request a challenge from the server.
//      */
//     async _requestChallenge() {
//         try {
//             var resp = await fetch('/api/get_challenge', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 credentials: 'same-origin'
//             });

//             var data = await resp.json();

//             if (!data.success) {
//                 this.onFail(data.error || 'Could not get challenge.');
//                 return false;
//             }

//             this.challenge = data.challenge;
//             this.token = data.challenge.token;
//             this._remaining = data.challenge.timeout;
//             return true;

//         } catch (err) {
//             this.onFail('Network error: ' + err.message);
//             return false;
//         }
//     }

//     /**
//      * Tell the UI to show the challenge instruction.
//      */
//     _showChallenge() {
//         this.onStatus({
//             phase: 'challenge_start',
//             type: this.challenge.type,
//             instruction: this.challenge.instruction,
//             detail: this.challenge.detail || '',
//             icon: this.challenge.icon,
//             timeout: this.challenge.timeout,
//             remaining: this._remaining
//         });
//     }

//     /**
//      * Start capturing and sending frames.
//      */
//     _startStreaming() {
//         this.running = true;
//         var self = this;
//         this._frameTimer = setInterval(function() {
//             self._captureAndSend();
//         }, 1000 / this.FPS);
//     }

//     /**
//      * Capture one frame and send it to the server.
//      */
//     async _captureAndSend() {
//         if (!this.running || this.sending) {
//             return;
//         }
//         this.sending = true;

//         try {
//             var vw = this.video.videoWidth;
//             var vh = this.video.videoHeight;

//             if (vw === 0 || vh === 0) {
//                 this.sending = false;
//                 return;
//             }

//             // Resize for speed
//             var scale = Math.min(this.MAX_WIDTH / vw, 1);
//             this.canvas.width = Math.round(vw * scale);
//             this.canvas.height = Math.round(vh * scale);
//             this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

//             var frameData = this.canvas.toDataURL('image/jpeg', 0.75);

//             // Send to server
//             var resp = await fetch('/api/verify_challenge_frame', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 credentials: 'same-origin',
//                 body: JSON.stringify({
//                     frame: frameData,
//                     token: this.token
//                 })
//             });

//             var result = await resp.json();

//             // Handle results
//             if (result.status === 'passed') {
//                 this.stop();
//                 this.onPass(result);
//                 return;
//             }

//             if (result.status === 'expired') {
//                 this.stop();
//                 this.onFail('Challenge timed out. Click Retry.');
//                 return;
//             }

//             if (result.status === 'face_mismatch') {
//                 this.onStatus({
//                     phase: 'warning',
//                     message: result.message,
//                     progress: 0
//                 });
//                 return;
//             }

//             if (!result.success && result.error) {
//                 this.stop();
//                 this.onFail(result.error);
//                 return;
//             }

//             // Progress update
//             this.onStatus({
//                 phase: 'verifying',
//                 status: result.status,
//                 message: result.message,
//                 progress: result.progress || 0,
//                 remaining: result.remaining
//             });

//         } catch (err) {
//             console.error('Challenge frame error:', err);
//         } finally {
//             this.sending = false;
//         }
//     }

//     /**
//      * Start the countdown timer.
//      */
//     _startCountdown() {
//         var self = this;
//         this._tickTimer = setInterval(function() {
//             self._remaining = Math.max(0, self._remaining - 1);

//             self.onStatus({
//                 phase: 'tick',
//                 remaining: self._remaining
//             });

//             if (self._remaining <= 0) {
//                 self.stop();
//                 self.onFail('Challenge timed out. Click Retry.');
//             }
//         }, 1000);
//     }
// }

/**
 * challenge.js - Active Liveness Challenge Frontend (Optimized)
 * 
 * Smooth, lag-free challenge handling with visual feedback.
 * 
 * Optimizations:
 * - Skips sending if previous frame still processing (no queue buildup)
 * - Smaller frame size + lower JPEG quality = faster upload
 * - Friendly timeout messages
 * - Smooth progress updates
 */

// class LivenessChallenge {

//     constructor(videoElement, callbacks) {
//         this.video = videoElement;
//         this.canvas = document.createElement('canvas');
//         this.ctx = this.canvas.getContext('2d');

//         // Callbacks
//         this.onPass = (callbacks && callbacks.onPass) ? callbacks.onPass : function() {};
//         this.onFail = (callbacks && callbacks.onFail) ? callbacks.onFail : function() {};
//         this.onStatus = (callbacks && callbacks.onStatus) ? callbacks.onStatus : function() {};

//         // State
//         this.challenge = null;
//         this.token = null;
//         this.running = false;
//         this.sending = false;

//         // Timers
//         this._frameTimer = null;
//         this._tickTimer = null;
//         this._remaining = 0;

//         // Performance tracking
//         this._framesSent = 0;
//         this._startTime = 0;
//         this._lastLatency = 0;

//         // Optimized settings
//         this.FPS = 4;              // 4 frames per second (reliable, no queue buildup)
//         this.MAX_WIDTH = 420;      // Balance: big enough for face detection, small enough for speed
//         this.JPEG_QUALITY = 0.65;  // Lower quality = smaller payload = faster upload
//     }

//     /**
//      * Start the challenge flow.
//      */
//     async start() {
//         this.onStatus({
//             phase: 'requesting',
//             message: 'Getting challenge...'
//         });

//         this._framesSent = 0;
//         this._startTime = Date.now();

//         var success = await this._requestChallenge();
//         if (!success) {
//             return;
//         }

//         this._showChallenge();
//         this._startStreaming();
//         this._startCountdown();
//     }

//     /**
//      * Stop everything.
//      */
//     stop() {
//         this.running = false;
//         if (this._frameTimer) {
//             clearInterval(this._frameTimer);
//             this._frameTimer = null;
//         }
//         if (this._tickTimer) {
//             clearInterval(this._tickTimer);
//             this._tickTimer = null;
//         }
//     }

//     /**
//      * Retry the challenge (request a new one).
//      */
//     retry() {
//         this.stop();
//         this.start();
//     }

//     /**
//      * Request a challenge from the server.
//      */
//     async _requestChallenge() {
//         try {
//             var resp = await fetch('/api/get_challenge', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 credentials: 'same-origin'
//             });

//             var data = await resp.json();

//             if (!data.success) {
//                 this.onFail(data.error || 'Could not get challenge.');
//                 return false;
//             }

//             this.challenge = data.challenge;
//             this.token = data.challenge.token;
//             this._remaining = data.challenge.timeout;
//             return true;

//         } catch (err) {
//             this.onFail('Network error: ' + err.message);
//             return false;
//         }
//     }

//     /**
//      * Tell the UI to show the challenge instruction.
//      */
//     _showChallenge() {
//         this.onStatus({
//             phase: 'challenge_start',
//             type: this.challenge.type,
//             instruction: this.challenge.instruction,
//             detail: this.challenge.detail || '',
//             icon: this.challenge.icon,
//             timeout: this.challenge.timeout,
//             remaining: this._remaining
//         });
//     }

//     /**
//      * Start capturing and sending frames.
//      */
//     _startStreaming() {
//         this.running = true;
//         var self = this;
//         this._frameTimer = setInterval(function() {
//             self._captureAndSend();
//         }, 1000 / this.FPS);
//     }

//     /**
//      * Capture one frame and send it to the server.
//      * Optimized: skips if previous frame still being processed.
//      */
//     async _captureAndSend() {
//         // CRITICAL: Skip if previous frame still processing
//         // This prevents request queue buildup which causes lag
//         if (!this.running || this.sending) {
//             return;
//         }
//         this.sending = true;

//         try {
//             var vw = this.video.videoWidth;
//             var vh = this.video.videoHeight;

//             if (vw === 0 || vh === 0) {
//                 this.sending = false;
//                 return;
//             }

//             // Resize frame for speed
//             var scale = Math.min(this.MAX_WIDTH / vw, 1);
//             this.canvas.width = Math.round(vw * scale);
//             this.canvas.height = Math.round(vh * scale);
//             this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

//             // Lower JPEG quality = smaller payload = faster upload
//             var frameData = this.canvas.toDataURL('image/jpeg', this.JPEG_QUALITY);

//             // Track latency
//             var sendTime = Date.now();

//             // Send to server
//             var resp = await fetch('/api/verify_challenge_frame', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 credentials: 'same-origin',
//                 body: JSON.stringify({
//                     frame: frameData,
//                     token: this.token
//                 })
//             });

//             var result = await resp.json();

//             // Track performance
//             this._lastLatency = Date.now() - sendTime;
//             this._framesSent++;

//             // Handle results
//             if (result.status === 'passed') {
//                 this.stop();
//                 this.onPass(result);
//                 return;
//             }

//             if (result.status === 'expired') {
//                 this.stop();
//                 this.onFail('No worries! Let\'s try again. Click Retry below.');
//                 return;
//             }

//             if (result.status === 'face_mismatch') {
//                 this.onStatus({
//                     phase: 'warning',
//                     message: result.message,
//                     progress: 0
//                 });
//                 return;
//             }

//             if (!result.success && result.error) {
//                 // Don't stop on server errors — just log and continue
//                 // The server might recover on the next frame
//                 console.warn('Challenge frame error:', result.error);
//                 return;
//             }

//             // Progress update — smooth UI
//             this.onStatus({
//                 phase: 'verifying',
//                 status: result.status,
//                 message: result.message,
//                 progress: result.progress || 0,
//                 remaining: result.remaining
//             });

//         } catch (err) {
//             // Network error — don't stop, server might be briefly slow
//             console.error('Challenge frame network error:', err);
//         } finally {
//             this.sending = false;
//         }
//     }

//     /**
//      * Start the countdown timer.
//      */
//     _startCountdown() {
//         var self = this;
//         this._tickTimer = setInterval(function() {
//             self._remaining = Math.max(0, self._remaining - 1);

//             self.onStatus({
//                 phase: 'tick',
//                 remaining: self._remaining
//             });

//             if (self._remaining <= 0) {
//                 self.stop();
//                 self.onFail('No worries! Let\'s try again. Click Retry below.');
//             }
//         }, 1000);
//     }
// }
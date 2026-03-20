"""
test_challenge.py — Standalone Challenge Testing Server

Run this INSTEAD of app.py to test challenges directly:
    python test_challenge.py

Open: http://localhost:5001/test

Features:
- Pick any challenge type or use random
- See real-time debug metrics (ratios, EAR, state)
- No login/password/blink required
- Visual landmark overlay info
"""

import os
import sys
import base64
import time
import logging

import cv2
import numpy as np
from flask import Flask, render_template_string, request, jsonify, session

from challenge import ChallengeManager
from config import CHALLENGE_CONFIG

# ── App setup ──
app = Flask(__name__)
app.secret_key = 'test-challenge-secret-key-12345'

# ── Logging ──
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ── Challenge manager with debug ON ──
test_config = {**CHALLENGE_CONFIG}
test_config['debug'] = True          # always show debug metrics
test_config['timeout_seconds'] = 12  # more time for testing
challenge_manager = ChallengeManager(config=test_config)


# ── Helper ──
def decode_frame(data_url):
    """Decode base64 data URL to RGB numpy array."""
    try:
        if ',' in data_url:
            data_url = data_url.split(',')[1]
        img_bytes = base64.b64decode(data_url)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except Exception as e:
        logger.error(f"Frame decode error: {e}")
        return None


# ══════════════════════════════════════════════════════════
#  TEST PAGE
# ══════════════════════════════════════════════════════════

TEST_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Challenge Test — Debug Mode</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
        }

        h1 {
            font-size: 24px;
            margin-bottom: 6px;
            color: #38bdf8;
        }

        .subtitle {
            font-size: 13px;
            color: #64748b;
            margin-bottom: 24px;
        }

        /* ── Layout ── */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        @media (max-width: 700px) {
            .main-grid { grid-template-columns: 1fr; }
        }

        /* ── Cards ── */
        .card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
        }

        .card h2 {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #38bdf8;
            margin-bottom: 14px;
            font-family: 'JetBrains Mono', monospace;
        }

        /* ── Webcam ── */
        .webcam-wrap {
            position: relative;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            aspect-ratio: 4/3;
            margin-bottom: 16px;
        }

                .webcam-wrap video {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transform: scaleX(-1);
        }

        /* Face oval guide */
        .webcam-wrap .face-guide {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            pointer-events: none;
            z-index: 2;
        }

        .webcam-wrap .face-guide svg ellipse {
            stroke: rgba(56, 189, 248, 0.7);
            stroke-width: 2.5;
            stroke-dasharray: 10 5;
            fill: none;
            animation: ovalPulse 2s ease-in-out infinite;
        }

        @keyframes ovalPulse {
            0%, 100% { stroke-opacity: 0.5; }
            50%      { stroke-opacity: 1; }
        }

        .webcam-wrap .face-guide-label {
            margin-top: 6px;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.04em;
            color: rgba(56, 189, 248, 0.85);
            background: rgba(0, 0, 0, 0.5);
            padding: 3px 10px;
            border-radius: 99px;
            backdrop-filter: blur(4px);
        }

        /* Scan line */
        .webcam-wrap .scan-line {
            position: absolute;
            left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, #38bdf8, rgba(56,189,248,0.9), #38bdf8, transparent);
            box-shadow: 0 0 12px #38bdf8;
            animation: scanMove 3s ease-in-out infinite;
            pointer-events: none;
            z-index: 3;
        }

        @keyframes scanMove {
            0%   { top: 5%; }
            50%  { top: 92%; }
            100% { top: 5%; }
        }

        /* Corner brackets */
        .webcam-wrap .scan-corners {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 4;
        }

        .webcam-wrap .scan-corners::before,
        .webcam-wrap .scan-corners::after,
        .webcam-wrap .scan-corners span::before,
        .webcam-wrap .scan-corners span::after {
            content: '';
            position: absolute;
            width: 18px; height: 18px;
            border-color: #38bdf8;
            border-style: solid;
            opacity: 0.7;
            animation: cornerBright 1.4s ease-in-out infinite alternate;
        }

        .webcam-wrap .scan-corners::before  { top:8px; left:8px;   border-width:2px 0 0 2px; }
        .webcam-wrap .scan-corners::after   { top:8px; right:8px;  border-width:2px 2px 0 0; }
        .webcam-wrap .scan-corners span::before { bottom:8px; left:8px;  border-width:0 0 2px 2px; }
        .webcam-wrap .scan-corners span::after  { bottom:8px; right:8px; border-width:0 2px 2px 0; }

        @keyframes cornerBright {
            from { opacity: 0.4; }
            to   { opacity: 1; box-shadow: 0 0 8px #38bdf8; }
        }

        /* ── Challenge buttons ── */
        .challenge-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 16px;
        }

        .challenge-buttons button {
            padding: 10px 12px;
            border: 1.5px solid #334155;
            border-radius: 8px;
            background: #0f172a;
            color: #e2e8f0;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }

        .challenge-buttons button:hover {
            border-color: #38bdf8;
            background: #1e293b;
            color: #38bdf8;
        }

        .challenge-buttons button.active {
            border-color: #38bdf8;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }

        .challenge-buttons button.random-btn {
            grid-column: 1 / -1;
            background: linear-gradient(135deg, #1e40af, #0891b2);
            border-color: #0891b2;
            color: #fff;
        }

        .challenge-buttons button.random-btn:hover {
            filter: brightness(1.15);
        }

        /* ── Action buttons ── */
        .action-buttons {
            display: flex;
            gap: 10px;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            flex: 1;
            transition: all 0.2s;
        }

        .btn-start {
            background: linear-gradient(135deg, #059669, #10b981);
            color: #fff;
        }

        .btn-start:hover { filter: brightness(1.1); }

        .btn-stop {
            background: #dc2626;
            color: #fff;
        }

        .btn-stop:hover { filter: brightness(1.1); }

        .btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }

        /* ── Challenge display ── */
        .challenge-display {
            background: #0f172a;
            border: 2px solid #334155;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin-bottom: 16px;
            min-height: 140px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            transition: border-color 0.3s, box-shadow 0.3s;
        }

        .challenge-display.detecting {
            border-color: #eab308;
            box-shadow: 0 0 20px rgba(234, 179, 8, 0.2);
        }

        .challenge-display.passed {
            border-color: #22c55e;
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.2);
        }

        .challenge-display.failed {
            border-color: #ef4444;
        }

        .challenge-icon {
            font-size: 44px;
            margin-bottom: 8px;
        }

        .challenge-instruction {
            font-size: 18px;
            font-weight: 700;
            color: #f1f5f9;
        }

        .challenge-status-text {
            font-size: 14px;
            color: #94a3b8;
            margin-top: 8px;
        }

        /* ── Progress bar ── */
        .progress-track {
            background: #334155;
            border-radius: 6px;
            height: 10px;
            overflow: hidden;
            margin-bottom: 12px;
        }

        .progress-fill {
            height: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, #38bdf8, #22c55e);
            transition: width 0.3s;
            width: 0%;
        }

        .progress-fill.success {
            background: linear-gradient(90deg, #22c55e, #4ade80) !important;
        }

        .progress-fill.fail {
            background: #ef4444 !important;
        }

        /* ── Timer ── */
        .timer {
            font-size: 20px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: #38bdf8;
            text-align: right;
            transition: color 0.3s;
        }

        .timer.warning { color: #ef4444; }

        /* ── Debug panel ── */
        .debug-panel {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            line-height: 1.8;
            max-height: 400px;
            overflow-y: auto;
        }

        .debug-row {
            display: flex;
            justify-content: space-between;
            padding: 2px 0;
            border-bottom: 1px solid #1e293b;
        }

        .debug-label {
            color: #64748b;
        }

        .debug-value {
            color: #38bdf8;
            font-weight: 600;
        }

        .debug-value.good { color: #22c55e; }
        .debug-value.bad { color: #ef4444; }
        .debug-value.warn { color: #eab308; }

        /* ── Log ── */
        .log-panel {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            line-height: 1.6;
            max-height: 200px;
            overflow-y: auto;
            margin-top: 16px;
        }

        .log-entry {
            padding: 2px 0;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
        }

        .log-entry .time { color: #475569; }
        .log-entry .msg { color: #94a3b8; }
        .log-entry.pass .msg { color: #22c55e; }
        .log-entry.fail .msg { color: #ef4444; }

        /* ── Header row ── */
        .header-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .stats-row {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }

        .stat-box {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px;
            text-align: center;
        }

        .stat-box .label {
            font-size: 9px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #64748b;
            margin-bottom: 4px;
        }

        .stat-box .value {
            font-size: 18px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: #38bdf8;
        }

        .config-info {
            font-size: 11px;
            color: #475569;
            margin-top: 12px;
            padding: 10px;
            background: #0f172a;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧪 Challenge Verification Tester</h1>
        <p class="subtitle">Test all challenge types directly — no login required</p>

        <div class="main-grid">
            <!-- LEFT COLUMN: Webcam + Controls -->
            <div>
                <div class="card">
                    <h2>📷 Camera</h2>
                    <div class="webcam-wrap">
                        <video id="video" autoplay playsinline muted></video>
                        <!-- Face position guide -->
                        <div class="face-guide">
                            <span class="face-guide-label-top">👤 Keep face here</span>
                            <svg viewBox="0 0 200 240" width="48%" xmlns="http://www.w3.org/2000/svg" style="overflow:visible">
                                <ellipse cx="100" cy="112" rx="82" ry="100" 
                                         stroke="rgba(56,189,248,0.15)" stroke-width="12" fill="none"/>
                                <ellipse cx="100" cy="112" rx="76" ry="95" 
                                         stroke="rgba(56,189,248,0.7)" stroke-width="2.5"
                                         stroke-dasharray="10 5" fill="none"/>
                                <line x1="40" y1="95" x2="160" y2="95" 
                                      stroke="rgba(56,189,248,0.25)" stroke-width="1" stroke-dasharray="4 4"/>
                                <line x1="100" y1="60" x2="100" y2="165" 
                                      stroke="rgba(56,189,248,0.15)" stroke-width="1" stroke-dasharray="4 4"/>
                            </svg>
                            <span class="face-guide-label">Stay in the oval — move gently</span>
                        </div>
                        <!-- Center dot -->
                        <div style="position:absolute;width:8px;height:8px;border-radius:50%;background:rgba(56,189,248,0.6);top:42%;left:50%;transform:translate(-50%,-50%);z-index:2;box-shadow:0 0 8px rgba(56,189,248,0.4);"></div>
                        <!-- Distance hint -->
                        <div style="position:absolute;bottom:6px;left:50%;transform:translateX(-50%);font-size:10px;font-weight:600;color:rgba(255,255,255,0.6);background:rgba(0,0,0,0.6);padding:3px 12px;border-radius:99px;z-index:5;white-space:nowrap;">📏 About arm's length from camera</div>
                        <div class="scan-line"></div>
                        <div class="scan-corners"><span></span></div>
                    </div>

                    <h2>Select Challenge</h2>
                    <div class="challenge-buttons">
                        <button onclick="selectChallenge('turn_left')" id="btn-turn_left">👈 Turn Left</button>
                        <button onclick="selectChallenge('turn_right')" id="btn-turn_right">Turn Right 👉</button>
                        <button onclick="selectChallenge('blink_twice')" id="btn-blink_twice">👁 Blink Twice</button>
                        <button onclick="selectChallenge('random')" id="btn-random" class="random-btn">🎲 Random Challenge</button>
                    </div>

                    <div class="action-buttons">
                        <button class="btn btn-start" id="startBtn" onclick="startTest()" disabled>▶ Start Test</button>
                        <button class="btn btn-stop" id="stopBtn" onclick="stopTest()" disabled>■ Stop</button>
                    </div>
                </div>

                <!-- Config info -->
                <div class="config-info">
                    <strong>Current Thresholds:</strong><br>
                    turn_ratio: {{ config.turn_ratio_threshold }}<br>
                    look_up: {{ config.look_up_threshold }} | look_down: {{ config.look_down_threshold }}<br>
                    neutral: {{ config.vertical_neutral_min }} - {{ config.vertical_neutral_max }}<br>
                    ear_blink: {{ config.ear_blink_threshold }} | blinks_needed: {{ config.required_blinks }}<br>
                    timeout: {{ config.timeout_seconds }}s | min_challenge_frames: {{ config.min_challenge_frames }}
                </div>
            </div>

            <!-- RIGHT COLUMN: Challenge + Debug -->
            <div>
                <div class="card">
                    <div class="header-row">
                        <h2>🎯 Challenge</h2>
                        <div class="timer" id="timer">--</div>
                    </div>

                    <div class="challenge-display" id="challengeDisplay">
                        <div class="challenge-icon" id="challengeIcon">🎯</div>
                        <div class="challenge-instruction" id="challengeInstruction">Select a challenge and click Start</div>
                        <div class="challenge-status-text" id="challengeStatusText"></div>
                    </div>

                    <div class="progress-track">
                        <div class="progress-fill" id="progressBar"></div>
                    </div>

                    <!-- Stats -->
                    <div class="stats-row">
                        <div class="stat-box">
                            <div class="label">Tests Run</div>
                            <div class="value" id="statTests">0</div>
                        </div>
                        <div class="stat-box">
                            <div class="label">Passed</div>
                            <div class="value" id="statPassed" style="color:#22c55e">0</div>
                        </div>
                        <div class="stat-box">
                            <div class="label">Failed</div>
                            <div class="value" id="statFailed" style="color:#ef4444">0</div>
                        </div>
                    </div>

                    <h2>📊 Live Debug</h2>
                    <div class="debug-panel" id="debugPanel">
                        <div class="debug-row">
                            <span class="debug-label">Status</span>
                            <span class="debug-value" id="dbgStatus">idle</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">Phase</span>
                            <span class="debug-value" id="dbgPhase">-</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">Progress</span>
                            <span class="debug-value" id="dbgProgress">0%</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">Message</span>
                            <span class="debug-value" id="dbgMessage">-</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">Remaining</span>
                            <span class="debug-value" id="dbgRemaining">-</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">FPS Sent</span>
                            <span class="debug-value" id="dbgFps">0</span>
                        </div>
                        <div class="debug-row">
                            <span class="debug-label">Latency</span>
                            <span class="debug-value" id="dbgLatency">-</span>
                        </div>
                    </div>

                    <div class="log-panel" id="logPanel"></div>
                </div>
            </div>
        </div>
    </div>

<script>
    // ══════════════════════════════════════════════
    //  STATE
    // ══════════════════════════════════════════════

    var selectedType = null;
    var challenge = null;
    var token = null;
    var running = false;
    var sending = false;
    var frameTimer = null;
    var tickTimer = null;
    var remaining = 0;
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    var video = document.getElementById('video');
    var framesSent = 0;
    var testStart = 0;
    var stats = { tests: 0, passed: 0, failed: 0 };

    // ── Init webcam ──
    async function initCamera() {
        try {
            var stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
                audio: false
            });
            video.srcObject = stream;
            addLog('Camera initialized');
        } catch (e) {
            addLog('Camera error: ' + e.message, 'fail');
        }
    }

    initCamera();

    // ══════════════════════════════════════════════
    //  CHALLENGE SELECTION
    // ══════════════════════════════════════════════

    function selectChallenge(type) {
        selectedType = type;

        // Update button styles
        var buttons = document.querySelectorAll('.challenge-buttons button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].classList.remove('active');
        }
        var btn = document.getElementById('btn-' + type);
        if (btn) btn.classList.add('active');

        document.getElementById('startBtn').disabled = false;

        var label = type === 'random' ? '🎲 Random (server picks)' : type;
        addLog('Selected: ' + label);
    }

    // ══════════════════════════════════════════════
    //  START / STOP
    // ══════════════════════════════════════════════

    async function startTest() {
        if (!selectedType) return;
        if (running) stopTest();

        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;

        // Reset UI
        resetUI();
        addLog('Requesting challenge...');

        // Request challenge from server
        try {
            var resp = await fetch('/test/api/get_challenge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ type: selectedType })
            });
            var data = await resp.json();

            if (!data.success) {
                addLog('Error: ' + (data.error || 'Unknown'), 'fail');
                document.getElementById('startBtn').disabled = false;
                return;
            }

            challenge = data.challenge;
            token = challenge.token;
            remaining = challenge.timeout;

            // Show challenge
            document.getElementById('challengeIcon').textContent = challenge.icon;
            document.getElementById('challengeInstruction').textContent = challenge.instruction;
            document.getElementById('challengeStatusText').textContent = 'Look straight at camera first...';
            document.getElementById('timer').textContent = remaining + 's';

            addLog('Challenge: ' + challenge.type + ' (token: ' + token.substring(0, 8) + '...)');

            stats.tests++;
            updateStats();

            // Start streaming
            running = true;
            framesSent = 0;
            testStart = Date.now();
            frameTimer = setInterval(captureAndSend, 250); // 4 fps
            tickTimer = setInterval(tick, 1000);

        } catch (e) {
            addLog('Network error: ' + e.message, 'fail');
            document.getElementById('startBtn').disabled = false;
        }
    }

    function stopTest() {
        running = false;
        if (frameTimer) { clearInterval(frameTimer); frameTimer = null; }
        if (tickTimer) { clearInterval(tickTimer); tickTimer = null; }
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;
        addLog('Test stopped');
    }

    // ══════════════════════════════════════════════
    //  FRAME CAPTURE & SEND
    // ══════════════════════════════════════════════

    async function captureAndSend() {
        if (!running || sending) return;
        sending = true;

        try {
            var vw = video.videoWidth;
            var vh = video.videoHeight;
            if (vw === 0 || vh === 0) { sending = false; return; }

            var scale = Math.min(480 / vw, 1);
            canvas.width = Math.round(vw * scale);
            canvas.height = Math.round(vh * scale);
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            var frameData = canvas.toDataURL('image/jpeg', 0.75);

            var t0 = Date.now();

            var resp = await fetch('/test/api/verify_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ frame: frameData, token: token })
            });

            var result = await resp.json();
            var latency = Date.now() - t0;

            framesSent++;
            var elapsed = (Date.now() - testStart) / 1000;
            var fps = (framesSent / elapsed).toFixed(1);

            // Update debug panel
            updateDebug(result, latency, fps);

            // Handle result
            if (result.status === 'passed') {
                running = false;
                clearInterval(frameTimer);
                clearInterval(tickTimer);
                stats.passed++;
                updateStats();

                document.getElementById('challengeDisplay').className = 'challenge-display passed';
                document.getElementById('challengeStatusText').textContent = '✅ ' + result.message;
                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressBar').classList.add('success');
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                addLog('PASSED: ' + result.message, 'pass');
                return;
            }

            if (result.status === 'expired') {
                running = false;
                clearInterval(frameTimer);
                clearInterval(tickTimer);
                stats.failed++;
                updateStats();

                document.getElementById('challengeDisplay').className = 'challenge-display failed';
                document.getElementById('challengeStatusText').textContent = '❌ Timed out';
                document.getElementById('startBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                addLog('FAILED: Timeout', 'fail');
                return;
            }

            // Update progress
            var pct = Math.round((result.progress || 0) * 100);
            document.getElementById('progressBar').style.width = pct + '%';
            document.getElementById('challengeStatusText').textContent = result.message || '';

            // Visual state
            var display = document.getElementById('challengeDisplay');
            display.className = 'challenge-display';
            if (result.status === 'detecting') {
                display.classList.add('detecting');
            }

        } catch (e) {
            console.error('Frame error:', e);
        } finally {
            sending = false;
        }
    }

    // ══════════════════════════════════════════════
    //  TIMER
    // ══════════════════════════════════════════════

    function tick() {
        remaining = Math.max(0, remaining - 1);
        var timerEl = document.getElementById('timer');
        timerEl.textContent = remaining + 's';

        if (remaining <= 5) {
            timerEl.classList.add('warning');
        } else {
            timerEl.classList.remove('warning');
        }

        if (remaining <= 0) {
            stopTest();
            stats.failed++;
            updateStats();
            document.getElementById('challengeDisplay').className = 'challenge-display failed';
            document.getElementById('challengeStatusText').textContent = '❌ Timed out';
            addLog('FAILED: Timeout (client)', 'fail');
        }
    }

    // ══════════════════════════════════════════════
    //  DEBUG PANEL
    // ══════════════════════════════════════════════

    function updateDebug(result, latency, fps) {
        var status = result.status || '-';
        var statusClass = '';
        if (status === 'passed' || status === 'neutral_ok') statusClass = 'good';
        else if (status === 'no_face' || status === 'face_mismatch' || status === 'expired') statusClass = 'bad';
        else if (status === 'detecting') statusClass = 'warn';

        setDebug('dbgStatus', status, statusClass);
        setDebug('dbgPhase', result.status || '-');
        setDebug('dbgProgress', Math.round((result.progress || 0) * 100) + '%');
        setDebug('dbgMessage', result.message || '-');
        setDebug('dbgRemaining', result.remaining !== undefined ? result.remaining + 's' : '-');
        setDebug('dbgFps', fps);

        var latClass = latency < 200 ? 'good' : (latency < 500 ? 'warn' : 'bad');
        setDebug('dbgLatency', latency + 'ms', latClass);
    }

    function setDebug(id, value, cls) {
        var el = document.getElementById(id);
        if (el) {
            el.textContent = value;
            el.className = 'debug-value';
            if (cls) el.classList.add(cls);
        }
    }

    // ══════════════════════════════════════════════
    //  LOG
    // ══════════════════════════════════════════════

    function addLog(message, type) {
        var panel = document.getElementById('logPanel');
        var now = new Date().toLocaleTimeString();
        var cls = type === 'pass' ? 'pass' : (type === 'fail' ? 'fail' : '');

        var entry = document.createElement('div');
        entry.className = 'log-entry ' + cls;
        entry.innerHTML = '<span class="time">[' + now + ']</span> <span class="msg">' + message + '</span>';

        panel.insertBefore(entry, panel.firstChild);

        // Keep only last 50 entries
        while (panel.children.length > 50) {
            panel.removeChild(panel.lastChild);
        }
    }

    // ══════════════════════════════════════════════
    //  HELPERS
    // ══════════════════════════════════════════════

    function updateStats() {
        document.getElementById('statTests').textContent = stats.tests;
        document.getElementById('statPassed').textContent = stats.passed;
        document.getElementById('statFailed').textContent = stats.failed;
    }

    function resetUI() {
        document.getElementById('progressBar').style.width = '0%';
        document.getElementById('progressBar').className = 'progress-fill';
        document.getElementById('challengeDisplay').className = 'challenge-display';
        document.getElementById('challengeStatusText').textContent = '';
        document.getElementById('challengeIcon').textContent = '🎯';
        document.getElementById('challengeInstruction').textContent = 'Loading...';
        document.getElementById('timer').textContent = '--';
        document.getElementById('timer').classList.remove('warning');
    }
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════

@app.route('/test')
def test_page():
    """Serve the test page."""
    return render_template_string(TEST_HTML, config=test_config)


@app.route('/test/api/get_challenge', methods=['POST'])
def test_get_challenge():
    """Generate a challenge for testing (no auth required)."""
    data = request.get_json(force=True)
    requested_type = data.get('type', 'random')

    if requested_type == 'random':
        challenge = challenge_manager.generate()
    else:
        # Force a specific challenge type
        challenge = challenge_manager.generate()
        # Override the type
        if requested_type in challenge_manager.CHALLENGES:
            info = challenge_manager.CHALLENGES[requested_type]
            challenge['type'] = requested_type
            challenge['instruction'] = info['instruction']
            challenge['icon'] = info['icon']

    # Store in session
    session['test_challenge'] = challenge
    session.modified = True

    logger.info(f"Test challenge: {challenge['type']} (token: {challenge['token'][:8]})")

    return jsonify({
        'success': True,
        'challenge': {
            'type': challenge['type'],
            'instruction': challenge['instruction'],
            'icon': challenge['icon'],
            'token': challenge['token'],
            'timeout': test_config['timeout_seconds'],
        }
    })


@app.route('/test/api/verify_frame', methods=['POST'])
def test_verify_frame():
    """Verify a frame against the test challenge (no auth required)."""
    challenge = session.get('test_challenge')
    if not challenge:
        return jsonify({'success': False, 'error': 'No challenge', 'status': 'error'}), 400

    data = request.get_json(force=True)
    token = data.get('token', '')

    if token != challenge['token']:
        return jsonify({'success': False, 'error': 'Bad token', 'status': 'error'}), 403

    # Decode frame
    frame_rgb = decode_frame(data.get('frame', ''))
    if frame_rgb is None:
        return jsonify({'success': False, 'error': 'Bad frame', 'status': 'error'}), 400

    # Process frame (no identity check in test mode)
    result = challenge_manager.process_frame(frame_rgb, challenge, enrolled_encodings=None)

    # Save state back
    session['test_challenge'] = challenge
    session.modified = True

    response = {
        'success': True,
        'status': result['status'],
        'message': result['message'],
        'progress': result.get('progress', 0),
        'remaining': round(challenge_manager.time_remaining(challenge), 1),
    }

    if result['status'] == 'passed':
        session.pop('test_challenge', None)
        logger.info(f"Test PASSED: {challenge['type']}")

    return jsonify(response)


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  CHALLENGE TESTER — Debug Mode")
    print("  Open: http://localhost:5001/test")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=5001, debug=True)
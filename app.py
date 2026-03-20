"""
Face Verification Login System - Flask Backend
Production-ready backend with security and logging.
"""

import os
import sys
import json
import time
import hashlib
import base64
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps

import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session as FlaskSession
from werkzeug.security import generate_password_hash, check_password_hash

from config import (
    DATABASE_PATH, ENROLLMENT_TARGET_SAMPLES, ENROLLMENT_MIN_SAMPLES,
    LOGIN_CAPTURE_FPS, LOGIN_CAPTURE_DURATION_SECONDS, LOGIN_MIN_FRAMES,
    MAX_LOGIN_ATTEMPTS_PER_HOUR, MAX_VERIFY_ATTEMPTS_PER_LOGIN,
    SESSION_TIMEOUT_MINUTES, FACE_MATCH_THRESHOLD, MIN_MATCH_RATIO,
    LOG_LEVEL, LOG_DIR, LOG_FILE, ERROR_MESSAGES, SUCCESS_MESSAGES,
    ADMIN_MAINTENANCE_MODE,
    DEBUG_FACE, DEBUG_FRAMES_DIR, DEBUG_FACE_MAX_SAVED_FRAMES,
    BLINK_DETECTION_ENABLED, BLINK_MIN_FRAMES, BLINK_DETECTION_TIMEOUT,
    CHALLENGE_CONFIG,

)
from database import get_db
from face_utils import FaceDetector, FaceRecognizer, validate_frame
from anti_spoof import analyze_liveness
from blink_detector import detect_blink_from_frames
from challenge import ChallengeManager
# ==================== APP SETUP ====================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Session configuration
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
FlaskSession(app)

# Create logs directory
os.makedirs(LOG_DIR, exist_ok=True)

# ==================== LOGGING ====================

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# Use UTF-8 encoding for file handler (supports Unicode/emoji)
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.INFO)

# Use UTF-8 for console (Windows still may have issues with emojis in terminal)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ==================== CHALLENGE MANAGER ====================
challenge_manager = ChallengeManager(config=CHALLENGE_CONFIG)

# ==================== HELPERS ====================

def get_client_ip():
    """Get client IP from request."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def get_user_agent():
    """Get user agent from request."""
    return request.headers.get('User-Agent', 'Unknown')

def hash_password(password):
    """Hash password for storage."""
    return generate_password_hash(password)

def verify_password(stored_hash, password):
    """Verify password against hash."""
    return check_password_hash(stored_hash, password)

def login_required(f):
    """Decorator to require login for a route.
    Accepts normal biometric auth, password-only auth, and emergency bypass."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Accept if: user_id exists AND one approved auth path is active.
        has_user = 'user_id' in session
        is_verified = session.get('verified_face', False)
        is_password_only = session.get('auth_method') == 'password_only'
        is_emergency_bypass = session.get('emergency_bypass', False)
        
        if not has_user or (not is_verified and not is_password_only and not is_emergency_bypass):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Not logged in'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges.
    Accepts normal biometric auth, password-only auth, and emergency bypass."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Accept if: user_id exists AND one approved auth path is active.
        has_user = 'user_id' in session
        is_verified = session.get('verified_face', False)
        is_password_only = session.get('auth_method') == 'password_only'
        is_emergency_bypass = session.get('emergency_bypass', False)
        
        if not has_user or (not is_verified and not is_password_only and not is_emergency_bypass):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Not logged in'}), 401
            return redirect(url_for('index'))
        
        db = get_db()
        if not db.is_admin(session['user_id']):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Admin access required'}), 403
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def rate_limit_check(user_id, limit_type='login'):
    """Check if user exceeded rate limit."""
    db = get_db()
    if limit_type == 'login':
        attempts = db.get_recent_login_attempts(user_id, hours=1)
        if attempts >= MAX_LOGIN_ATTEMPTS_PER_HOUR:
            return False, f"Too many login attempts. Try again after 1 hour."
    return True, None


def debug_log_failed_verification(
    user_id,
    verify_session_id,
    reason,
    frames=None,
    frame_metrics=None,
    liveness_score=None,
    face_distance=None,
    min_distance=None,
    avg_distance=None,
    blink_stats=None,
):
    """Save failed verification frames and print tuning metrics when DEBUG_FACE is enabled."""
    if not DEBUG_FACE:
        return

    frames = frames or []
    frame_metrics = frame_metrics or []
    blink_stats = blink_stats or {}

    try:
        os.makedirs(DEBUG_FRAMES_DIR, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        safe_session = (verify_session_id or 'no_session')[:8]
        debug_prefix = f"{timestamp}_{user_id}_{safe_session}_{reason}"

        frames_to_save = frames[:DEBUG_FACE_MAX_SAVED_FRAMES]
        saved_files = []
        for index, frame in enumerate(frames_to_save):
            file_name = f"{debug_prefix}_frame_{index:02d}.jpg"
            file_path = os.path.join(DEBUG_FRAMES_DIR, file_name)
            if cv2.imwrite(file_path, frame):
                saved_files.append(file_name)

        brightness_values = [
            m.get('brightness_mean') for m in frame_metrics
            if m.get('brightness_mean') is not None
        ]
        blur_values = [
            m.get('blur_score') for m in frame_metrics
            if m.get('blur_score') is not None
        ]

        brightness_summary = (
            f"avg={float(np.mean(brightness_values)):.2f}, min={float(np.min(brightness_values)):.2f}, max={float(np.max(brightness_values)):.2f}"
            if brightness_values else "n/a"
        )
        blur_summary = (
            f"avg={float(np.mean(blur_values)):.3f}, min={float(np.min(blur_values)):.3f}, max={float(np.max(blur_values)):.3f}"
            if blur_values else "n/a"
        )

        distance_text = "n/a" if face_distance is None else f"{float(face_distance):.4f}"
        min_distance_text = "n/a" if min_distance is None else f"{float(min_distance):.4f}"
        avg_distance_text = "n/a" if avg_distance is None else f"{float(avg_distance):.4f}"
        liveness_text = "n/a" if liveness_score is None else f"{float(liveness_score):.4f}"
        blink_text = f"avg_ear={blink_stats.get('avg_ear', 0):.4f}, count={blink_stats.get('blink_count', 0)}" if blink_stats else "n/a"

        logger.warning(
            "[DEBUG_FACE] verification_failed "
            f"user={user_id} session={verify_session_id} reason={reason} "
            f"face_distance={distance_text} min_distance={min_distance_text} avg_distance={avg_distance_text} "
            f"liveness_score={liveness_text} blink={blink_text} blur_score={blur_summary} brightness={brightness_summary} "
            f"frames_received={len(frames)} frames_saved={len(saved_files)} debug_dir={DEBUG_FRAMES_DIR}"
        )

        if saved_files:
            logger.warning(f"[DEBUG_FACE] saved_frame_files={saved_files}")
    except Exception as debug_error:
        logger.error(f"[DEBUG_FACE] failed to save debug artifacts: {debug_error}")

def get_enrolled_encodings(user_id):
    """Get enrolled face encodings for a user as numpy arrays.
    Used by challenge system for identity re-verification."""
    try:
        db = get_db()
        stored = db.get_user_embeddings(user_id)
        if not stored:
            return None
        encodings = []
        for e in stored:
            if isinstance(e, str):
                encodings.append(np.array(json.loads(e)))
            else:
                encodings.append(np.array(e))
        return encodings if encodings else None
    except Exception as ex:
        logger.error(f"Failed to load encodings for {user_id}: {ex}")
        return None

def _challenge_identity_check(frame_bgr, user_id):
    """
    Single-frame identity check during challenge.
    """
    try:
        detector   = FaceDetector()
        recognizer = FaceRecognizer()

        threshold = CHALLENGE_CONFIG['identity_threshold']

        validation = validate_frame(frame_bgr, detector)
        if not validation['is_valid']:
            logger.info(f"[CHALLENGE-ID] user={user_id}: frame invalid (skipped)")
            return False, False, None

        embedding = recognizer.get_embedding(frame_bgr, validation['face_location'])
        if embedding is None:
            logger.info(f"[CHALLENGE-ID] user={user_id}: no embedding (skipped)")
            return False, False, None

        db = get_db()
        stored_embeddings = db.get_user_embeddings(user_id)
        if not stored_embeddings:
            logger.info(f"[CHALLENGE-ID] user={user_id}: no stored embeddings")
            return False, False, None

        stored_arr = np.array([
            json.loads(e) if isinstance(e, str) else e
            for e in stored_embeddings
        ])

        comparison = recognizer.compare_embeddings(
            embedding, stored_arr,
            tolerance=threshold
        )

        distances = comparison['distances']
        min_dist = float(np.min(distances))
        avg_dist = float(np.mean(distances))
        matched  = min_dist < threshold

        logger.info(
            f"[CHALLENGE-ID] user={user_id}: "
            f"min_dist={min_dist:.4f} avg_dist={avg_dist:.4f} "
            f"threshold={threshold:.4f} "
            f"stored_embeddings={len(stored_arr)} "
            f"{'✅ MATCH' if matched else '❌ MISMATCH'}"
        )

        return True, matched, min_dist

    except Exception as exc:
        logger.warning(f"[CHALLENGE-ID] check error for {user_id}: {exc}")
        return False, False, None
# ==================== ROUTES: PUBLIC ====================

@app.route('/')
@app.route('/login')
def index():
    """Home page / login page."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register')
def register_page():
    """Public registration is disabled; user creation is admin-only."""
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard after login."""
    return render_template('dashboard.html', user_id=session['user_id'])

# ==================== ROUTES: AUTHENTICATION ====================

@app.route('/api/admin/create-user', methods=['POST'])
@admin_required
def admin_create_user():
    """
    Admin endpoint to create a new user.
    Accessible only to authenticated admins.
    """
    data = request.json
    user_id = data.get('user_id', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()
    
    if not user_id or not password:
        return jsonify({'success': False, 'error': 'User ID and password required'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
    
    db = get_db()
    
    # Check if user exists
    if db.get_user(user_id):
        return jsonify({'success': False, 'error': 'User already exists'}), 409
    
    # Hash password and create user
    password_hash = hash_password(password)
    if db.create_user(user_id, password_hash, email):
        logger.info(f"Admin created user: {user_id}")
        return jsonify({
            'success': True,
            'message': 'User created. User can now enroll their face.',
            'user_id': user_id
        }), 201
    else:
        return jsonify({'success': False, 'error': 'Failed to create user'}), 500

@app.route('/api/auth/register', methods=['POST'])
def api_register_user():
    """Public registration is disabled; only admins can create users."""
    return jsonify({
        'success': False,
        'error': 'Account creation is disabled here. Please contact admin.'
    }), 403

@app.route('/switch-account', methods=['GET'])
def switch_account():
    """Clear session and redirect to login so another user can sign in."""
    previous_user = session.get('user_id') or session.get('pending_user_id')
    session.clear()
    if previous_user:
        logger.info(f"Account switch requested. Previous user: {previous_user}")
    return redirect(url_for('index'))

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """
    Step 1: Verify credentials.
    Client sends user_id and password.
    If valid, open webcam for face verification.
    """
    data = request.json
    user_id = data.get('user_id', '').strip()
    password = data.get('password', '').strip()
    
    if not user_id or not password:
        return jsonify({'success': False, 'error': ERROR_MESSAGES['invalid_credentials']}), 400
    
    db = get_db()
    user = db.get_user(user_id)
    
    if not user or not verify_password(user['password_hash'], password):
        logger.warning(f"Failed login attempt for user: {user_id}")
        return jsonify({'success': False, 'error': ERROR_MESSAGES['invalid_credentials']}), 401

    if 'is_active' in user.keys() and not bool(user['is_active']):
        return jsonify({'success': False, 'error': 'Account is disabled. Contact admin.'}), 403
    
    # Check rate limit
    allowed, msg = rate_limit_check(user_id, 'login')
    if not allowed:
        logger.warning(f"Rate limit exceeded for user: {user_id}")
        return jsonify({'success': False, 'error': msg}), 429

    face_verification_enabled = bool(user.get('face_verification_enabled', 1))
    if not face_verification_enabled:
        session.permanent = True
        session['user_id'] = user_id
        session['verified_face'] = False
        session['auth_method'] = 'password_only'
        session.pop('pending_user_id', None)
        session.pop('verify_session_id', None)
        session.pop('active_challenge', None)
        session.pop('login_stage', None)
        session.pop('emergency_bypass', None)

        db.update_last_login(user_id)
        db.log_verification_attempt(
            user_id, 'login', True,
            match_distance=0.0,
            anti_spoof_score=0.0,
            quality_score=0.0,
            num_frames=0,
            error_reason='password_only_admin_approved',
            ip_address=get_client_ip(),
            user_agent=get_user_agent(),
        )

        logger.info(
            f"[PASSWORD-ONLY] User {user_id} logged in without biometric verification"
        )
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user_id': user_id,
            'password_only': True,
            'redirect': '/dashboard',
        }), 200

    # Check if user is enrolled (only required for biometric login)
    if not user['is_enrolled']:
        return jsonify({
            'success': False,
            'error': 'User not enrolled. Please complete face enrollment first.'
        }), 403
    
    # Create verification session (don't authenticate yet!)
    verify_session_id = str(uuid.uuid4())
    session['verify_session_id'] = verify_session_id
    session['pending_user_id'] = user_id  # Temporary, not authenticated yet
    session['attempt_count'] = 0
    session['last_attempt'] = datetime.now().isoformat()
    session.pop('auth_method', None)
    session.pop('emergency_bypass', None)
    
    logger.info(f"Login step 1 successful for user: {user_id}, session: {verify_session_id}")
    
    return jsonify({
        'success': True,
        'message': 'Credentials verified. Please look at camera for face verification.',
        'verify_session_id': verify_session_id
    }), 200

@app.route('/api/auth/verify-face', methods=['POST'])
def api_verify_face():
    """
    Step 2: Verify face using captured frames.
    Client sends base64-encoded frames collected from webcam.
    
    EMERGENCY MODE: If ADMIN_MAINTENANCE_MODE is enabled, admins can bypass
    face verification by sending empty frames array. This allows system access
    during face verification outages.
    """
    if 'pending_user_id' not in session or 'verify_session_id' not in session:
        return jsonify({'success': False, 'error': 'Invalid session'}), 401
    
    user_id = session['pending_user_id']
    verify_session_id = session['verify_session_id']
    db = get_db()
    
    data = request.json
    frames_b64 = data.get('frames', [])
    
    # ========== EMERGENCY ADMIN BYPASS ==========
    # Only bypasses if: maintenance mode enabled AND admin is NOT enrolled (no face data)
    # If admin IS enrolled with face data, always require face verification even in maintenance mode
    admin_not_enrolled = not db.get_user(user_id)['is_enrolled'] if db.get_user(user_id) else True
    if ADMIN_MAINTENANCE_MODE and db.is_admin(user_id) and admin_not_enrolled:
        logger.warning(f"[MAINTENANCE MODE] Admin {user_id} logging in without face verification!")
        logger.warning(f"[MAINTENANCE MODE] This should only happen in emergency. Disable ADMIN_MAINTENANCE_MODE when fixed!")
        
        # Log this unusual authentication for audit
        db.log_verification_attempt(
            user_id, 'login', True,
            match_distance=0.0,
            anti_spoof_score=1.0,
            quality_score=1.0,
            num_frames=0,
            error_reason='admin_emergency_bypass',
            ip_address=get_client_ip(),
            user_agent=get_user_agent(),
            session_id=verify_session_id
        )
        
        # Authenticate admin user (bypass everything including challenge)
        session.permanent = True
        session['user_id'] = user_id
        session['verified_face'] = False  # Mark as bypassed (not normal)
        session['emergency_bypass'] = True  # Flag for UI to show warning
        session.pop('pending_user_id', None)
        
        db.update_last_login(user_id)
        
        return jsonify({
            'success': True,
            'message': '[MAINTENANCE MODE] Logged in without face verification!',
            'user_id': user_id,
            'emergency_bypass': True
        }), 200
    # ========== END EMERGENCY BYPASS ==========
    
    if not frames_b64 or len(frames_b64) < LOGIN_MIN_FRAMES:
        return jsonify({
            'success': False,
            'error': f'Need at least {LOGIN_MIN_FRAMES} frames',
        }), 400
    
    # Check attempt count
    attempt_count = session.get('attempt_count', 0)
    if attempt_count >= MAX_VERIFY_ATTEMPTS_PER_LOGIN:
        logger.warning(f"Max verify attempts exceeded for user: {user_id}")
        return jsonify({
            'success': False,
            'error': ERROR_MESSAGES['too_many_attempts']
        }), 429
    
    session['attempt_count'] = attempt_count + 1

    frames = []
    t_start = time.time()
    try:
        # Decode frames
        for frame_b64 in frames_b64:
            try:
                # Remove data URI prefix if present
                if ',' in frame_b64:
                    frame_b64 = frame_b64.split(',')[1]
                frame_bytes = base64.b64decode(frame_b64)
                frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.append(frame)
            except Exception as e:
                logger.warning(f"Failed to decode frame: {e}")
                continue
        
        if len(frames) < LOGIN_MIN_FRAMES:
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason='invalid_decoded_frames',
                frames=frames,
            )
            return jsonify({
                'success': False,
                'error': f'Invalid frames. Need at least {LOGIN_MIN_FRAMES} valid frames.'
            }), 400
        
        # Process frames and extract useful ones
        t_process_start = time.time()
        detector = FaceDetector()
        recognizer = FaceRecognizer()
        
        # ── PASS 1: validate frames (fast HOG face detect + quality check) ──────
        valid_frames = []
        face_locations_list = []
        quality_scores = []
        frame_metrics = []
        
        for frame in frames:
            result = validate_frame(frame, detector)
            frame_metrics.append({
                'is_valid': result.get('is_valid', False),
                'brightness_mean': result.get('brightness_mean'),
                'blur_score': result.get('quality_checks', {}).get('blur') if result.get('quality_checks') else None,
                'quality_score': result.get('quality_score'),
                'error': result.get('error')
            })
            if result['is_valid']:
                valid_frames.append(frame)
                face_locations_list.append(result['face_location'])
                quality_scores.append(result['quality_score'])
        
        logger.info(f"[TIMING] frame validation: {(time.time()-t_process_start)*1000:.0f}ms "
                    f"({len(valid_frames)}/{len(frames)} valid)")
        
        if len(valid_frames) < 2:
            logger.info(f"Not enough valid frames for user {user_id}: {len(valid_frames)}")
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason='low_quality_not_enough_embeddings',
                frames=valid_frames if valid_frames else frames,
                frame_metrics=frame_metrics,
            )
            return jsonify({
                'success': False,
                'error': ERROR_MESSAGES['low_quality'],
                'retry': True
            }), 400
        
        # ── BLINK DETECTION ───────────────────────────────────────────────────
        t_blink = time.time()
        blink_confirmed = False
        if BLINK_DETECTION_ENABLED and len(valid_frames) >= BLINK_MIN_FRAMES:
            logger.info(f"Running blink detection for {user_id} on {len(valid_frames)} frames")
            blink_result = detect_blink_from_frames(valid_frames, face_locations_list)
            
            blink_detected = blink_result['blink_detected']
            blink_count = blink_result['blink_count']
            blink_stats = blink_result['stats']
            
            logger.info(f"[TIMING] blink detection: {(time.time()-t_blink)*1000:.0f}ms — "
                       f"detected={blink_detected}, count={blink_count}, "
                       f"reason={blink_result.get('reason', 'N/A')}, "
                       f"frames={blink_result.get('frames_valid', 0)}/{blink_result.get('frames_total', 0)} valid, "
                       f"skipped={blink_result.get('frames_skipped', 0)}, "
                       f"avg_ear={blink_stats.get('avg_ear') or 'N/A'}, "
                       f"min_ear={blink_stats.get('min_ear') or 'N/A'}, "
                       f"baseline={blink_stats.get('baseline_ear') or 'N/A'}, "
                       f"threshold={blink_stats.get('adaptive_threshold')}, "
                       f"transitions={blink_stats.get('state_transitions')}")
            
            if not blink_detected:
                frames_total_b   = blink_result.get('frames_total', 0)
                frames_skipped_b = blink_result.get('frames_skipped', 0)
                frames_valid_b   = blink_result.get('frames_valid', 0)
                skip_ratio       = frames_skipped_b / frames_total_b if frames_total_b > 0 else 0

                glasses_blocking = skip_ratio > 0.50 and frames_valid_b < 4
                if glasses_blocking:
                    logger.warning(
                        f"[GLASSES-FALLBACK] Blink check skipped for {user_id} — "
                        f"{frames_skipped_b}/{frames_total_b} frames had no EAR "
                        f"(glasses likely blocking eye landmarks). "
                        f"Falling through to liveness+matching checks."
                    )
                    blink_confirmed = True
                else:
                    logger.warning(f"No blink detected for {user_id} - likely photo/screen spoof")
                    db = get_db()
                    db.log_verification_attempt(
                        user_id, 'login', False,
                        anti_spoof_score=0.0,
                        quality_score=np.mean(quality_scores) if quality_scores else 0.0,
                        num_frames=len(valid_frames),
                        error_reason='no_blink_detected',
                        ip_address=get_client_ip(),
                        user_agent=get_user_agent(),
                        session_id=verify_session_id
                    )
                    debug_log_failed_verification(
                        user_id=user_id,
                        verify_session_id=verify_session_id,
                        reason='no_blink_detected',
                        frames=valid_frames,
                        frame_metrics=frame_metrics,
                        blink_stats=blink_stats,
                    )
                    return jsonify({
                        'success': False,
                        'error': 'No blink detected. Please blink slowly once during verification.',
                        'retry': True,
                        'blink_detected': False
                    }), 403
            
            logger.info(f"Blink successfully detected for {user_id}, proceeding with face verification")
            blink_confirmed = True
        
        # ── PASS 2: encode only top-N frames by quality (slow ResNet step) ────
        if not BLINK_DETECTION_ENABLED:
            blink_confirmed = True
        MAX_ENCODE_FRAMES = 5
        t_encode = time.time()
        
        if len(valid_frames) > MAX_ENCODE_FRAMES:
            top_indices = sorted(
                range(len(quality_scores)),
                key=lambda i: quality_scores[i],
                reverse=True
            )[:MAX_ENCODE_FRAMES]
            top_indices = sorted(top_indices)
        else:
            top_indices = list(range(len(valid_frames)))
        
        embeddings = []
        for i in top_indices:
            emb = recognizer.get_embedding(valid_frames[i], face_locations_list[i])
            if emb is not None:
                embeddings.append(emb)
        
        logger.info(f"[TIMING] face encoding: {(time.time()-t_encode)*1000:.0f}ms "
                    f"({len(embeddings)} embeddings from top {len(top_indices)} frames)")
        
        if len(embeddings) < 2:
            logger.info(f"Not enough valid embeddings for user {user_id}: {len(embeddings)}")
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason='low_quality_not_enough_embeddings',
                frames=valid_frames if valid_frames else frames,
                frame_metrics=frame_metrics,
            )
            return jsonify({
                'success': False,
                'error': ERROR_MESSAGES['low_quality'],
                'retry': True
            }), 400
        
        # ========== LIVENESS ANALYSIS (PASSIVE ANTI-SPOOF) ==========
        t_liveness = time.time()
        liveness_result = analyze_liveness(valid_frames, face_locations_list, quality_scores)
        liveness_score = liveness_result['score']
        liveness_decision = liveness_result['decision']
        logger.info(f"[TIMING] liveness: {(time.time()-t_liveness)*1000:.0f}ms — "
                    f"score={liveness_score:.3f}, decision={liveness_decision}")
        
        if liveness_decision == 'reject':
            logger.warning(f"Spoof detected for user {user_id}: score={liveness_score:.3f}")
            db = get_db()
            db.log_verification_attempt(
                user_id, 'login', False,
                anti_spoof_score=liveness_score,
                quality_score=np.mean(quality_scores),
                motion_score=liveness_result['details']['motion'].get('score', 0),
                texture_score=liveness_result['details']['texture'].get('score', 0),
                num_frames=len(embeddings),
                error_reason='spoof_detected',
                ip_address=get_client_ip(),
                user_agent=get_user_agent(),
                session_id=verify_session_id
            )
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason='spoof_detected',
                frames=valid_frames,
                frame_metrics=frame_metrics,
                liveness_score=liveness_score,
            )
            return jsonify({
                'success': False,
                'error': ERROR_MESSAGES['spoof_detected'],
                'retry': True
            }), 403
        
        if liveness_decision == 'uncertain':
            logger.info(f"Uncertain liveness for user {user_id}: score={liveness_score:.3f}")
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason='liveness_uncertain',
                frames=valid_frames,
                frame_metrics=frame_metrics,
                liveness_score=liveness_score,
            )
            return jsonify({
                'success': False,
                'error': SUCCESS_MESSAGES['retry'],
                'retry': True
            }), 400
        
        # ── FACE MATCHING ───────────────────────────────────────────────
        t_match = time.time()
        db = get_db()
        stored_embeddings = db.get_user_embeddings(user_id)
        
        if not stored_embeddings:
            logger.error(f"No stored embeddings for enrolled user {user_id}")
            return jsonify({'success': False, 'error': 'User not properly enrolled'}), 500
        
        stored_emb_arrays = np.array([json.loads(e) if isinstance(e, str) else e 
                                      for e in stored_embeddings])
        
        # ========== MULTI-EMBEDDING MATCHING ==========
        all_pair_distances = []

        for live_embedding in embeddings:
            comparison = recognizer.compare_embeddings(
                live_embedding,
                stored_emb_arrays,
                tolerance=FACE_MATCH_THRESHOLD
            )
            all_pair_distances.extend(comparison['distances'])

        all_pair_distances = np.array(all_pair_distances)
        
        # ========== PHOTO/SCREEN DETECTION ==========
        if len(embeddings) >= 3:
            consecutive_distances = []
            for i in range(len(embeddings) - 1):
                dist = float(np.linalg.norm(embeddings[i] - embeddings[i+1]))
                consecutive_distances.append(dist)
            
            avg_consecutive_dist = float(np.mean(consecutive_distances))
            max_consecutive_dist = float(np.max(consecutive_distances))
            
            PHOTO_DETECTION_THRESHOLD = 0.06
            
            if avg_consecutive_dist < PHOTO_DETECTION_THRESHOLD:
                logger.warning(f"PHOTO/SCREEN SUSPECTED for {user_id}: "
                             f"avg_consecutive_dist={avg_consecutive_dist:.4f} < {PHOTO_DETECTION_THRESHOLD} "
                             f"(embeddings too consistent - likely static image)")
                db.log_verification_attempt(
                    user_id, 'login', False,
                    match_distance=float(np.mean(all_pair_distances)),
                    anti_spoof_score=liveness_score,
                    quality_score=np.mean(quality_scores),
                    num_frames=len(embeddings),
                    error_reason='photo_screen_detected',
                    ip_address=get_client_ip(),
                    user_agent=get_user_agent(),
                    session_id=verify_session_id
                )
                return jsonify({
                    'success': False,
                    'error': ERROR_MESSAGES['spoof_detected'],
                    'retry': True
                }), 403
            
            logger.info(f"Photo detection check for {user_id}: "
                       f"avg_consecutive_dist={avg_consecutive_dist:.4f}, "
                       f"max={max_consecutive_dist:.4f} (PASS - natural variation detected)")
        
        aggregated_distance = float(np.mean(all_pair_distances))
        min_distance        = float(np.min(all_pair_distances))
        avg_distance        = aggregated_distance
        match_ratio         = float(np.mean(all_pair_distances < FACE_MATCH_THRESHOLD))

        faces_matched = (aggregated_distance < FACE_MATCH_THRESHOLD) and (match_ratio >= MIN_MATCH_RATIO)
        
        logger.info(f"Multi-frame face matching for {user_id}: "
                   f"mean={aggregated_distance:.3f}, min={min_distance:.3f}, "
                   f"match_ratio={match_ratio:.2%} (need >={MIN_MATCH_RATIO:.0%}), "
                   f"pairs={len(all_pair_distances)} ({len(embeddings)} live × {len(stored_emb_arrays)} stored), "
                   f"threshold={FACE_MATCH_THRESHOLD}, match={faces_matched} "
                   f"[{(time.time()-t_match)*1000:.0f}ms]")
        
        if not faces_matched:
            reject_reason = 'face_ratio_below_min' if (aggregated_distance < FACE_MATCH_THRESHOLD and match_ratio < MIN_MATCH_RATIO) else 'face_not_matched'
            logger.warning(f"Face mismatch for user {user_id}: mean={aggregated_distance:.3f}, "
                           f"match_ratio={match_ratio:.2%} (need >={MIN_MATCH_RATIO:.0%}), reason={reject_reason}")
            db.log_verification_attempt(
                user_id, 'login', False,
                match_distance=aggregated_distance,
                min_distance=min_distance,
                avg_distance=avg_distance,
                anti_spoof_score=liveness_score,
                quality_score=np.mean(quality_scores),
                num_frames=len(embeddings),
                error_reason=reject_reason,
                ip_address=get_client_ip(),
                user_agent=get_user_agent(),
                session_id=verify_session_id
            )
            debug_log_failed_verification(
                user_id=user_id,
                verify_session_id=verify_session_id,
                reason=reject_reason,
                frames=valid_frames,
                frame_metrics=frame_metrics,
                liveness_score=liveness_score,
                face_distance=aggregated_distance,
                min_distance=min_distance,
                avg_distance=avg_distance,
            )
            return jsonify({
                'success': False,
                'error': ERROR_MESSAGES['face_not_matched'],
                'retry': True
            }), 403
        
        # ════════════════════════════════════════════════════════════════
        # ✓ FACE + BLINK + LIVENESS ALL PASSED
        # Do NOT authenticate yet — user must complete active challenge first
        # ════════════════════════════════════════════════════════════════
        total_ms = (time.time() - t_start) * 1000
        logger.info(f"Face verification passed for {user_id} — {total_ms:.0f}ms. Proceeding to challenge.")
        
        db.log_verification_attempt(
            user_id, 'login', True,
            match_distance=aggregated_distance,
            min_distance=min_distance,
            avg_distance=avg_distance,
            anti_spoof_score=liveness_score,
            quality_score=np.mean(quality_scores),
            motion_score=liveness_result['details']['motion'].get('score', 0),
            texture_score=liveness_result['details']['texture'].get('score', 0),
            num_frames=len(embeddings),
            ip_address=get_client_ip(),
            user_agent=get_user_agent(),
            session_id=verify_session_id
        )
        
        # Set session stage — challenge is the next step
        # Do NOT set user_id or verified_face yet
        # Keep pending_user_id — needed for challenge identity check
        session['login_stage'] = 'face_verified'
        
        return jsonify({
            'success': True,
            'message': 'Face verified. Please complete the liveness challenge.',
            'user_id': user_id,
            'blink_confirmed': blink_confirmed,
            'next_step': 'challenge'
        }), 200
    
    except Exception as e:
        logger.error(f"Error in face verification for {user_id}: {e}", exc_info=True)
        debug_log_failed_verification(
            user_id=user_id,
            verify_session_id=verify_session_id,
            reason='verify_exception',
            frames=frames,
        )
        return jsonify({'success': False, 'error': ERROR_MESSAGES['unknown_error']}), 500
# ==================== ROUTES: ACTIVE LIVENESS CHALLENGE ====================

@app.route('/api/get_challenge', methods=['POST'])
def api_get_challenge():
    """
    Generate a random liveness challenge.
    Called by frontend AFTER face verification passes.
    """
    # Verify that face verification has passed
    if session.get('login_stage') != 'face_verified':
        return jsonify({
            'success': False,
            'error': 'Complete face verification first.'
        }), 403
    
    if 'pending_user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Invalid session. Please restart login.'
        }), 403
    
    # Rate limit challenges
    attempts = session.get('challenge_attempts', 0)
    max_att = CHALLENGE_CONFIG.get('max_attempts', 3)
    
    if attempts >= max_att:
        session.clear()
        logger.warning("Challenge attempts exhausted for session")
        return jsonify({
            'success': False,
            'error': 'Too many attempts. Please restart login.'
        }), 429
    
    # Generate challenge (avoid repeating same type)
    last_type = session.get('last_challenge_type')
    challenge = challenge_manager.generate(exclude=last_type)
    
    # Store in session
    session['active_challenge'] = challenge
    session['challenge_attempts'] = attempts + 1
    session['last_challenge_type'] = challenge['type']
    session.modified = True
    
    user_id = session.get('pending_user_id', '?')
    logger.info(
        f"Challenge issued user={user_id} type={challenge['type']} "
        f"attempt={attempts + 1}/{max_att}"
    )
    
    return jsonify({
        'success': True,
        'challenge': {
            'type': challenge['type'],
            'instruction': challenge['instruction'],
            'detail': challenge.get('detail', ''),
            'icon': challenge['icon'],
            'token': challenge['token'],
            'timeout': CHALLENGE_CONFIG['timeout_seconds'],
        }
    })


# @app.route('/api/verify_challenge_frame', methods=['POST'])
# def api_verify_challenge_frame():
#     """
#     Verify a single webcam frame against the active challenge.
#     Called repeatedly (~4 fps) while user performs the challenge.
#     """
#     # Verify state
#     if session.get('login_stage') != 'face_verified':
#         return jsonify({'success': False, 'error': 'Invalid state'}), 403
    
#     challenge = session.get('active_challenge')
#     if not challenge:
#         return jsonify({'success': False, 'error': 'No active challenge'}), 403
    
#     # Verify token
#     data = request.get_json(force=True)
#     token = data.get('token', '')
    
#     if token != challenge['token']:
#         logger.warning("Challenge token mismatch")
#         return jsonify({'success': False, 'error': 'Invalid token'}), 403
    
#     # Decode frame (base64 -> BGR -> RGB)
#     frame_b64 = data.get('frame', '')
#     frame_rgb = None
#     try:
#         if ',' in frame_b64:
#             frame_b64 = frame_b64.split(',')[1]
#         frame_bytes = base64.b64decode(frame_b64)
#         frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
#         frame_bgr = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
#         if frame_bgr is not None:
#             frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
#     except Exception as e:
#         logger.error(f"Challenge frame decode failed: {e}")
    
#     if frame_rgb is None:
#         return jsonify({'success': False, 'error': 'Bad frame data'}), 400
    
#     # Get enrolled encodings for identity re-check
#     user_id = session.get('pending_user_id')
#     # enrolled = get_enrolled_encodings(user_id) if user_id else None
    
#     # Process frame against challenge
#     # result = challenge_manager.process_frame(frame_rgb, challenge, enrolled)
#     result = challenge_manager.process_frame(frame_rgb, challenge, None)
#     # Save updated challenge state back to session
#     session['active_challenge'] = challenge
#     session.modified = True
    
#     # === Handle outcomes ===
    
#     if result['status'] == 'passed':
#         # FULL LOGIN SUCCESS — authenticate now
#         verify_session_id = session.get('verify_session_id', '')
        
#         session['login_stage'] = 'challenge_passed'
#         session.permanent = True
#         session['user_id'] = user_id
#         session['verified_face'] = True
#         session.pop('active_challenge', None)
#         session.pop('pending_user_id', None)
        
#         # Update last login timestamp
#         db = get_db()
#         db.update_last_login(user_id)
        
#         logger.info(f"LOGIN SUCCESS user={user_id} (challenge={challenge['type']})")
        
#         return jsonify({
#             'success': True,
#             'status': 'passed',
#             'message': result['message'],
#             'redirect': '/dashboard',
#         })
    
#     if result['status'] == 'expired':
#         session.pop('active_challenge', None)
#         return jsonify({
#             'success': False,
#             'status': 'expired',
#             'message': result['message'],
#         })
    
#     if result['status'] == 'face_mismatch':
#         return jsonify({
#             'success': False,
#             'status': 'face_mismatch',
#             'message': result['message'],
#         })
    
#     # Still in progress — send status update
#     return jsonify({
#         'success': True,
#         'status': result['status'],
#         'message': result['message'],
#         'progress': result.get('progress', 0),
#         'remaining': round(challenge_manager.time_remaining(challenge), 1),
#     })

# @app.route('/api/verify_challenge_frame', methods=['POST'])
# def api_verify_challenge_frame():
#     """
#     Verify a single webcam frame against the active challenge.
#     Called repeatedly (~4 fps) while user performs the challenge.
    
#     Optimized:
#     - Session writes only when state changes (reduces ~20ms lag per frame)
#     - Proper numpy type conversion for JSON serialization
#     - Full error handling (never crashes, returns friendly error)
#     """
#     try:
#         # Verify state
#         if session.get('login_stage') != 'face_verified':
#             return jsonify({'success': False, 'error': 'Invalid state'}), 403
        
#         challenge = session.get('active_challenge')
#         if not challenge:
#             return jsonify({'success': False, 'error': 'No active challenge'}), 403
        
#         # Verify token
#         data = request.get_json(force=True)
#         token = data.get('token', '')
        
#         if token != challenge.get('token', ''):
#             return jsonify({'success': False, 'error': 'Invalid token'}), 403
        
#         # Decode frame (base64 -> BGR -> RGB)
#         frame_b64 = data.get('frame', '')
#         frame_rgb = None
#         try:
#             if ',' in frame_b64:
#                 frame_b64 = frame_b64.split(',')[1]
#             frame_bytes = base64.b64decode(frame_b64)
#             frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
#             frame_bgr = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
#             if frame_bgr is not None:
#                 frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
#         except Exception as e:
#             logger.error(f"Frame decode error: {e}")
        
#         if frame_rgb is None:
#             return jsonify({'success': False, 'error': 'Bad frame'}), 400
        
#         # Get user_id from session
#         user_id = session.get('pending_user_id')
        
#         # Process frame — no identity check (face already verified)
#         result = challenge_manager.process_frame(frame_rgb, challenge, None)
        
#         # ── Smart session save ──
#         # Only write to session when state actually changed
#         # This saves ~20ms per frame on unchanged frames
#         state = challenge.get('state', {})
#         current_status = result.get('status', '')
#         last_status = state.get('last_status', '')
        
#         state_changed = (
#             current_status != last_status or
#             current_status == 'passed' or
#             current_status == 'expired'
#         )
        
#         if state_changed:
#             state['last_status'] = current_status
            
#             # Convert numpy types to plain Python for JSON serialization
#             # (numpy.float64 cannot be serialized by Flask session)
#             if 'ratio_history' in state:
#                 state['ratio_history'] = [float(x) for x in state['ratio_history']]
#             if 'challenge_count' in state:
#                 state['challenge_count'] = float(state['challenge_count'])
#             if 'neutral_count' in state:
#                 state['neutral_count'] = float(state['neutral_count'])
            
#             session['active_challenge'] = challenge
#             session.modified = True
        
#         # ── Handle: PASSED ──
#         if result['status'] == 'passed':
#             # FULL LOGIN SUCCESS — authenticate now
#             session['login_stage'] = 'challenge_passed'
#             session.permanent = True
#             session['user_id'] = user_id
#             session['verified_face'] = True
#             session.pop('active_challenge', None)
#             session.pop('pending_user_id', None)
            
#             db = get_db()
#             db.update_last_login(user_id)
            
#             logger.info(f"LOGIN SUCCESS user={user_id} (challenge={challenge['type']})")
            
#             return jsonify({
#                 'success': True,
#                 'status': 'passed',
#                 'message': result['message'],
#                 'redirect': '/dashboard',
#             })
        
#         # ── Handle: EXPIRED ──
#         if result['status'] == 'expired':
#             session.pop('active_challenge', None)
#             return jsonify({
#                 'success': False,
#                 'status': 'expired',
#                 'message': result['message'],
#             })
        
#         # ── Handle: FACE MISMATCH ──
#         if result['status'] == 'face_mismatch':
#             return jsonify({
#                 'success': False,
#                 'status': 'face_mismatch',
#                 'message': result['message'],
#             })
        
#         # ── Handle: IN PROGRESS ──
#         return jsonify({
#             'success': True,
#             'status': result['status'],
#             'message': result['message'],
#             'progress': result.get('progress', 0),
#             'remaining': round(challenge_manager.time_remaining(challenge), 1),
#         })
    
#     except Exception as e:
#         logger.error(f"Challenge error: {e}", exc_info=True)
#         return jsonify({
#             'success': False,
#             'error': 'Please retry.',
#             'status': 'error'
#         }), 500

@app.route('/api/verify_challenge_frame', methods=['POST'])
def api_verify_challenge_frame():
    try:
        if session.get('login_stage') != 'face_verified':
            return jsonify({'success': False, 'error': 'Invalid state'}), 403

        challenge = session.get('active_challenge')
        if not challenge:
            return jsonify({'success': False, 'error': 'No active challenge'}), 403

        data = request.get_json(force=True)
        if data.get('token', '') != challenge.get('token', ''):
            return jsonify({'success': False, 'error': 'Invalid token'}), 403

        # ── Decode frame ──────────────────────────────────────────
        frame_b64 = data.get('frame', '')
        frame_bgr = None
        frame_rgb = None
        try:
            if ',' in frame_b64:
                frame_b64 = frame_b64.split(',')[1]
            raw = base64.b64decode(frame_b64)
            arr = np.frombuffer(raw, dtype=np.uint8)
            frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame_bgr is not None:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        except Exception as e:
            logger.error(f"Frame decode error: {e}")

        if frame_rgb is None:
            return jsonify({'success': False, 'error': 'Bad frame'}), 400

        user_id = session.get('pending_user_id')
        state   = challenge.get('state', {})

        # ── Read config values ────────────────────────────────────
        cfg = CHALLENGE_CONFIG
        check_interval     = cfg['identity_check_interval']
        min_checks         = cfg['identity_min_checks']
        required_ratio     = cfg['identity_match_ratio']
        max_consec_fails   = cfg['identity_max_consecutive_fails']

        # ── Identity tracking state ──────────────────────────────
        frame_count      = state.get('_id_frame_count', 0) + 1
        identity_checks  = state.get('_id_checks', 0)
        identity_matches = state.get('_id_matches', 0)
        consec_fails     = state.get('_id_consec_fails', 0)
        state['_id_frame_count'] = frame_count

        identity_checked_now = False

        # ═══════════════════════════════════════════════════════════
        # PERIODIC IDENTITY CHECK
        # ═══════════════════════════════════════════════════════════
        if frame_count % check_interval == 1:
            checked, matched, dist = _challenge_identity_check(frame_bgr, user_id)

            if checked:
                identity_checks += 1
                if matched:
                    identity_matches += 1
                    consec_fails = 0
                else:
                    consec_fails += 1

                state['_id_checks']       = identity_checks
                state['_id_matches']      = identity_matches
                state['_id_consec_fails'] = consec_fails
                state['_id_last_dist']    = round(dist, 4) if dist is not None else None
                identity_checked_now      = True

                logger.info(
                    f"[CHALLENGE-ID] user={user_id} check#{identity_checks}: "
                    f"dist={dist:.4f} threshold={CHALLENGE_CONFIG['identity_threshold']:.4f} "
                    f"{'✅ MATCH' if matched else '❌ MISMATCH'} "
                    f"running={identity_matches}/{identity_checks} "
                    f"({(identity_matches/identity_checks*100):.0f}%) "
                    f"consec_fails={consec_fails}"
                )

                # ── Early reject: consecutive failures ────────
                if consec_fails >= max_consec_fails:
                    logger.warning(
                        f"[CHALLENGE-ID] EARLY REJECT user={user_id}: "
                        f"{consec_fails} consecutive identity failures"
                    )
                    db = get_db()
                    db.log_verification_attempt(
                        user_id, 'challenge', False,
                        match_distance=dist,
                        error_reason='challenge_identity_consecutive_fail',
                        ip_address=get_client_ip(),
                        user_agent=get_user_agent(),
                        session_id=session.get('verify_session_id')
                    )
                    session.pop('active_challenge', None)
                    session.pop('login_stage', None)

                    return jsonify({
                        'success': False,
                        'status': 'face_mismatch',
                        'message': 'Face identity verification failed during challenge. '
                                   'The person does not match the enrolled face.',
                    })

        challenge['state'] = state

        # ── Process challenge action ──────────────────────────────
        result = challenge_manager.process_frame(frame_rgb, challenge, None)

        # ── Guard: process_frame returned None (face not found, etc.) ──
        if result is None:
            return jsonify({
                'success': True,
                'status': 'no_face',
                'message': 'Position your face in the frame',
                'progress': 0,
                'remaining': round(challenge_manager.time_remaining(challenge), 1),
                'identity': {
                    'checks': identity_checks,
                    'matches': identity_matches,
                    'ratio': round(identity_matches / identity_checks, 2) if identity_checks > 0 else None,
                    'last_distance': state.get('_id_last_dist'),
                    'status': 'matching' if identity_checks > 0 and identity_matches == identity_checks else 'partial',
                } if identity_checks > 0 else None
            })
        
        # ── Smart session save ────────────────────────────────────
        current_status = result.get('status', '')
        last_status    = state.get('last_status', '')
        state_changed  = (
            current_status != last_status
            or current_status in ('passed', 'expired')
            or identity_checked_now
        )

        if state_changed:
            state['last_status'] = current_status
            for key in ('ratio_history',):
                if key in state:
                    state[key] = [float(x) for x in state[key]]
            for key in ('challenge_count', 'neutral_count'):
                if key in state:
                    state[key] = float(state[key])
            session['active_challenge'] = challenge
            session.modified = True

        # ══════════════════════════════════════════════════════════
        # Handle: PASSED — gate on identity
        # ══════════════════════════════════════════════════════════
        if result['status'] == 'passed':

            # Final check if not enough periodic checks happened
            if identity_checks < min_checks:
                checked, matched, dist = _challenge_identity_check(frame_bgr, user_id)
                if checked:
                    identity_checks += 1
                    if matched:
                        identity_matches += 1
                    logger.info(
                        f"[CHALLENGE-ID] Final check user={user_id}: "
                        f"dist={dist:.4f} match={matched} "
                        f"total={identity_matches}/{identity_checks}"
                    )

            # ── IDENTITY GATE ─────────────────────────────────
            if identity_checks == 0:
                logger.warning(
                    f"[CHALLENGE-ID] BLOCKED user={user_id}: "
                    f"zero identity checks completed"
                )
                session.pop('active_challenge', None)
                session.pop('login_stage', None)
                return jsonify({
                    'success': False,
                    'status': 'face_mismatch',
                    'message': 'Could not verify face identity during challenge. '
                               'Please ensure good lighting and try again.',
                })

            ratio = identity_matches / identity_checks
            if ratio < required_ratio:
                logger.warning(
                    f"[CHALLENGE-ID] BLOCKED user={user_id}: "
                    f"ratio={ratio:.0%} ({identity_matches}/{identity_checks}) "
                    f"< required {required_ratio:.0%}"
                )
                db = get_db()
                db.log_verification_attempt(
                    user_id, 'challenge', False,
                    match_distance=state.get('_id_last_dist', 0),
                    error_reason='challenge_identity_final_fail',
                    ip_address=get_client_ip(),
                    user_agent=get_user_agent(),
                    session_id=session.get('verify_session_id')
                )
                session.pop('active_challenge', None)
                session.pop('login_stage', None)
                return jsonify({
                    'success': False,
                    'status': 'face_mismatch',
                    'message': 'Face identity verification failed during challenge. '
                               'Please try again.',
                })

            # ✅ FULL LOGIN SUCCESS
            session['login_stage']   = 'challenge_passed'
            session.permanent        = True
            session['user_id']       = user_id
            session['verified_face'] = True
            session.pop('active_challenge', None)
            session.pop('pending_user_id', None)

            db = get_db()
            db.update_last_login(user_id)

            logger.info(
                f"LOGIN SUCCESS user={user_id} "
                f"(challenge={challenge['type']}, "
                f"identity={identity_matches}/{identity_checks} = {ratio:.0%})"
            )

            return jsonify({
                'success': True,
                'status': 'passed',
                'message': result['message'],
                'redirect': '/dashboard',
            })

        # ── Handle: EXPIRED ──────────────────────────────────────
        if result['status'] == 'expired':
            session.pop('active_challenge', None)
            return jsonify({
                'success': False,
                'status': 'expired',
                'message': result['message'],
            })

        # ── Handle: FACE MISMATCH ────────────────────────────────
        if result['status'] == 'face_mismatch':
            return jsonify({
                'success': False,
                'status': 'face_mismatch',
                'message': result['message'],
            })

        # ── Handle: IN PROGRESS ──────────────────────────────────
        return jsonify({
            'success': True,
            'status': result['status'],
            'message': result['message'],
            'progress': result.get('progress', 0),
            'remaining': round(challenge_manager.time_remaining(challenge), 1),
        })

    except Exception as e:
        logger.error(f"Challenge error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Please retry.',
            'status': 'error'
        }), 500
        
@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    """Logout user."""
    user_id = session.get('user_id')
    session.clear()
    logger.info(f"User logged out: {user_id}")
    return jsonify({'success': True, 'message': 'Logged out'}), 200

# ==================== ROUTES: ENROLLMENT ====================

@app.route('/enroll')
def enroll_page():
    """Enrollment page."""
    return render_template('enroll.html')

@app.route('/api/enrollment/start', methods=['POST'])
def api_enrollment_start():
    """
    Step 1: Start enrollment session.
    Client provides user_id and password.
    """
    data = request.json
    user_id = data.get('user_id', '').strip()
    password = data.get('password', '').strip()
    
    if not user_id or not password:
        return jsonify({'success': False, 'error': 'User ID and password required'}), 400
    
    db = get_db()
    user = db.get_user(user_id)
    
    if not user or not verify_password(user['password_hash'], password):
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    if user['is_enrolled']:
        return jsonify({
            'success': False,
            'error': 'User already enrolled. Contact admin to re-enroll.'
        }), 409
    
    # Clear any old sessions and create new one
    db.clear_old_enrollment_sessions(user_id)
    session_id = db.create_enrollment_session(user_id)
    
    logger.info(f"Enrollment started for user {user_id}, session: {session_id}")
    
    return jsonify({
        'success': True,
        'message': f'Enrollment started. Please capture {ENROLLMENT_TARGET_SAMPLES} face samples.',
        'session_id': session_id,
        'target_samples': ENROLLMENT_TARGET_SAMPLES,
        'min_samples': ENROLLMENT_MIN_SAMPLES
    }), 200

@app.route('/api/enrollment/capture', methods=['POST'])
def api_enrollment_capture():
    """
    Step 2: Process captured frames and accumulate embeddings.
    Client sends frames from enrollment capture.
    """
    data = request.json
    session_id = data.get('session_id', '').strip()
    frames_b64 = data.get('frames', [])
    
    if not session_id or not frames_b64:
        return jsonify({'success': False, 'error': 'Session ID and frames required'}), 400
    
    db = get_db()
    enroll_session = db.get_enrollment_session(session_id)
    
    if not enroll_session:
        return jsonify({'success': False, 'error': 'Invalid enrollment session'}), 401
    
    user_id = enroll_session['user_id']
    
    try:
        # Decode frames
        frames = []
        for frame_b64 in frames_b64:
            try:
                if ',' in frame_b64:
                    frame_b64 = frame_b64.split(',')[1]
                frame_bytes = base64.b64decode(frame_b64)
                frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.append(frame)
            except Exception as e:
                logger.warning(f"Failed to decode frame in enrollment: {e}")
                continue
        
        if not frames:
            return jsonify({'success': False, 'error': 'No valid frames'}), 400
        
        # Process frames
        detector = FaceDetector()
        recognizer = FaceRecognizer()
        
        new_embeddings = []
        quality_scores_collected = []
        
        for frame in frames:
            # Validate quality
            result = validate_frame(frame, detector)
            
            if result['is_valid']:
                quality_scores_collected.append(result['quality_score'])
                
                # Get embedding
                embedding = recognizer.get_embedding(frame, result['face_location'])
                if embedding is not None:
                    new_embeddings.append(embedding)
        
        if not new_embeddings:
            logger.info(f"No valid embeddings in enrollment capture for {user_id}")
            return jsonify({
                'success': False,
                'error': ERROR_MESSAGES['low_quality'],
                'collected_samples': enroll_session['num_samples_collected'],
                'target_samples': ENROLLMENT_TARGET_SAMPLES
            }), 400
        
        # Store new embeddings
        total_samples = 0
        for embedding in new_embeddings:
            embedding_json = json.dumps(embedding.tolist())
            if db.add_face_embedding(user_id, embedding, embedding_json):
                total_samples += 1
        
        # Update session
        num_collected = enroll_session['num_samples_collected'] + total_samples
        db.update_enrollment_session(session_id, num_collected)
        
        # Check if we have enough samples
        is_complete = num_collected >= ENROLLMENT_MIN_SAMPLES
        
        logger.info(f"Enrollment capture for {user_id}: "
                   f"new={total_samples}, total={num_collected}, complete={is_complete}")
        
        response = {
            'success': True,
            'new_samples': total_samples,
            'total_samples': num_collected,
            'target_samples': ENROLLMENT_TARGET_SAMPLES,
            'min_samples': ENROLLMENT_MIN_SAMPLES,
            'is_complete': is_complete,
            'avg_quality': float(np.mean(quality_scores_collected)) if quality_scores_collected else 0
        }
        
        if is_complete:
            response['message'] = SUCCESS_MESSAGES['enrollment_complete']
        else:
            response['message'] = f'Collected {num_collected}/{ENROLLMENT_TARGET_SAMPLES} samples'
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Error in enrollment capture for {user_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': ERROR_MESSAGES['unknown_error']}), 500

@app.route('/api/enrollment/complete', methods=['POST'])
def api_enrollment_complete():
    """
    Step 3: Complete enrollment.
    Mark user as enrolled.
    """
    data = request.json
    session_id = data.get('session_id', '').strip()
    
    if not session_id:
        return jsonify({'success': False, 'error': 'Session ID required'}), 400
    
    db = get_db()
    enroll_session = db.get_enrollment_session(session_id)
    
    if not enroll_session:
        return jsonify({'success': False, 'error': 'Invalid enrollment session'}), 401
    
    user_id = enroll_session['user_id']
    num_samples = enroll_session['num_samples_collected']
    
    if num_samples < ENROLLMENT_MIN_SAMPLES:
        return jsonify({
            'success': False,
            'error': f'Not enough samples. Need at least {ENROLLMENT_MIN_SAMPLES}. '
                     f'You have {num_samples}.'
        }), 400
    
    # Mark as complete
    db.mark_enrollment_complete(user_id)
    db.complete_enrollment_session(session_id)
    
    logger.info(f"Enrollment completed for user {user_id} with {num_samples} samples")
    
    return jsonify({
        'success': True,
        'message': SUCCESS_MESSAGES['enrollment_complete'],
        'user_id': user_id
    }), 200

# ==================== ROUTES: STATUS & INFO ====================

@app.route('/api/user/profile')
@login_required
def api_user_profile():
    """Get current user profile (used by dashboard)."""
    db = get_db()
    user_id = session['user_id']
    user = db.get_user(user_id)
    embeddings_count = db.count_user_embeddings(user_id)

    return jsonify({
        'success': True,
        'user': {
            'user_id': user_id,
            'is_enrolled': bool(user['is_enrolled']),
            'is_admin': bool(user['is_admin']) if 'is_admin' in user.keys() else False,
            'face_sample_count': embeddings_count,
            'created_at': user['created_at'],
            'enrollment_completed_at': user['enrollment_completed_at'],
            'maintenance_mode': ADMIN_MAINTENANCE_MODE,
        }
    }), 200


@app.route('/api/user/status')
@login_required
def api_user_status():
    """Get current user status."""
    db = get_db()
    user_id = session['user_id']
    user = db.get_user(user_id)
    embeddings_count = db.count_user_embeddings(user_id)
    
    return jsonify({
        'user_id': user_id,
        'is_enrolled': bool(user['is_enrolled']),
        'is_admin': bool(user['is_admin']) if 'is_admin' in user.keys() else False,
        'embeddings_count': embeddings_count,
        'created_at': user['created_at'],
        'enrollment_completed_at': user['enrollment_completed_at'],
        'emergency_bypass': bool(session.get('emergency_bypass', False))  # Show maintenance warning
    }), 200

@app.route('/api/config')
def api_config():
    """Get public configuration."""
    return jsonify({
        'frame_width': 640,
        'frame_height': 480,
        'enrollment_target_samples': ENROLLMENT_TARGET_SAMPLES,
        'enrollment_min_samples': ENROLLMENT_MIN_SAMPLES,
        'login_capture_duration': LOGIN_CAPTURE_DURATION_SECONDS,
        'login_min_frames': LOGIN_MIN_FRAMES
    }), 200

# ==================== ROUTES: ADMIN PANEL ====================

@app.route('/admin', strict_slashes=False)
@admin_required
def admin_panel():
    """Admin dashboard page."""
    return render_template('admin.html')

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    """Get system statistics."""
    db = get_db()
    stats = db.get_system_stats()
    return jsonify({
        'success': True,
        'stats': stats
    }), 200

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    """Get all users list."""
    db = get_db()
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    users = db.get_all_users_admin(include_inactive=include_inactive)
    return jsonify({
        'success': True,
        'users': users
    }), 200

@app.route('/api/admin/user/<user_id>', methods=['GET'])
@admin_required
def api_admin_user_detail(user_id):
    """Get detailed user information."""
    db = get_db()
    user = db.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Get additional info
    embeddings = db.get_user_embeddings(user_id)
    logs = db.get_user_verification_logs(user_id, limit=50)
    
    return jsonify({
        'success': True,
        'user': dict(user),
        'num_embeddings': len(embeddings),
        'recent_logs': logs
    }), 200

@app.route('/api/admin/user/<user_id>/toggle-status', methods=['POST'])
@admin_required
def api_admin_toggle_user_status(user_id):
    """Enable or disable a user account."""
    if user_id == session['user_id']:
        return jsonify({'success': False, 'error': 'Cannot disable your own account'}), 400
    
    db = get_db()
    data = request.json
    is_active = data.get('is_active', True)
    
    success = db.toggle_user_status(user_id, is_active)
    
    if success:
        action = 'enabled' if is_active else 'disabled'
        logger.info(f"Admin {session['user_id']} {action} user {user_id}")
        return jsonify({
            'success': True,
            'message': f'User {action} successfully'
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/api/admin/user/<user_id>/toggle-admin', methods=['POST'])
@admin_required
def api_admin_toggle_admin_status(user_id):
    """Grant or revoke admin privileges."""
    if user_id == session['user_id']:
        return jsonify({'success': False, 'error': 'Cannot modify your own admin status'}), 400
    
    db = get_db()
    data = request.json
    is_admin = data.get('is_admin', False)
    
    success = db.set_admin_status(user_id, is_admin)
    
    if success:
        action = 'granted' if is_admin else 'revoked'
        logger.info(f"Admin {session['user_id']} {action} admin privileges for user {user_id}")
        return jsonify({
            'success': True,
            'message': f'Admin privileges {action} successfully'
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/api/admin/user/<user_id>/toggle-face-verification', methods=['POST'])
@admin_required
def api_admin_toggle_face_verification(user_id):
    """Enable or disable biometric verification requirement for a user."""
    db = get_db()
    user = db.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    data = request.json or {}
    enabled = bool(data.get('enabled', True))
    success = db.set_face_verification_enabled(user_id, enabled)
    if not success:
        return jsonify({'success': False, 'error': 'Failed to update setting'}), 500

    status_text = 'enabled' if enabled else 'disabled'
    db.log_verification_attempt(
        user_id,
        'admin_action',
        True,
        error_reason=f'face_verification_{status_text}_by_{session["user_id"]}',
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
    )
    logger.info(
        f"Admin {session['user_id']} {status_text} face verification for user {user_id}"
    )

    return jsonify({
        'success': True,
        'message': f'Face verification {status_text} for {user_id}',
        'face_verification_enabled': enabled,
    }), 200

@app.route('/api/admin/user/<user_id>/edit', methods=['POST'])
@admin_required
def api_admin_edit_user(user_id):
    """Edit user profile fields (user_id, password, email)."""
    db = get_db()
    existing_user = db.get_user(user_id)
    if not existing_user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    data = request.json or {}
    new_user_id = (data.get('new_user_id') or '').strip()
    if new_user_id == '':
        new_user_id = None

    new_password = data.get('new_password')
    if new_password is None:
        new_password = ''
    new_password = new_password.strip()

    if new_password and len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    password_hash = hash_password(new_password) if new_password else None

    # If email key is omitted, leave unchanged. If present (even empty), update it.
    email_provided = 'email' in data
    new_email = data.get('email') if email_provided else None

    try:
        final_user_id = db.update_user_profile(
            user_id,
            new_user_id=new_user_id,
            new_password_hash=password_hash,
            new_email=new_email,
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        logger.error(f"Admin edit user failed for {user_id}: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to update user'}), 500

    if session.get('user_id') == user_id and final_user_id != user_id:
        session['user_id'] = final_user_id

    change_parts = []
    if final_user_id != user_id:
        change_parts.append(f"user_id {user_id} -> {final_user_id}")
    if password_hash:
        change_parts.append('password changed')
    if email_provided:
        change_parts.append('email updated')
    change_summary = ', '.join(change_parts) if change_parts else 'no changes'

    db.log_verification_attempt(
        final_user_id,
        'admin_action',
        True,
        error_reason=f'edit_user_by_{session["user_id"]}',
        ip_address=get_client_ip(),
        user_agent=get_user_agent(),
    )
    logger.info(f"Admin {session['user_id']} edited user {user_id}: {change_summary}")

    return jsonify({
        'success': True,
        'message': f'User updated ({change_summary})',
        'final_user_id': final_user_id,
    }), 200

@app.route('/api/admin/user/<user_id>/reset-enrollment', methods=['POST'])
@admin_required
def api_admin_reset_enrollment(user_id):
    """Reset a user's enrollment so they can re-enroll their face."""
    db = get_db()
    user = db.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM face_embeddings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM enrollment_sessions WHERE user_id = ?', (user_id,))
    cursor.execute('''
        UPDATE users
        SET is_enrolled = 0, enrollment_completed_at = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

    logger.info(f"Admin {session['user_id']} reset enrollment for user {user_id}")
    return jsonify({
        'success': True,
        'message': f'Enrollment reset for {user_id}. User can now re-enroll.'
    }), 200

@app.route('/api/admin/user/<user_id>/delete', methods=['DELETE'])
@admin_required
def api_admin_delete_user(user_id):
    """Delete a user account."""
    if user_id == session['user_id']:
        return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400
    
    db = get_db()
    success = db.delete_user(user_id)
    
    if success:
        logger.info(f"Admin {session['user_id']} deleted user {user_id}")
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404

@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_admin_logs():
    """Get verification logs."""
    db = get_db()
    limit = int(request.args.get('limit', 100))
    user_id = request.args.get('user_id', None)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute('''
            SELECT * FROM verification_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
    else:
        cursor.execute('''
            SELECT * FROM verification_logs
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
    
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'logs': logs
    }), 200

# ==================== FAVICON ====================

@app.route('/favicon.ico')
def favicon():
    """Return empty 204 to suppress browser 404 requests for favicon."""
    from flask import Response
    return Response(status=204)

@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def chrome_devtools():
    """Suppress Chrome DevTools 404."""
    return jsonify({}), 200

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({'error': 'Unauthorized'}), 401

# ==================== MAIN ====================

if __name__ == '__main__':
    # Initialize database
    db = get_db()
    
    # Run app
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5000, debug=debug)

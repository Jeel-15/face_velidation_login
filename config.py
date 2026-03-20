# """
# Configuration and constants for face verification system.
# All thresholds and parameters are defined here for easy tuning.
# """

# import os

# # ==================== DATABASE ====================
# DATABASE_PATH = os.environ.get('DATABASE_PATH', 'face_login.db')

# # ==================== FACE DETECTION / RECOGNITION ====================
# # Using face_recognition library (dlib-based, practical and fast)
# FACE_MODEL = 'hog'  # 'hog' for CPU, 'cnn' for GPU (slower but more accurate)
# FACE_ENCODING_MODEL = 'small'  # small or large (more accurate but slower)

# # ==================== ENROLLMENT SETTINGS ====================
# ENROLLMENT_TARGET_SAMPLES = 10  # Target number of embeddings per user
# ENROLLMENT_MIN_SAMPLES = 8     # Minimum required valid samples
# ENROLLMENT_DURATION_SECONDS = 3  # Capture window duration
# ENROLLMENT_FPS = 20  # Frames per second to process

# # ==================== QUALITY GATES ====================
# # Face size: absolute minimum face width in pixels
# # Tuning: Increase to reject small/far faces (better security, more retries).
# #         Decrease if legitimate users are often far from camera.
# MIN_FACE_SIZE = 80

# # Face size ratio: minimum face width relative to frame width
# # Tuning: Increase for stricter framing, decrease for smaller camera previews.
# MIN_FACE_SIZE_RATIO = 0.15

# # Brightness: minimum average grayscale intensity for a valid face region
# # Tuning: Increase if too many dark/underexposed spoofs pass.
# #         Decrease if real users fail in dim environments.
# MIN_BRIGHTNESS = 20

# # Brightness upper cap (overexposed/washed frames)
# # Tuning: Lower for stricter glare rejection, raise for bright offices.
# MAX_BRIGHTNESS = 240

# # Brightness variance: rejects very flat/uniform regions
# # Tuning: Increase to reject flat print/screen patches; decrease to reduce false retries.
# MIN_BRIGHTNESS_VARIANCE = 5

# # Maximum tolerated blur represented as minimum Laplacian variance.
# # (Higher Laplacian variance = sharper image in this pipeline.)
# # Tuning: Increase for stricter sharpness; decrease if low-end cameras are blocked.
# MAX_BLUR = 40

# # Face angle (yaw, pitch, roll)
# MAX_FACE_YAW = 25    # degrees
# MAX_FACE_PITCH = 25  # degrees
# MAX_FACE_ROLL = 20   # degrees

# # Multiple faces check
# MAX_FACES_ALLOWED = 1

# # ==================== ANTI-SPOOF SETTINGS ====================
# # Motion analyzer
# MOTION_ANALYSIS_FRAMES = 5  # Use last N frames for motion analysis
# MOTION_WINDOW_EXPAND_RATIO = 1.3  # Expand face window by this ratio for bg motion
# SUSPICIOUS_MOTION_RATIO = 0.7  # If bg_motion > face_motion * this, suspect spoof
# MOTION_SCORE_THRESHOLD = 0.6  # Confidence threshold for motion-based liveness

# # Texture analyzer
# TEXTURE_ANALYSIS_FOCUS_PERCENT = 0.3  # Use center 30% of face for texture analysis
# LOW_TEXTURE_THRESHOLD = 5.0  # Very low STD = likely screen/photo
# HIGH_TEXTURE_THRESHOLD = 120.0  # Very high texture = possible moire patterns
# NORMAL_TEXTURE_MIN = 10.0
# NORMAL_TEXTURE_MAX = 80.0
# TEXTURE_SCORE_THRESHOLD = 0.6

# # Overall anti-spoof decision
# # Strong liveness pass threshold
# # Tuning: Raise to be stricter (fewer false accepts, more retries), lower to be more permissive.
# # BALANCED: 0.74 allows real faces (~0.77) but rejects obvious spoofs with multi-frame analysis
# LIVENESS_STRONG_THRESHOLD = 0.74

# # Weak liveness threshold (below this = likely spoof)
# # Tuning: Raise to reject more aggressively, lower to reduce false rejects.
# # Set to 0.50 - below this is clear spoof, between 0.50-0.74 is uncertain (requires retry)
# LIVENESS_WEAK_THRESHOLD = 0.50

# # Passive anti-spoof quality gates (kept moderate to avoid blocking real users)
# # MADE STRICTER to detect mobile phone screens and printed photos
# ANTI_SPOOF_MIN_BRIGHTNESS = 25.0  # Increased from 35.0
# ANTI_SPOOF_MAX_BRIGHTNESS = 235.0  # Decreased from 220.0 (screens often too bright)
# ANTI_SPOOF_MIN_FACE_RATIO = 0.13  # Increased from 0.11 (face must be larger)
# ANTI_SPOOF_MIN_LAPLACIAN = 25.0  # Increased from 45.0 (must be sharper - real faces have more detail)

# # Replay detection thresholds (face vs background moving together)
# # MADE STRICTER to catch phones being held up
# REPLAY_MIN_MOTION = 1.5  # Increased from 1.2 (need more motion diversity)
# REPLAY_TOGETHER_RATIO = 0.75  # Decreased from 0.82 (more sensitive to synchronized movement)
# REPLAY_STRONG_SUSPECT_RATIO = 0.70  # Increased from 0.65 (stricter)

# # Motion interpretation thresholds
# MOTION_MINIMAL_MOTION_THRESHOLD = 1.0  # Increased from 0.8 (need more motion)
# MOTION_MINIMAL_SCORE_CAP = 0.40  # Decreased from 0.45 (penalize low motion more)
# MOTION_CLEAN_REPLAY_MAX = 0.35  # Decreased from 0.4 (stricter replay detection)
# MOTION_FACE_BG_DOMINANCE_MIN = 1.15  # Increased from 1.05 (face should move MORE than background)
# REPLAY_SUSPECT_SCORE_CAP = 0.20  # Decreased from 0.25 (penalize replay suspects more)

# # Texture heuristics (screen high-frequency patterns and printed-photo smoothness)
# # MADE STRICTER for screen detection
# TEXTURE_PRINT_STD_MAX = 6.0  # Decreased from 7.0 (printed photos are smoother)
# TEXTURE_PRINT_LAP_MAX = 30.0  # Decreased from 35.0 (less edge variation)
# TEXTURE_PRINT_EDGE_MAX = 0.025  # Decreased from 0.03 (stricter)
# TEXTURE_SCREEN_HF_MIN = 0.50  # Increased from 0.42 (screens have MORE high-freq patterns)
# TEXTURE_SCREEN_EDGE_MIN = 0.12  # Increased from 0.09 (screens have more edges)

# # Texture scoring shape (natural band and falloff)
# TEXTURE_NATURAL_STD_MIN = 8.0
# TEXTURE_NATURAL_STD_MAX = 65.0
# TEXTURE_STD_FALLOFF_RANGE = 80.0
# TEXTURE_LAP_BASE = 30.0
# TEXTURE_LAP_RANGE = 120.0
# TEXTURE_HF_TARGET = 0.22
# TEXTURE_HF_TOLERANCE = 0.28

# # Passive spoof fusion gates
# # MADE STRICTER to reject more aggressively
# ANTI_SPOOF_LOW_QUALITY_GATE = 0.50  # Increased from 0.45
# STRONG_SPOOF_MOTION_MAX = 0.30  # Decreased from 0.35 (lower motion = likely spoof)
# STRONG_SPOOF_TEXTURE_MAX = 0.25  # Decreased from 0.30 (abnormal texture = likely spoof)
# STRONG_SPOOF_MOTION_TEXTURE_MAX = 0.40  # Decreased from 0.45 (combined low scores = spoof)

# # Confidence labeling thresholds for testing telemetry
# ANTI_SPOOF_CONFIDENCE_HIGH_ACCEPT = 0.85  # Increased from 0.75 (must be very confident to accept)
# ANTI_SPOOF_CONFIDENCE_HIGH_REJECT = 0.35  # Increased from 0.25 (more confident rejection)

# # ==================== FACE MATCHING SETTINGS ====================
# # Comparison with stored embeddings
# # Main face match threshold (Euclidean distance in embedding space)
# # Tuning: Lower = stricter (better security, more false rejects), Higher = looser.
# # 0.6 is the dlib demo default - way too loose for production security.
# # 0.48 is strict: only very close matches pass, greatly reduces impostor risk.
# FACE_MATCH_THRESHOLD = 0.48
# MIN_MATCH_RATIO = 0.60  # At least 60% of ALL (live×stored) pairwise comparisons must match

# # -------------------- Backward-compatible aliases --------------------
# # Existing modules may still reference old names.
# MIN_FACE_SIZE_PIXELS = MIN_FACE_SIZE
# BLUR_THRESHOLD = MAX_BLUR
# FACE_MATCH_TOLERANCE = FACE_MATCH_THRESHOLD
# LIVENESS_HIGH_CONFIDENCE_THRESHOLD = LIVENESS_STRONG_THRESHOLD
# LIVENESS_LOW_CONFIDENCE_THRESHOLD = LIVENESS_WEAK_THRESHOLD

# # ==================== LOGIN VERIFICATION FLOW ====================
# LOGIN_CAPTURE_DURATION_SECONDS = 3  # Increased from 2s \u2014 gives glasses wearers more time to blink
# LOGIN_CAPTURE_FPS = 15
# LOGIN_MIN_FRAMES = 8  # Min frames server expects (frontend sends every 2nd = ~15 frames)

# # ==================== BLINK DETECTION (LIVENESS) ====================
# # Blink detection using Eye Aspect Ratio (EAR) method
# # EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
# # Eyes open: EAR ~ 0.25-0.35
# # Eyes closed: EAR ~ 0.10-0.15

# BLINK_DETECTION_ENABLED = True  # Enable blink-based liveness detection
# BLINK_EAR_THRESHOLD = 0.27       # Raised slightly: catches glasses-wearer blinks (was 0.25)
# BLINK_EAR_OPEN_THRESHOLD = 0.30  # Eyes considered open above this (was 0.28)
# BLINK_CONSEC_FRAMES_CLOSED = 1   # 1 frame enough — glasses make 2-frame streak very hard
# BLINK_CONSEC_FRAMES_OPEN = 1     # Consecutive frames with open eyes before/after blink
# BLINK_DETECTION_TIMEOUT = 7.0    # Max seconds to wait for blink
# BLINK_MIN_FRAMES = 8             # Minimum frames needed for blink detection (must match LOGIN_MIN_FRAMES)
# BLINK_COOLDOWN_FRAMES = 3        # Frames to wait after detecting blink before counting another
# BLINK_MIN_EAR_DROP = 0.05        # Reduced from 0.07 — glasses wearers have smaller EAR range
# BLINK_BASELINE_FRAMES = 5        # How many frames to measure open-eye baseline from

# # ==================== RATE LIMITING ====================
# MAX_LOGIN_ATTEMPTS_PER_HOUR = 999  # Temporarily raised for testing
# MAX_VERIFY_ATTEMPTS_PER_LOGIN = 3  # Maximum retry attempts per login session

# # ==================== SESSION & SECURITY ====================
# SESSION_TIMEOUT_MINUTES = 30
# SESSION_CHECK_INTERVAL_SECONDS = 60

# # ==================== EMERGENCY ADMIN BYPASS ====================
# # For when face verification system is broken/down
# # Set ADMIN_MAINTENANCE_MODE=true to allow admins to login with just password
# # This should ONLY be used in emergency situations!
# ADMIN_MAINTENANCE_MODE = os.environ.get('ADMIN_MAINTENANCE_MODE', 'false').lower() == 'true'

# # ==================== LOGGING ====================
# LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
# LOG_DIR = 'logs'
# LOG_FILE = os.path.join(LOG_DIR, 'verification.log')

# # Face-debug mode for threshold tuning.
# # Set DEBUG_FACE=true during testing to save failed verification frames and
# # detailed metrics (distance/blur/brightness/liveness) into logs.
# # Keep this disabled in normal production to avoid extra disk usage.
# DEBUG_FACE = os.environ.get('DEBUG_FACE', 'false').lower() == 'true'

# # Directory used when DEBUG_FACE is enabled.
# DEBUG_FRAMES_DIR = os.path.join(LOG_DIR, 'debug_frames')

# # Maximum number of frames to save per failed verification attempt.
# # Increase for deeper analysis, decrease to reduce storage usage.
# DEBUG_FACE_MAX_SAVED_FRAMES = 10

# # ==================== API RESPONSES ====================
# # User-friendly error messages
# ERROR_MESSAGES = {
#     'low_quality': 'Face quality too low. Please ensure good lighting and face is clearly visible.',
#     'multiple_faces': 'Multiple faces detected. Only one face should be in frame.',
#     'no_face': 'No face detected. Please move closer or ensure face is visible.',
#     'spoof_detected': 'Possible photo/screen detected. This may be a security check.',
#     'face_not_matched': 'Face does not match. Please try again.',
#     'invalid_credentials': 'Invalid credentials. Please try again.',
#     'too_many_attempts': 'Too many failed attempts. Please try again later.',
#     'unknown_error': 'An error occurred. Please try again.',
# }

# SUCCESS_MESSAGES = {
#     'enrollment_complete': 'Enrollment successful! You can now login with your face.',
#     'login_success': 'Login successful!',
#     'retry': 'Uncertain. Please try again - ensure good lighting and face is clearly visible.',
# }

# # ==================== FRONTEND SETTINGS ====================
# FRAME_WIDTH = 640
# FRAME_HEIGHT = 480


# # ══════════════════════════════════════════════════════════
# # ACTIVE LIVENESS CHALLENGE CONFIGURATION
# # Added for random challenge after blink detection
# # ══════════════════════════════════════════════════════════

# # CHALLENGE_CONFIG = {
# #     # Timing
# #     'timeout_seconds': 15,

# #     # Head turn detection
# #     # LOWERED from 1.5 to 1.25 — less turn needed so face stays detectable
# #     'turn_ratio_threshold': 1.25,

# #     # Look up/down detection
# #     'vertical_neutral_min': 0.27,
# #     'vertical_neutral_max': 0.43,
# #     # RAISED from 0.20 to 0.23 — less tilt needed
# #     'look_up_threshold': 0.23,
# #     # LOWERED from 0.50 to 0.47 — less tilt needed
# #     'look_down_threshold': 0.47,

# #     # Blink detection
# #     'ear_blink_threshold': 0.21,
# #     'required_blinks': 2,

# #     # State machine
# #     'min_neutral_frames': 3,
# #     # LOWERED from 3 to 2 — hold pose for fewer frames
# #     'min_challenge_frames': 2,

# #     # Security
# #     'max_attempts': 3,
# #     'face_match_tolerance': 0.50,
# #     'verify_identity_every_n': 3,

# #     # Debug — set True to see ratio values in server logs for tuning
# #     'debug': True,
# # }


# CHALLENGE_CONFIG = {
#     # Timing — 10 seconds is enough for turn/blink
#     'timeout_seconds': 10,

#     # Head turn detection
#     'turn_ratio_threshold': 1.20,

#     # Blink detection
#     'ear_blink_threshold': 0.22,
#     'required_blinks': 2,

#     # State machine
#     'min_neutral_frames': 3,
#     'min_challenge_frames': 2,

#     # No-face tolerance during action
#     'max_no_face_streak': 15,

#     # Smoothing
#     'smoothing_window': 3,

#     # Security
#     'max_attempts': 3,
#     'face_match_tolerance': 0.55,
#     'verify_identity_every_n': 3,

#     # Debug
#     'debug': True,
# }



"""
Configuration and constants for face verification system.
All thresholds and parameters are defined here for easy tuning.
"""

import os

# ==================== DATABASE ====================
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'face_login.db')

# ==================== FACE DETECTION / RECOGNITION ====================
FACE_MODEL = 'hog'  # 'hog' for CPU, 'cnn' for GPU
FACE_ENCODING_MODEL = 'small'  # small or large

# ==================== ENROLLMENT SETTINGS ====================
ENROLLMENT_TARGET_SAMPLES = 10
ENROLLMENT_MIN_SAMPLES = 8
ENROLLMENT_DURATION_SECONDS = 3
ENROLLMENT_FPS = 20

# ==================== QUALITY GATES ====================
# RELAXED to work with different cameras, lighting, and user distances

# Face size: minimum face width in pixels
# LOWERED from 80 to 55 — works when users sit further from camera
MIN_FACE_SIZE = 55

# Face size ratio: minimum face width relative to frame width
# LOWERED from 0.15 to 0.08 — works with all camera setups
MIN_FACE_SIZE_RATIO = 0.08

# Brightness: minimum average grayscale intensity
# LOWERED from 30 to 15 — works in dim rooms
MIN_BRIGHTNESS = 15

# Brightness upper cap
# RAISED from 225 to 245 — works in bright offices
MAX_BRIGHTNESS = 245

# Brightness variance: rejects flat/uniform regions
# LOWERED from 10 to 3 — works with different skin tones and lighting
MIN_BRIGHTNESS_VARIANCE = 3

# Blur: minimum Laplacian variance (higher = sharper)
# LOWERED from 100 to 25 — works with cheaper webcams
MAX_BLUR = 25

# Face angle (yaw, pitch, roll)
MAX_FACE_YAW = 30     # RAISED from 25 — more forgiving
MAX_FACE_PITCH = 30   # RAISED from 25
MAX_FACE_ROLL = 25    # RAISED from 20

# Multiple faces check
MAX_FACES_ALLOWED = 1

# ==================== ANTI-SPOOF SETTINGS ====================
# Motion analyzer
MOTION_ANALYSIS_FRAMES = 5
MOTION_WINDOW_EXPAND_RATIO = 1.3
SUSPICIOUS_MOTION_RATIO = 0.7
MOTION_SCORE_THRESHOLD = 0.6

# Texture analyzer
TEXTURE_ANALYSIS_FOCUS_PERCENT = 0.3
LOW_TEXTURE_THRESHOLD = 5.0
HIGH_TEXTURE_THRESHOLD = 120.0
NORMAL_TEXTURE_MIN = 10.0
NORMAL_TEXTURE_MAX = 80.0
TEXTURE_SCORE_THRESHOLD = 0.6

# Overall anti-spoof decision
LIVENESS_STRONG_THRESHOLD = 0.74
LIVENESS_WEAK_THRESHOLD = 0.50

# Passive anti-spoof quality gates
# RELAXED to stop blocking legitimate users
ANTI_SPOOF_MIN_BRIGHTNESS = 15.0    # LOWERED from 40 — works in dim rooms
ANTI_SPOOF_MAX_BRIGHTNESS = 245.0   # RAISED from 210 — works in bright offices
ANTI_SPOOF_MIN_FACE_RATIO = 0.06    # LOWERED from 0.13 — works when sitting far
ANTI_SPOOF_MIN_LAPLACIAN = 15.0     # LOWERED from 55 — works with cheap webcams

# Replay detection
REPLAY_MIN_MOTION = 1.5
REPLAY_TOGETHER_RATIO = 0.75
REPLAY_STRONG_SUSPECT_RATIO = 0.70

# Motion interpretation
MOTION_MINIMAL_MOTION_THRESHOLD = 1.0
MOTION_MINIMAL_SCORE_CAP = 0.40
MOTION_CLEAN_REPLAY_MAX = 0.35
MOTION_FACE_BG_DOMINANCE_MIN = 1.15
REPLAY_SUSPECT_SCORE_CAP = 0.20

# Texture heuristics
TEXTURE_PRINT_STD_MAX = 6.0
TEXTURE_PRINT_LAP_MAX = 30.0
TEXTURE_PRINT_EDGE_MAX = 0.025
TEXTURE_SCREEN_HF_MIN = 0.50
TEXTURE_SCREEN_EDGE_MIN = 0.12

# Texture scoring shape
TEXTURE_NATURAL_STD_MIN = 8.0
TEXTURE_NATURAL_STD_MAX = 65.0
TEXTURE_STD_FALLOFF_RANGE = 80.0
TEXTURE_LAP_BASE = 30.0
TEXTURE_LAP_RANGE = 120.0
TEXTURE_HF_TARGET = 0.22
TEXTURE_HF_TOLERANCE = 0.28

# Passive spoof fusion gates
ANTI_SPOOF_LOW_QUALITY_GATE = 0.50
STRONG_SPOOF_MOTION_MAX = 0.30
STRONG_SPOOF_TEXTURE_MAX = 0.25
STRONG_SPOOF_MOTION_TEXTURE_MAX = 0.40

# Confidence labeling
ANTI_SPOOF_CONFIDENCE_HIGH_ACCEPT = 0.85
ANTI_SPOOF_CONFIDENCE_HIGH_REJECT = 0.35

# ==================== FACE MATCHING SETTINGS ====================
FACE_MATCH_THRESHOLD = 0.48
MIN_MATCH_RATIO = 0.60

# Backward-compatible aliases
MIN_FACE_SIZE_PIXELS = MIN_FACE_SIZE
BLUR_THRESHOLD = MAX_BLUR
FACE_MATCH_TOLERANCE = FACE_MATCH_THRESHOLD
LIVENESS_HIGH_CONFIDENCE_THRESHOLD = LIVENESS_STRONG_THRESHOLD
LIVENESS_LOW_CONFIDENCE_THRESHOLD = LIVENESS_WEAK_THRESHOLD

# ==================== LOGIN VERIFICATION FLOW ====================
LOGIN_CAPTURE_DURATION_SECONDS = 3
LOGIN_CAPTURE_FPS = 15
LOGIN_MIN_FRAMES = 8

# ==================== BLINK DETECTION (LIVENESS) ====================
BLINK_DETECTION_ENABLED = True
BLINK_EAR_THRESHOLD = 0.27
BLINK_EAR_OPEN_THRESHOLD = 0.30
BLINK_CONSEC_FRAMES_CLOSED = 1
BLINK_CONSEC_FRAMES_OPEN = 1
BLINK_DETECTION_TIMEOUT = 7.0
BLINK_MIN_FRAMES = 8
BLINK_COOLDOWN_FRAMES = 3
BLINK_MIN_EAR_DROP = 0.05
BLINK_BASELINE_FRAMES = 5

# ==================== RATE LIMITING ====================
MAX_LOGIN_ATTEMPTS_PER_HOUR = 999  # Temporarily raised for testing
MAX_VERIFY_ATTEMPTS_PER_LOGIN = 5  # RAISED from 3 — more retries for users

# ==================== SESSION & SECURITY ====================
SESSION_TIMEOUT_MINUTES = 30
SESSION_CHECK_INTERVAL_SECONDS = 60

# ==================== EMERGENCY ADMIN BYPASS ====================
ADMIN_MAINTENANCE_MODE = os.environ.get('ADMIN_MAINTENANCE_MODE', 'false').lower() == 'true'

# ==================== LOGGING ====================
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'verification.log')

DEBUG_FACE = os.environ.get('DEBUG_FACE', 'false').lower() == 'true'
DEBUG_FRAMES_DIR = os.path.join(LOG_DIR, 'debug_frames')
DEBUG_FACE_MAX_SAVED_FRAMES = 10

# ==================== API RESPONSES ====================
ERROR_MESSAGES = {
    'low_quality': (
        'Camera could not capture your face clearly.\n'
        'Try this:\n'
        '  Move closer to the camera\n'
        '  Make sure your face is well lit (face a window or lamp)\n'
        '  Remove sunglasses or hats\n'
        '  Hold still and look directly at the camera'
    ),
    'multiple_faces': (
        'More than one face detected.\n'
        'Make sure only YOU are visible to the camera.'
    ),
    'no_face': (
        'Camera cannot see your face.\n'
        'Move closer and make sure your face is well lit.'
    ),
    'spoof_detected': (
        'Security check failed.\n'
        'Please use your real face (not a photo or video).\n'
        'Make sure you are in good lighting and blink naturally.'
    ),
    'face_not_matched': (
        'Your face did not match.\n'
        'Try this:\n'
        '  Improve your lighting (face a window or lamp)\n'
        '  Remove glasses if you enrolled without them\n'
        '  Look directly at the camera'
    ),
    'invalid_credentials': 'Wrong user ID or password. Please check and try again.',
    'too_many_attempts': (
        'Too many failed attempts.\n'
        'Please wait a few minutes and try again.'
    ),
    'unknown_error': 'Something went wrong. Please try again.',
}

SUCCESS_MESSAGES = {
    'enrollment_complete': 'Face enrollment complete! You can now login with your face.',
    'login_success': 'Login successful! Welcome back.',
    'retry': (
        'Could not verify clearly. Please try again.\n'
        'Make sure your face is well lit and look directly at the camera.'
    ),
}

# ==================== FRONTEND SETTINGS ====================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
# ══════════════════════════════════════════════════════════
# ACTIVE LIVENESS CHALLENGE CONFIGURATION
# ══════════════════════════════════════════════════════════

CHALLENGE_CONFIG = {
    # Timing
    'timeout_seconds': 15,

    # Head turn detection
    'turn_ratio_threshold': 1.30,

    # Blink detection
    # Keep threshold strict enough to avoid eye flutter, but align count with UI instruction.
    'ear_blink_threshold': 0.21,
    'required_blinks': 2,

    # State machine
    'min_neutral_frames': 2,
    'min_challenge_frames': 4,

    # No-face tolerance during action
    'max_no_face_streak': 15,

    # Smoothing
    'smoothing_window': 3,

    # Upsampling retry for face detection
    'upsample_every_n': 4,

    # Security
    'max_attempts': 5,

    # ── Identity verification during challenge ──────────────────
    # Periodically checks that the face performing the challenge
    # matches the enrolled user (prevents face-swap attack)
    'identity_check_interval': 4,                        # check every Nth frame (~1/sec at 4fps)
    'identity_min_checks': 2,                            # minimum checks needed before allowing login
    'identity_match_ratio': 0.50,                        # ≥50% of checks must match
    'identity_threshold': FACE_MATCH_THRESHOLD * 1.15,   # 15% lenient (head angled during challenge)
    'identity_max_consecutive_fails': 3,                 # 3 consecutive mismatches = early reject

    # Debug
    'debug': True,
}

# CHALLENGE_CONFIG = {
#     # Timing — 12 seconds
#     'timeout_seconds': 12,

#     # Head turn detection
#     # 1.15 = very gentle turn (barely noticeable)
#     # 'turn_ratio_threshold': 1.15,

#     # # Blink detection
#     # # 0.25 = easy to detect blinks
#     # 'ear_blink_threshold': 0.25,
    
#         # 1.22 = noticeable but comfortable turn
#     # Not too easy (blocks replay), not too hard (real users pass)
#     'turn_ratio_threshold': 1.40,

#     # Blink detection
#     # 0.22 = requires a real blink (not just eye flutter)
#     'ear_blink_threshold': 0.18,
    
#     'required_blinks': 2,

#     # State machine
#     'min_neutral_frames': 2,
#     'min_challenge_frames': 2,

#     # No-face tolerance during action
#     'max_no_face_streak': 15,

#     # Smoothing — 2 frame moving average
#     'smoothing_window': 2,

#     # Security
#     'max_attempts': 5,
#     'face_match_tolerance': 0.65,
#     'verify_identity_every_n': 8,

#     # Debug — shows ratio values in server console
#     'debug': True,
# }

# CHALLENGE_CONFIG = {
#     # Timing
#     'timeout_seconds': 15,

#     # Head turn detection
#     # 1.30 = clear deliberate turn (random sway won't reach this)
#     # User must turn AND hold for ~1 second
#     'turn_ratio_threshold': 1.30,

#     # Blink detection
#     # 0.21 = requires real deliberate blink (not eye flutter)
#     # Must close clearly and open clearly to count
#     'ear_blink_threshold': 0.21,
#     # 3 blinks required (harder than 2)
#     'required_blinks': 3,

#     # State machine
#     'min_neutral_frames': 2,
#     # 4 frames = ~1 second of sustained pose at 4 FPS
#     'min_challenge_frames': 4,

#     # No-face tolerance during action
#     'max_no_face_streak': 15,

#     # Smoothing — 3 frame window for turn detection
#     # Smoothed ratio used for pose = requires SUSTAINED turn
#     'smoothing_window': 3,

#     # Upsampling retry for face detection
#     'upsample_every_n': 4,

#     # Security
#     'max_attempts': 5,

#     # ── Identity verification during challenge ──
#     # Periodically checks that the face performing the challenge
#     # matches the enrolled user (prevents face-swap attack)
#     'identity_check_interval': 4,    # Check every 4 frames (~1 sec at 4fps)
#     'face_match_tolerance': FACE_MATCH_THRESHOLD,  # 0.48 — same threshold as login
#     'min_match_ratio': 0.50,         # At least 50% of stored encodings must match
#     'max_identity_failures': 3,      # 3 consecutive mismatches = reject
    
    
    
#     # Debug
#     'debug': True,
# }
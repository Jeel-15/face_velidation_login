
# """
# challenge.py - Active Liveness Challenge Engine

# Generates random challenges and verifies them using facial landmarks.
# Challenges: turn_left, turn_right, look_up, blink_twice
# """

# import random
# import time
# import uuid
# import logging
# import numpy as np
# import face_recognition

# logger = logging.getLogger(__name__)


# def _euclidean(a, b):
#     """2D Euclidean distance between two points."""
#     return np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# def _validate_landmarks(lm):
#     """Check that all required landmark groups exist with correct point counts."""
#     required = {
#         'chin': 17,
#         'nose_tip': 5,
#         'nose_bridge': 4,
#         'left_eye': 6,
#         'right_eye': 6,
#         'left_eyebrow': 5,
#         'right_eyebrow': 5,
#     }
#     for key, count in required.items():
#         if len(lm.get(key, [])) < count:
#             return False
#     return True


# class ChallengeManager:
#     """
#     Manages active liveness challenges.

#     Supported challenges:
#         turn_left   - turn head left
#         turn_right  - turn head right
#         look_up     - tilt head up
#         blink_twice - blink two times

#     Usage:
#         mgr = ChallengeManager(config)
#         challenge = mgr.generate()
#         result = mgr.process_frame(frame_rgb, challenge, enrolled_encodings)
#     """

#     CHALLENGES = {
#         'turn_left': {
#             'instruction': 'Gently tilt your face slightly to the LEFT',
#             'detail': 'Just a small turn — keep looking at the camera',
#             'icon': '👈',
#         },
#         'turn_right': {
#             'instruction': 'Gently tilt your face slightly to the RIGHT',
#             'detail': 'Just a small turn — keep looking at the camera',
#             'icon': '👉',
#         },
#         'blink_twice': {
#             'instruction': 'Blink your eyes TWICE slowly',
#             'detail': 'Close and open your eyes naturally, two times',
#             'icon': '👁',
#         },
#     }

#     DEFAULT_CONFIG = {
#         'timeout_seconds': 15,

#         # Head turn — how asymmetric the nose position must be
#         # Lower = easier (less turn needed), Higher = harder
#         'turn_ratio_threshold': 1.25,

#         # Look up — nose-to-eyes vertical ratio
#         # Higher value = less tilt needed (easier)
#         'look_up_threshold': 0.23,

#         # Neutral pose band (when user is looking straight)
#         'vertical_neutral_min': 0.25,
#         'vertical_neutral_max': 0.45,

#         # Turn neutral band (inverse threshold to threshold)
#         # Auto-calculated from turn_ratio_threshold

#         # Blink detection
#         'ear_blink_threshold': 0.21,
#         'required_blinks': 2,

#         # State machine — frames needed
#         'min_neutral_frames': 3,
#         'min_challenge_frames': 2,

#         # No-face tolerance during action phase
#         'max_no_face_streak': 12,

#         # Security
#         'max_attempts': 3,
#         'face_match_tolerance': 0.50,
#         'verify_identity_every_n': 3,

#         # Smoothing — prevents jitter in ratio readings
#         'smoothing_window': 3,

#         # Debug
#         'debug': False,
#     }

#     def __init__(self, config=None):
#         """Initialize with optional config dict that overrides defaults."""
#         self.config = {**self.DEFAULT_CONFIG}
#         if config:
#             self.config.update(config)

#     def generate(self, exclude=None):
#         """
#         Generate a new random challenge.

#         Args:
#             exclude: str or list of challenge types to skip

#         Returns:
#             dict with challenge info and state
#         """
#         pool = list(self.CHALLENGES.keys())

#         if exclude:
#             if isinstance(exclude, str):
#                 exclude = [exclude]
#             pool = [c for c in pool if c not in exclude]
#             if not pool:
#                 pool = list(self.CHALLENGES.keys())

#         ctype = random.SystemRandom().choice(pool)
#         info = self.CHALLENGES[ctype]

#         challenge = {
#             'type': ctype,
#             'token': uuid.uuid4().hex,
#             'created_at': time.time(),
#             'instruction': info['instruction'],
#             'detail': info.get('detail', ''),
#             'icon': info['icon'],
#             'state': {
#                 'phase': 'waiting_neutral',
#                 'neutral_count': 0,
#                 'challenge_count': 0,
#                 'blink_count': 0,
#                 'eye_was_closed': False,
#                 'frame_number': 0,
#                 'no_face_streak': 0,
#                 'ratio_history': [],
#             },
#             'completed': False,
#         }

#         logger.info(
#             "Challenge generated type=%-12s token=%s",
#             ctype, challenge['token'][:8]
#         )
#         return challenge

#     def is_expired(self, challenge):
#         """Check if challenge has timed out."""
#         elapsed = time.time() - challenge['created_at']
#         return elapsed > self.config['timeout_seconds']

#     def time_remaining(self, challenge):
#         """Get seconds remaining for this challenge."""
#         elapsed = time.time() - challenge['created_at']
#         remaining = self.config['timeout_seconds'] - elapsed
#         return max(0, remaining)

#     def process_frame(self, frame_rgb, challenge, enrolled_encodings=None):
#         """
#         Process one webcam frame against the active challenge.

#         Args:
#             frame_rgb: numpy array (H, W, 3) in RGB format
#             challenge: dict from generate()
#             enrolled_encodings: list of numpy arrays (user face encodings)

#         Returns:
#             dict with keys: status, message, progress
#         """
#         # Check expiry
#         if self.is_expired(challenge):
#             return self._result('expired', 'Time ran out. Please try again.', 0)

#         # Check if already completed
#         if challenge['completed']:
#             return self._result('passed', 'Challenge already completed.', 1.0)

#         # Increment frame counter
#         challenge['state']['frame_number'] += 1
#         state = challenge['state']

#                 # ── Detect face landmarks ──
#         # Try normal detection first, then retry with upsampling if no face found
#         landmark_list = face_recognition.face_landmarks(frame_rgb)

#         if not landmark_list:
#             # Retry: find face locations with upsampling (detects smaller/distant faces)
#             face_locs = face_recognition.face_locations(frame_rgb, number_of_times_to_upsample=2, model='hog')
#             if face_locs:
#                 landmark_list = face_recognition.face_landmarks(frame_rgb, face_locations=face_locs)

#         if not landmark_list:
#             state['no_face_streak'] = state.get('no_face_streak', 0) + 1
#             max_streak = self.config.get('max_no_face_streak', 15)

#             # During action phase — be very forgiving
#             if state['phase'] == 'awaiting_action':
#                 if state['no_face_streak'] > max_streak:
#                     return self._result(
#                         'no_face',
#                         'Move back towards the camera slowly.',
#                         0.20
#                     )
#                 current = state.get('challenge_count', 0)
#                 min_c = self.config['min_challenge_frames']
#                 p = 0.30 + 0.35 * (current / max(min_c, 1))
#                 return self._result('continue', 'Keep going... you\'re doing great!', p)

#             if state['no_face_streak'] > 8:
#                 return self._result('no_face', 'Move closer and look at the camera.', 0)

#             return self._result('continue', 'Look at the camera...', 0.05)
#         # Face detected — reset no-face streak
#         state['no_face_streak'] = 0

#         lm = landmark_list[0]
#         if not _validate_landmarks(lm):
#             if state['phase'] == 'awaiting_action':
#                 return self._result('continue', 'Keep going...', 0.30)
#             return self._result('no_face', 'Face partially hidden. Show your full face.', 0)

#         # Identity verification (periodic)
#         # if enrolled_encodings is not None:
#         #     n = self.config['verify_identity_every_n']
#         #     frame_num = state['frame_number']
#         #     if frame_num % n == 1:
#         #         encs = face_recognition.face_encodings(frame_rgb)
#         #         if encs:
#         #             distances = face_recognition.face_distance(enrolled_encodings, encs[0])
#         #             best_distance = min(distances)
#         #             if best_distance > self.config['face_match_tolerance']:
#         #                 logger.warning(
#         #                     "Identity mismatch during challenge (dist=%.3f)",
#         #                     best_distance
#         #                 )
#         #                 return self._result(
#         #                     'face_mismatch',
#         #                     'Face does not match. Please stay in frame.',
#         #                     0
#         #                 )

#         # Route to the correct handler
#         ctype = challenge['type']

#         if ctype == 'turn_left' or ctype == 'turn_right':
#             return self._handle_turn(lm, challenge)
#         elif ctype == 'blink_twice':
#             return self._handle_blinks(lm, challenge)
#         else:
#             return self._result('error', 'Unknown challenge type.', 0)

#     # ══════════════════════════════════════════════
#     #  HEAD TURN DETECTION (left / right)
#     # ══════════════════════════════════════════════

#     def _head_turn_ratio(self, lm):
#         """
#         Calculate nose position relative to jaw edges.

#         Returns smoothed ratio:
#             ratio > 1 = nose shifted left (person turned left)
#             ratio < 1 = nose shifted right (person turned right)
#             ratio ≈ 1 = facing camera
#         """
#         chin = lm['chin']
#         nose_x = lm['nose_tip'][2][0]

#         d_left = abs(nose_x - chin[0][0])
#         d_right = abs(chin[16][0] - nose_x)

#         if d_right < 1:
#             return 99.0

#         return d_left / d_right

#     def _smooth_ratio(self, raw_ratio, state, window_key='ratio_history'):
#         """Apply moving average smoothing to reduce jitter."""
#         history = state.get(window_key, [])
#         history.append(raw_ratio)

#         window = self.config.get('smoothing_window', 3)
#         if len(history) > window:
#             history = history[-window:]

#         state[window_key] = history

#         return float(np.mean(history))

#     def _handle_turn(self, lm, challenge):
#         """Handle turn_left and turn_right challenges."""
#         raw_ratio = self._head_turn_ratio(lm)
#         ratio = self._smooth_ratio(raw_ratio, challenge['state'])

#         thresh = self.config['turn_ratio_threshold']
#         inv = 1.0 / thresh

#         # Wider neutral band for more forgiving detection
#         neutral_low = inv * 0.95    # slightly inside inverse threshold
#         neutral_high = thresh * 0.95  # slightly inside threshold

#         is_neutral = (neutral_low < ratio < neutral_high)

#         if challenge['type'] == 'turn_left':
#             is_pose = (ratio >= thresh)
#         else:
#             is_pose = (ratio <= inv)

#         if self.config['debug']:
#             logger.debug(
#                 "turn  raw=%.3f  smoothed=%.3f  thresh=%.2f  neutral=%s  pose=%s",
#                 raw_ratio, ratio, thresh, is_neutral, is_pose
#             )

#         return self._advance(challenge, is_neutral, is_pose)

#     # ══════════════════════════════════════════════
#     #  VERTICAL TILT DETECTION (up only)
#     # ══════════════════════════════════════════════

#     def _vertical_ratio(self, lm):
#         """
#         Calculate vertical head tilt.
#         Smaller value = looking up.
#         Larger value = looking down.
#         """
#         l_eye = np.mean(lm['left_eye'], axis=0)
#         r_eye = np.mean(lm['right_eye'], axis=0)
#         eyes_y = (l_eye[1] + r_eye[1]) / 2.0

#         nose_y = lm['nose_tip'][2][1]
#         chin_y = lm['chin'][8][1]

#         brows = lm['left_eyebrow'] + lm['right_eyebrow']
#         brow_y = min(p[1] for p in brows)

#         face_h = chin_y - brow_y
#         if face_h < 1:
#             return 0.35

#         return (nose_y - eyes_y) / face_h

#     def _handle_tilt(self, lm, challenge):
#         """Handle look_up challenge."""
#         raw_ratio = self._vertical_ratio(lm)
#         ratio = self._smooth_ratio(raw_ratio, challenge['state'], 'tilt_history')

#         n_lo = self.config['vertical_neutral_min']
#         n_hi = self.config['vertical_neutral_max']

#         is_neutral = (n_lo < ratio < n_hi)
#         is_pose = (ratio < self.config['look_up_threshold'])

#         if self.config['debug']:
#             logger.debug(
#                 "tilt  raw=%.3f  smoothed=%.3f  up_thresh=%.2f  neutral=%s  pose=%s",
#                 raw_ratio, ratio, self.config['look_up_threshold'], is_neutral, is_pose
#             )

#         return self._advance(challenge, is_neutral, is_pose)

#     # ══════════════════════════════════════════════
#     #  BLINK TWICE DETECTION
#     # ══════════════════════════════════════════════

#     def _ear(self, eye_pts):
#         """
#         Calculate Eye Aspect Ratio (EAR).
#         Low EAR = eye closed.
#         """
#         p = eye_pts
#         v1 = _euclidean(p[1], p[5])
#         v2 = _euclidean(p[2], p[4])
#         h = _euclidean(p[0], p[3])
#         if h == 0:
#             return 0.0
#         return (v1 + v2) / (2.0 * h)

#     def _handle_blinks(self, lm, challenge):
#         """Handle blink_twice challenge."""
#         left_ear = self._ear(lm['left_eye'])
#         right_ear = self._ear(lm['right_eye'])
#         avg_ear = (left_ear + right_ear) / 2.0

#         state = challenge['state']
#         thresh = self.config['ear_blink_threshold']
#         required = self.config['required_blinks']

#         # Detect open -> closed -> open transitions
#         if avg_ear < thresh:
#             if not state['eye_was_closed']:
#                 state['eye_was_closed'] = True
#                 if self.config['debug']:
#                     logger.debug("Eyes CLOSED  EAR=%.3f (below %.3f)", avg_ear, thresh)
#         else:
#             if state['eye_was_closed']:
#                 state['blink_count'] += 1
#                 state['eye_was_closed'] = False
#                 logger.info("Blink #%d detected  EAR=%.3f", state['blink_count'], avg_ear)

#         progress = min(state['blink_count'] / required, 1.0)

#         if state['blink_count'] >= required:
#             challenge['completed'] = True
#             return self._result(
#                 'passed',
#                 '{} blinks detected. Challenge passed!'.format(required),
#                 1.0
#             )

#         # Show progress with clear message
#         remaining_blinks = required - state['blink_count']
#         if state['blink_count'] == 0:
#             msg = 'Blink your eyes slowly... ({} blinks needed)'.format(required)
#         else:
#             msg = 'Good! {} more blink{} needed'.format(
#                 remaining_blinks,
#                 's' if remaining_blinks > 1 else ''
#             )

#         return self._result(
#             'continue',
#             msg,
#             0.3 + 0.7 * progress
#         )

#     # ══════════════════════════════════════════════
#     #  STATE MACHINE (neutral → pose)
#     # ══════════════════════════════════════════════

#     def _advance(self, challenge, is_neutral, is_challenge_pose):
#         """
#         Two-phase state machine:
#         Phase 1: Accumulate neutral frames (user facing camera)
#         Phase 2: Accumulate challenge pose frames (user performing action)

#         Refined behavior:
#         - Progress never drops below phase minimum
#         - Challenge count decreases slowly (not instantly)
#         - Clear feedback messages at each stage
#         """
#         state = challenge['state']
#         min_n = self.config['min_neutral_frames']
#         min_c = self.config['min_challenge_frames']

#         # Phase 1: waiting for neutral position
#         if state['phase'] == 'waiting_neutral':
#             if is_neutral:
#                 state['neutral_count'] += 1
#             else:
#                 # Slow decay — don't punish brief glances away
#                 state['neutral_count'] = max(0, state['neutral_count'] - 1)

#             if state['neutral_count'] >= min_n:
#                 state['phase'] = 'awaiting_action'
#                 state['challenge_count'] = 0
#                 return self._result(
#                     'neutral_ok',
#                     'Good! Now perform the action.',
#                     0.30
#                 )

#             p = 0.05 + 0.20 * (state['neutral_count'] / max(min_n, 1))

#             if state['neutral_count'] == 0:
#                 msg = 'Look straight at the camera...'
#             else:
#                 msg = 'Hold steady... looking good'

#             return self._result('waiting_neutral', msg, p)

#         # Phase 2: waiting for challenge pose
#         if is_challenge_pose:
#             state['challenge_count'] += 1
#         else:
#             # Very slow decay — don't lose all progress from one bad frame
#             # Only decay by 0.5 per non-matching frame (effectively 1 per 2 frames)
#             state['challenge_count'] = max(0, state['challenge_count'] - 0.5)

#         effective_count = int(state['challenge_count'])

#         if effective_count >= min_c:
#             challenge['completed'] = True
#             return self._result('passed', 'Challenge passed!', 1.0)

#         if state['challenge_count'] > 0:
#             p = 0.30 + 0.70 * (state['challenge_count'] / max(min_c, 1))
#             p = min(p, 0.99)  # cap at 99% until actually passed

#             if state['challenge_count'] >= min_c * 0.6:
#                 msg = 'Almost there... hold it!'
#             else:
#                 msg = 'Detecting movement... hold the pose'

#             return self._result('detecting', msg, p)

#         return self._result('continue', 'Perform the action now!', 0.30)

#     # ══════════════════════════════════════════════
#     #  HELPER
#     # ══════════════════════════════════════════════

#     @staticmethod
#     def _result(status, message, progress=0):
#         """Create a standardized result dict."""
#         return {
#             'status': status,
#             'message': message,
#             'progress': round(float(progress), 2),
#         }


"""
challenge.py - Active Liveness Challenge Engine (Optimized)

Fast, forgiving challenge detection for real users.
Challenges: turn_left, turn_right, blink_twice
"""

import random
import time
import uuid
import logging
import numpy as np
import face_recognition

logger = logging.getLogger(__name__)


def _euclidean(a, b):
    """2D Euclidean distance between two points."""
    return np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _validate_landmarks(lm):
    """Check only essential landmark groups (reduced for reliability)."""
    required = {
        'chin': 17,
        'nose_tip': 5,
        'left_eye': 6,
        'right_eye': 6,
    }
    for key, count in required.items():
        if len(lm.get(key, [])) < count:
            return False
    return True


class ChallengeManager:
    """
    Manages active liveness challenges.

    Supported challenges:
        turn_left   - gently tilt face left
        turn_right  - gently tilt face right
        blink_twice - blink two times
    """

    CHALLENGES = {
        'turn_left': {
            'instruction': 'Gently tilt your face slightly to the LEFT',
            'detail': 'Just a small turn — keep looking at the camera',
            'icon': '👈',
        },
        'turn_right': {
            'instruction': 'Gently tilt your face slightly to the RIGHT',
            'detail': 'Just a small turn — keep looking at the camera',
            'icon': '👉',
        },
        'blink_twice': {
            'instruction': 'Slowly blink your eyes TWICE',
            'detail': 'Close and open your eyes naturally, two times',
            'icon': '👁',
        },
    }

    # DEFAULT_CONFIG = {
    #     'timeout_seconds': 15,
    #     # 'turn_ratio_threshold': 1.15,
    #     'turn_ratio_threshold': 1.40,
    #     # 'ear_blink_threshold': 0.25,
    #     'ear_blink_threshold': 0.18,
    #     'required_blinks': 2,
    #     'min_neutral_frames': 2,
    #     'min_challenge_frames': 2,
    #     'max_no_face_streak': 15,
    #     'max_attempts': 5,
    #     'smoothing_window': 2,
    #     # Upsampling retry interval (every N frames when face not found)
    #     # Higher = faster but misses more, Lower = slower but finds more
    #     'upsample_every_n': 4,
    #     'debug': False,
    # }
    DEFAULT_CONFIG = {
        'timeout_seconds': 15,
        'turn_ratio_threshold': 1.30,
        'ear_blink_threshold': 0.21,
        # Slightly easier challenge while still requiring intentional blinks.
        'required_blinks': 2,
        'min_neutral_frames': 2,
        'min_challenge_frames': 4,
        'max_no_face_streak': 15,
        'max_attempts': 5,
        'smoothing_window': 3,
        'upsample_every_n': 4,
        'debug': False,
        
    }

    def __init__(self, config=None):
        """Initialize with optional config dict that overrides defaults."""
        self.config = {**self.DEFAULT_CONFIG}
        if config:
            self.config.update(config)

    def generate(self, exclude=None):
        """Generate a new random challenge."""
        pool = list(self.CHALLENGES.keys())

        if exclude:
            if isinstance(exclude, str):
                exclude = [exclude]
            pool = [c for c in pool if c not in exclude]
            if not pool:
                pool = list(self.CHALLENGES.keys())

        ctype = random.SystemRandom().choice(pool)
        info = self.CHALLENGES[ctype]

        challenge = {
            'type': ctype,
            'token': uuid.uuid4().hex,
            'created_at': time.time(),
            'instruction': info['instruction'],
            'detail': info.get('detail', ''),
            'icon': info['icon'],
            'state': {
                'phase': 'waiting_neutral',
                'neutral_count': 0,
                'challenge_count': 0,
                'blink_count': 0,
                'eye_was_closed': False,
                'frame_number': 0,
                'no_face_streak': 0,
                'ratio_history': [],
                'last_status': '',
            },
            'completed': False,
        }

        logger.info(
            "Challenge generated type=%-12s token=%s",
            ctype, challenge['token'][:8]
        )
        return challenge

    def is_expired(self, challenge):
        """Check if challenge has timed out."""
        return (time.time() - challenge['created_at']) > self.config['timeout_seconds']

    def time_remaining(self, challenge):
        """Get seconds remaining."""
        return max(0, self.config['timeout_seconds'] - (time.time() - challenge['created_at']))

    def process_frame(self, frame_rgb, challenge, enrolled_encodings=None):
        # Check expiry
        if self.is_expired(challenge):
            return self._result('expired', 'Time ran out. Click Retry to try again.', 0)

        # Check if already completed
        if challenge['completed']:
            return self._result('passed', 'Challenge already completed.', 1.0)

        state = challenge['state']
        state['frame_number'] += 1
        frame_num = state['frame_number']

        # ── FAST face detection ──
        # Step 1: Try fast detection (no upsampling — ~60ms)
        landmark_list = face_recognition.face_landmarks(frame_rgb)

        # Step 2: Only retry with upsampling every N frames (upsampling is ~200ms)
        # This prevents lag while still catching smaller/distant faces periodically
        if not landmark_list:
            upsample_interval = self.config.get('upsample_every_n', 4)
            if frame_num % upsample_interval == 0:
                face_locs = face_recognition.face_locations(
                    frame_rgb, number_of_times_to_upsample=1, model='hog'
                )
                if face_locs:
                    landmark_list = face_recognition.face_landmarks(
                        frame_rgb, face_locations=face_locs
                    )

        # ── Handle no face ──
        if not landmark_list:
            state['no_face_streak'] = state.get('no_face_streak', 0) + 1
            max_streak = self.config.get('max_no_face_streak', 15)

            # During action phase — be very forgiving (don't reset progress)
            if state['phase'] == 'awaiting_action':
                if state['no_face_streak'] > max_streak:
                    return self._result(
                        'no_face',
                        'Move back towards the camera slowly.',
                        0.20
                    )
                # Hold current progress
                current = state.get('challenge_count', 0)
                min_c = self.config['min_challenge_frames']
                p = 0.30 + 0.35 * (current / max(min_c, 1))
                return self._result('continue', 'Keep going... you\'re doing great!', p)

            # During neutral phase — brief loss is OK
            if state['no_face_streak'] > 6:
                return self._result('no_face', 'Move closer and look at the camera.', 0)

            # Very brief loss — don't show scary error
            return self._result('continue', 'Finding your face...', 0.05)

        # ── Face found — reset streak ──
        state['no_face_streak'] = 0

        lm = landmark_list[0]
        if not _validate_landmarks(lm):
            if state['phase'] == 'awaiting_action':
                return self._result('continue', 'Keep going...', 0.30)
            return self._result('continue', 'Move slightly closer.', 0.05)

                # ── Route to challenge handler ──
        ctype = challenge['type']

        if ctype == 'turn_left' or ctype == 'turn_right':
            result = self._handle_turn(lm, challenge)
        elif ctype == 'blink_twice':
            result = self._handle_blinks(lm, challenge)
        else:
            return self._result('error', 'Unknown challenge type.', 0)
        
        return result
        # # ══════════════════════════════════════════════
        # #  FINAL IDENTITY GATE — before allowing pass
        # # ══════════════════════════════════════════════
        # if result['status'] == 'passed' and enrolled_encodings is not None:
        #     if not state.get('identity_verified', False):
        #         final_check = self._check_identity(frame_rgb, enrolled_encodings)
        #         if final_check is True:
        #             state['identity_verified'] = True
        #             logger.info("IDENTITY verified on final check — allowing pass")
        #         else:
        #             challenge['completed'] = False
        #             logger.warning(
        #                 "IDENTITY NOT CONFIRMED on final check — blocking pass"
        #             )
        #             return self._result(
        #                 'face_mismatch',
        #                 'Could not verify your identity. '
        #                 'Look straight at the camera and retry.',
        #                 0
        #             )

        # return result
    # ══════════════════════════════════════════════
    #  HEAD TURN DETECTION (left / right)
    # ══════════════════════════════════════════════

    def _head_turn_ratio(self, lm):
        """
        Calculate nose position relative to jaw edges.

        ratio > 1 = person turned LEFT (nose closer to right jaw)
        ratio < 1 = person turned RIGHT (nose closer to left jaw)
        ratio ≈ 1 = facing camera
        """
        chin = lm['chin']
        nose_x = lm['nose_tip'][2][0]

        d_left = abs(nose_x - chin[0][0])
        d_right = abs(chin[16][0] - nose_x)

        if d_right < 1:
            return 99.0
        if d_left < 1:
            return 0.01

        return d_left / d_right

    def _smooth_ratio(self, raw_ratio, state):
        """Apply moving average smoothing to reduce jitter."""
        history = state.get('ratio_history', [])
        history.append(float(raw_ratio))

        window = self.config.get('smoothing_window', 2)
        if len(history) > window:
            history = history[-window:]

        state['ratio_history'] = history
        return float(np.mean(history))

    # def _handle_turn(self, lm, challenge):
    #     """Handle turn_left and turn_right challenges."""
    #     raw_ratio = self._head_turn_ratio(lm)
    #     ratio = self._smooth_ratio(raw_ratio, challenge['state'])

    #     thresh = self.config['turn_ratio_threshold']
    #     inv = 1.0 / thresh

    #     # Wide neutral band — very forgiving
    #     neutral_low = inv * 0.85
    #     neutral_high = thresh * 0.85

    #     is_neutral = (neutral_low < ratio < neutral_high)

    #     if challenge['type'] == 'turn_left':
    #         is_pose = (ratio >= thresh)
    #     else:
    #         is_pose = (ratio <= inv)

    #     # Debug logging — uses logger.info so it ALWAYS shows in console
    #     if self.config['debug']:
    #         direction = challenge['type']
    #         target = ">={:.2f}".format(thresh) if direction == 'turn_left' else "<={:.2f}".format(inv)
    #         logger.info(
    #             "CHALLENGE-DEBUG %s raw=%.3f smooth=%.3f need=%s neutral=%s DETECTED=%s phase=%s",
    #             direction, raw_ratio, ratio, target, is_neutral, is_pose, challenge['state']['phase']
    #         )

    #     return self._advance(challenge, is_neutral, is_pose)

    # def _handle_turn(self, lm, challenge):
    #     """
    #     Handle turn_left and turn_right challenges.
        
    #     Uses RAW ratio (no smoothing) for pose detection.
    #     Smoothing kills the turn signal because it averages
    #     the turned frame with previous straight-face frames.
        
    #     Uses smoothed ratio only for neutral detection (stable).
    #     """
    #     raw_ratio = self._head_turn_ratio(lm)
    #     smoothed = self._smooth_ratio(raw_ratio, challenge['state'])

    #     thresh = self.config['turn_ratio_threshold']
    #     inv = 1.0 / thresh

    #     # Neutral detection uses SMOOTHED ratio (needs to be stable)
    #     is_neutral = (inv * 0.85 < smoothed < thresh * 0.85)

    #     # Pose detection uses RAW ratio (no smoothing — instant response)
    #     # This is the KEY fix: raw ratio responds immediately to head turn
    #     if challenge['type'] == 'turn_left':
    #         is_pose = (raw_ratio >= thresh)
    #     else:
    #         is_pose = (raw_ratio <= inv)

    #     if self.config['debug']:
    #         direction = challenge['type']
    #         target = ">={:.2f}".format(thresh) if direction == 'turn_left' else "<={:.2f}".format(inv)
    #         logger.info(
    #             "CHALLENGE-DEBUG %s raw=%.3f smooth=%.3f need=%s neutral=%s DETECTED=%s phase=%s",
    #             direction, raw_ratio, smoothed, target, is_neutral, is_pose, challenge['state']['phase']
    #         )

    #     return self._advance(challenge, is_neutral, is_pose)
    
    def _handle_turn(self, lm, challenge):
        """
        Handle turn_left and turn_right challenges.
        
        Requires DELIBERATE, SUSTAINED head turn.
        Random head sway will NOT pass.
        User must turn and HOLD for ~1 second.
        """
        raw_ratio = self._head_turn_ratio(lm)
        smoothed = self._smooth_ratio(raw_ratio, challenge['state'])

        thresh = self.config['turn_ratio_threshold']
        inv = 1.0 / thresh

        # Neutral detection uses SMOOTHED ratio (stable)
        is_neutral = (inv * 0.85 < smoothed < thresh * 0.85)

        # Pose detection: use SMOOTHED ratio
        # This means user must HOLD the turn (not just a quick jerk)
        # Smoothing requires multiple frames of consistent turning
        if challenge['type'] == 'turn_left':
            is_pose = (smoothed >= thresh)
        else:
            is_pose = (smoothed <= inv)

        if self.config['debug']:
            direction = challenge['type']
            target = ">={:.2f}".format(thresh) if direction == 'turn_left' else "<={:.2f}".format(inv)
            logger.info(
                "CHALLENGE-DEBUG %s raw=%.3f smooth=%.3f need=%s neutral=%s DETECTED=%s phase=%s",
                direction, raw_ratio, smoothed, target, is_neutral, is_pose, challenge['state']['phase']
            )

        return self._advance(challenge, is_neutral, is_pose)

    # ══════════════════════════════════════════════
    #  BLINK TWICE DETECTION
    # ══════════════════════════════════════════════

    def _ear(self, eye_pts):
        """Calculate Eye Aspect Ratio. Low EAR = eye closed."""
        p = eye_pts
        v1 = _euclidean(p[1], p[5])
        v2 = _euclidean(p[2], p[4])
        h = _euclidean(p[0], p[3])
        if h == 0:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    # def _handle_blinks(self, lm, challenge):
    #     """Handle blink_twice challenge."""
    #     left_ear = self._ear(lm['left_eye'])
    #     right_ear = self._ear(lm['right_eye'])
    #     avg_ear = (left_ear + right_ear) / 2.0

    #     state = challenge['state']
    #     thresh = self.config['ear_blink_threshold']
    #     required = self.config['required_blinks']

    #     # Debug logging — only every 3rd frame to reduce console spam
    #     if self.config['debug'] and state['frame_number'] % 3 == 0:
    #         logger.info(
    #             "CHALLENGE-DEBUG blink EAR=%.3f thresh=%.3f closed=%s count=%d/%d",
    #             avg_ear, thresh, state['eye_was_closed'], state['blink_count'], required
    #         )

    #     # Detect open -> closed -> open transitions
    #     if avg_ear < thresh:
    #         if not state['eye_was_closed']:
    #             state['eye_was_closed'] = True
    #     else:
    #         if state['eye_was_closed']:
    #             state['blink_count'] += 1
    #             state['eye_was_closed'] = False
    #             logger.info("Blink #%d detected EAR=%.3f", state['blink_count'], avg_ear)

    #     progress = min(state['blink_count'] / required, 1.0)

    #     if state['blink_count'] >= required:
    #         challenge['completed'] = True
    #         return self._result('passed', 'Challenge passed! ✓', 1.0)

    #     # Friendly progress messages
    #     remaining_blinks = required - state['blink_count']
    #     if state['blink_count'] == 0:
    #         msg = 'Blink slowly... ({} times)'.format(required)
    #     elif remaining_blinks == 1:
    #         msg = 'Great! Just 1 more blink...'
    #     else:
    #         msg = 'Good! {} more blinks needed'.format(remaining_blinks)

    #     return self._result('continue', msg, 0.3 + 0.7 * progress)

    def _handle_blinks(self, lm, challenge):
        """
        Handle blink_twice challenge.
        Requires deliberate blinks (not eye flutter).
        """
        left_ear = self._ear(lm['left_eye'])
        right_ear = self._ear(lm['right_eye'])
        avg_ear = (left_ear + right_ear) / 2.0

        state = challenge['state']
        thresh = self.config['ear_blink_threshold']
        required = self.config['required_blinks']

        # Debug logging — only every 3rd frame to reduce spam
        if self.config['debug'] and state['frame_number'] % 3 == 0:
            logger.info(
                "CHALLENGE-DEBUG blink EAR=%.3f thresh=%.3f closed=%s count=%d/%d",
                avg_ear, thresh, state['eye_was_closed'], state['blink_count'], required
            )

        # Detect open -> closed -> open transitions
        # Slightly relaxed gates: still needs a real dip and reopen,
        # but less punishing for users with glasses / small eye movement.
        close_gate = thresh * 0.94
        open_gate = thresh * 1.06

        if avg_ear < thresh:
            if not state['eye_was_closed']:
                if avg_ear < close_gate:
                    state['eye_was_closed'] = True
                    if self.config['debug']:
                        logger.info("CHALLENGE-DEBUG Eyes CLOSED EAR=%.3f (gate=%.3f)", avg_ear, close_gate)
        else:
            if state['eye_was_closed']:
                if avg_ear > open_gate:
                    state['blink_count'] += 1
                    state['eye_was_closed'] = False
                    logger.info("Blink #%d detected EAR=%.3f", state['blink_count'], avg_ear)
                else:
                    # Eyes barely reopened — ignore micro-flutter.
                    pass

        progress = min(state['blink_count'] / required, 1.0)

        if state['blink_count'] >= required:
            challenge['completed'] = True
            return self._result('passed', 'Challenge passed! ✓', 1.0)

        remaining_blinks = required - state['blink_count']
        if state['blink_count'] == 0:
            msg = 'Blink slowly and clearly... ({} times)'.format(required)
        elif remaining_blinks == 1:
            msg = 'Great! Just 1 more clear blink...'
        else:
            msg = 'Good! {} more blinks needed'.format(remaining_blinks)

        return self._result('continue', msg, 0.3 + 0.7 * progress)

    # ══════════════════════════════════════════════
    #  STATE MACHINE (neutral → pose)
    # ══════════════════════════════════════════════

    # def _advance(self, challenge, is_neutral, is_challenge_pose):
    #     """
    #     Two-phase state machine:
    #     Phase 1: User looks straight (neutral) — proves they're at the camera
    #     Phase 2: User performs the action — proves they're real

    #     Optimized:
    #     - Fast increment on correct pose (+2.0 per frame)
    #     - Very slow decay on wrong pose (-0.2 per frame)
    #     - Neutral phase also forgiving (-0.3 decay)
    #     - Never shows "error" or "failed" during attempt
    #     """
    #     state = challenge['state']
    #     min_n = self.config['min_neutral_frames']
    #     min_c = self.config['min_challenge_frames']
    #     detail = challenge.get('detail', '')

    #     # ── Phase 1: waiting for neutral ──
    #     if state['phase'] == 'waiting_neutral':
    #         if is_neutral:
    #             state['neutral_count'] += 1
    #         else:
    #             # Slow decay — don't punish brief glances away
    #             state['neutral_count'] = max(0, state['neutral_count'] - 0.3)

    #         if state['neutral_count'] >= min_n:
    #             state['phase'] = 'awaiting_action'
    #             state['challenge_count'] = 0

    #             if detail:
    #                 msg = 'Now: ' + detail
    #             else:
    #                 msg = 'Good! Now gently perform the action.'

    #             return self._result('neutral_ok', msg, 0.30)

    #         p = 0.05 + 0.20 * (state['neutral_count'] / max(min_n, 1))

    #         if state['neutral_count'] < 1:
    #             msg = 'Look straight at the camera...'
    #         else:
    #             msg = 'Good, hold steady...'

    #         return self._result('waiting_neutral', msg, p)

    #     # ── Phase 2: waiting for pose ──
    #     if is_challenge_pose:
    #         # FAST increment — reward correct pose immediately
    #         state['challenge_count'] += 2.0
    #     else:
    #         # VERY slow decay — one bad frame barely affects progress
    #         state['challenge_count'] = max(0, state['challenge_count'] - 0.2)

    #     if state['challenge_count'] >= min_c:
    #         challenge['completed'] = True
    #         return self._result('passed', 'Challenge passed! ✓', 1.0)

    #     if state['challenge_count'] > 0:
    #         p = 0.30 + 0.70 * (state['challenge_count'] / max(min_c, 1))
    #         p = min(p, 0.99)  # cap at 99% until actually passed

    #         if state['challenge_count'] >= min_c * 0.5:
    #             msg = 'Almost there... hold it!'
    #         else:
    #             msg = 'Good! Hold the position...'

    #         return self._result('detecting', msg, p)

    #     # Not detecting yet — give gentle reminder
    #     if detail:
    #         msg = detail
    #     else:
    #         msg = 'Gently perform the action now'

    #     return self._result('continue', msg, 0.30)

    def _advance(self, challenge, is_neutral, is_challenge_pose):
        """
        Two-phase state machine:
        Phase 1: User looks straight (neutral)
        Phase 2: User performs the action and HOLDS it

        Security:
        - Slow increment (+1.0 per frame) — needs sustained pose
        - Fast decay (-1.0 per frame) — stops rewarding if user stops
        - Higher min_challenge_frames — must hold for ~1 second
        """
        state = challenge['state']
        min_n = self.config['min_neutral_frames']
        min_c = self.config['min_challenge_frames']
        detail = challenge.get('detail', '')

        # ── Phase 1: waiting for neutral ──
        if state['phase'] == 'waiting_neutral':
            if is_neutral:
                state['neutral_count'] += 1
            else:
                state['neutral_count'] = max(0, state['neutral_count'] - 0.3)

            if state['neutral_count'] >= min_n:
                state['phase'] = 'awaiting_action'
                state['challenge_count'] = 0

                if detail:
                    msg = 'Now: ' + detail
                else:
                    msg = 'Good! Now gently perform the action.'

                return self._result('neutral_ok', msg, 0.30)

            p = 0.05 + 0.20 * (state['neutral_count'] / max(min_n, 1))

            if state['neutral_count'] < 1:
                msg = 'Look straight at the camera...'
            else:
                msg = 'Good, hold steady...'

            return self._result('waiting_neutral', msg, p)

        # ── Phase 2: waiting for sustained pose ──
        if is_challenge_pose:
            # Slow increment — requires SUSTAINED movement
            state['challenge_count'] += 1.0
        else:
            # Fast decay — progress drops quickly if you stop
            state['challenge_count'] = max(0, state['challenge_count'] - 1.0)

        if state['challenge_count'] >= min_c:
            challenge['completed'] = True
            return self._result('passed', 'Challenge passed! ✓', 1.0)

        if state['challenge_count'] > 0:
            p = 0.30 + 0.70 * (state['challenge_count'] / max(min_c, 1))
            p = min(p, 0.99)

            if state['challenge_count'] >= min_c * 0.7:
                msg = 'Almost there... keep holding!'
            else:
                msg = 'Good! Keep holding the position...'

            return self._result('detecting', msg, p)

        if detail:
            msg = detail
        else:
            msg = 'Turn your head and hold it there'

        return self._result('continue', msg, 0.30)

    # ══════════════════════════════════════════════
    #  HELPER
    # ══════════════════════════════════════════════

    @staticmethod
    def _result(status, message, progress=0):
        """Create a standardized result dict."""
        return {
            'status': status,
            'message': message,
            'progress': round(float(progress), 2),
        }
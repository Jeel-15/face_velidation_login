"""
Blink detection for liveness verification.

Uses Eye Aspect Ratio (EAR) to detect genuine blinks.
Algorithm: open -> closed (>=CONSEC_FRAMES_CLOSED frames) -> open = 1 blink.

Robustness design:
- eye_aspect_ratio() returns None for bad/missing landmarks (not 0.0 which looks like closed eyes)
- Frames where EAR is None are skipped completely (never counted as closed eyes)
- Adaptive threshold: measures user's own open-eye baseline so threshold adapts per person
- All f-strings safely handle None values (no NoneType.__format__ crash)
- Detailed structured diagnostics returned for every call
"""

import numpy as np
import face_recognition
from scipy.spatial import distance as dist
from config import (
    BLINK_EAR_THRESHOLD,
    BLINK_EAR_OPEN_THRESHOLD,
    BLINK_CONSEC_FRAMES_CLOSED,
    BLINK_COOLDOWN_FRAMES,
    BLINK_MIN_EAR_DROP,
    BLINK_BASELINE_FRAMES,
)


# ---------------------------------------------------------------------------
# EAR helper
# ---------------------------------------------------------------------------

def eye_aspect_ratio(eye_landmarks):
    """
    Returns float EAR, or None if landmarks invalid/degenerate.
    CRITICAL: Returns None (not 0.0) so caller can skip frame vs treat as closed.
    """
    if eye_landmarks is None or len(eye_landmarks) != 6:
        return None
    try:
        eye = np.array(eye_landmarks, dtype=np.float64)
        A = dist.euclidean(eye[1], eye[5])
        B = dist.euclidean(eye[2], eye[4])
        C = dist.euclidean(eye[0], eye[3])
        if C < 1e-6:
            return None
        return float((A + B) / (2.0 * C))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# BlinkDetector state machine
# ---------------------------------------------------------------------------

class BlinkDetector:
    """
    State machine: open -> closed (streak >= CONSEC_FRAMES_CLOSED) -> open = 1 blink.
    Frames with EAR=None are SKIPPED (not counted as closed, not reset streaks).
    Adaptive threshold: baseline from first N open frames.
    """

    def __init__(self):
        self.ear_history = []
        self.state_history = []
        self.blink_count = 0
        self.frames_since_blink = 0
        self.consecutive_closed = 0
        self.had_closed_phase = False
        self.min_ear_seen = 1.0
        self.frames_total = 0
        self.frames_with_ear = 0
        self.frames_skipped_no_ear = 0
        self.state_transitions = []
        self.baseline_ears = []
        self.baseline_ear = None
        self.adaptive_threshold = BLINK_EAR_THRESHOLD

    def reset(self):
        self.ear_history.clear()
        self.state_history.clear()
        self.blink_count = 0
        self.frames_since_blink = 0
        self.consecutive_closed = 0
        self.had_closed_phase = False
        self.min_ear_seen = 1.0
        self.frames_total = 0
        self.frames_with_ear = 0
        self.frames_skipped_no_ear = 0
        self.state_transitions.clear()
        self.baseline_ears.clear()
        self.baseline_ear = None
        self.adaptive_threshold = BLINK_EAR_THRESHOLD

    def _update_baseline(self, ear):
        if self.baseline_ear is not None:
            return
        if ear > BLINK_EAR_OPEN_THRESHOLD:
            self.baseline_ears.append(ear)
        if len(self.baseline_ears) >= BLINK_BASELINE_FRAMES:
            self.baseline_ear = float(np.mean(self.baseline_ears))
            self.adaptive_threshold = min(
                self.baseline_ear - BLINK_MIN_EAR_DROP,
                BLINK_EAR_THRESHOLD,
            )

    def _is_closed(self, ear):
        return ear < self.adaptive_threshold and ear < BLINK_EAR_THRESHOLD

    def process_frame(self, frame, face_location=None):
        self.frames_total += 1
        result = {
            'ear': None, 'state': 'skipped', 'blink_this_frame': False,
            'blink_count': self.blink_count, 'skip_reason': None, 'message': '',
        }
        try:
            rgb = frame[:, :, ::-1]
            landmarks_list = (
                face_recognition.face_landmarks(rgb, [face_location])
                if face_location is not None
                else face_recognition.face_landmarks(rgb)
            )
        except Exception as exc:
            result['skip_reason'] = f'landmark_exception:{exc}'
            result['message'] = f'[SKIP] landmark exception: {exc}'
            self.frames_skipped_no_ear += 1
            return result

        if not landmarks_list:
            result['skip_reason'] = 'no_face_detected'
            result['message'] = '[SKIP] no face detected'
            self.frames_skipped_no_ear += 1
            return result

        lm = landmarks_list[0]
        if 'left_eye' not in lm or 'right_eye' not in lm:
            result['skip_reason'] = 'no_eye_landmarks'
            result['message'] = '[SKIP] eye landmarks missing'
            self.frames_skipped_no_ear += 1
            return result

        left_ear  = eye_aspect_ratio(lm['left_eye'])
        right_ear = eye_aspect_ratio(lm['right_eye'])

        if left_ear is None or right_ear is None:
            result['skip_reason'] = 'ear_compute_failed'
            result['message'] = f'[SKIP] EAR failed (L={left_ear}, R={right_ear})'
            self.frames_skipped_no_ear += 1
            return result

        avg_ear = (left_ear + right_ear) / 2.0
        result['ear'] = avg_ear
        self.frames_with_ear += 1
        self.ear_history.append(avg_ear)
        if avg_ear < self.min_ear_seen:
            self.min_ear_seen = avg_ear

        self._update_baseline(avg_ear)

        # Safe string formatting — never call .3f on None
        baseline_str  = f'{self.baseline_ear:.3f}' if self.baseline_ear is not None else 'N/A'
        threshold_str = f'{self.adaptive_threshold:.3f}'

        is_closed = self._is_closed(avg_ear)
        current_state = 'closed' if is_closed else 'open'
        result['state'] = current_state
        self.state_history.append(current_state)

        if self.frames_since_blink > 0:
            self.frames_since_blink -= 1

        if current_state == 'closed':
            self.consecutive_closed += 1
            if self.consecutive_closed >= BLINK_CONSEC_FRAMES_CLOSED:
                if not self.had_closed_phase:
                    self.state_transitions.append(f'CLOSE_PHASE@ear={avg_ear:.3f}')
                self.had_closed_phase = True
            result['message'] = (
                f'closed EAR={avg_ear:.3f} thresh={threshold_str} streak={self.consecutive_closed}'
            )
        else:
            if self.had_closed_phase and self.frames_since_blink == 0:
                self.blink_count += 1
                result['blink_this_frame'] = True
                result['blink_count'] = self.blink_count
                self.state_transitions.append(f'BLINK#{self.blink_count}@ear={avg_ear:.3f}')
                self.had_closed_phase = False
                self.frames_since_blink = BLINK_COOLDOWN_FRAMES
                result['message'] = (
                    f'BLINK #{self.blink_count} detected EAR={avg_ear:.3f} baseline={baseline_str}'
                )
            else:
                result['message'] = (
                    f'open EAR={avg_ear:.3f} baseline={baseline_str} thresh={threshold_str}'
                )
            self.consecutive_closed = 0

        return result

    def has_blinked(self):
        return self.blink_count > 0

    def get_stats(self):
        ears = self.ear_history
        return {
            'blink_count':        self.blink_count,
            'frames_total':       self.frames_total,
            'frames_with_ear':    self.frames_with_ear,
            'frames_skipped':     self.frames_skipped_no_ear,
            'avg_ear':            round(float(np.mean(ears)),  3) if ears else None,
            'min_ear':            round(float(self.min_ear_seen), 3) if ears else None,
            'max_ear':            round(float(np.max(ears)),   3) if ears else None,
            'baseline_ear':       round(self.baseline_ear, 3)       if self.baseline_ear is not None else None,
            'adaptive_threshold': round(self.adaptive_threshold, 3),
            'state_transitions':  list(self.state_transitions),
            'ear_sequence':       [round(e, 3) for e in ears],
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_blink_from_frames(frames, face_locations=None):
    """
    Run blink detection over a list of BGR frames.
    NO internal frame-sampling — JS already sends every 2nd frame.
    Returns structured result dict with diagnostics.
    """
    if not frames:
        return {
            'blink_detected': False, 'blink_count': 0,
            'reason': 'no_frames_provided',
            'frames_total': 0, 'frames_valid': 0, 'frames_skipped': 0,
            'stats': {}, 'per_frame_results': [],
        }

    detector = BlinkDetector()
    per_frame_results = []

    for i, frame in enumerate(frames):
        face_loc = (
            face_locations[i]
            if face_locations and i < len(face_locations) and face_locations[i] is not None
            else None
        )
        try:
            result = detector.process_frame(frame, face_loc)
        except Exception as exc:
            result = {
                'ear': None, 'state': 'skipped', 'blink_this_frame': False,
                'blink_count': detector.blink_count,
                'skip_reason': f'unexpected:{exc}', 'message': f'[SKIP] {exc}',
            }
            detector.frames_total += 1
            detector.frames_skipped_no_ear += 1

        per_frame_results.append(result)
        if detector.has_blinked():
            break   # early exit once blink confirmed

    stats = detector.get_stats()

    # Determine human-readable failure reason
    if detector.has_blinked():
        reason = 'blink_detected'
    elif stats['frames_with_ear'] == 0:
        reason = 'no_valid_ear_frames'
    elif stats['baseline_ear'] is None:
        reason = 'baseline_not_established'
    elif detector.had_closed_phase:
        reason = 'incomplete_blink_no_open_after_close'
    else:
        reason = (
            f'no_close_phase_detected('
            f'min_ear={stats["min_ear"]},thresh={stats["adaptive_threshold"]})'
        )

    return {
        'blink_detected':    detector.has_blinked(),
        'blink_count':       detector.blink_count,
        'reason':            reason,
        'frames_total':      stats['frames_total'],
        'frames_valid':      stats['frames_with_ear'],
        'frames_skipped':    stats['frames_skipped'],
        'stats':             stats,
        'per_frame_results': per_frame_results,
    }

"""
Passive anti-spoof detection without challenge-response.

This module intentionally avoids active liveness challenges (blink/head-move prompts)
and relies on passive signals from captured frames.
"""

import numpy as np
import cv2
from collections import deque
from config import (
    MOTION_ANALYSIS_FRAMES,
    MOTION_WINDOW_EXPAND_RATIO,
    SUSPICIOUS_MOTION_RATIO,
    TEXTURE_ANALYSIS_FOCUS_PERCENT,
    LIVENESS_STRONG_THRESHOLD,
    LIVENESS_WEAK_THRESHOLD,
    ANTI_SPOOF_MIN_BRIGHTNESS,
    ANTI_SPOOF_MAX_BRIGHTNESS,
    ANTI_SPOOF_MIN_LAPLACIAN,
    ANTI_SPOOF_MIN_FACE_RATIO,
    REPLAY_MIN_MOTION,
    REPLAY_TOGETHER_RATIO,
    REPLAY_STRONG_SUSPECT_RATIO,
    TEXTURE_PRINT_STD_MAX,
    TEXTURE_PRINT_LAP_MAX,
    TEXTURE_PRINT_EDGE_MAX,
    TEXTURE_SCREEN_HF_MIN,
    TEXTURE_SCREEN_EDGE_MIN,
    MOTION_MINIMAL_MOTION_THRESHOLD,
    MOTION_MINIMAL_SCORE_CAP,
    MOTION_CLEAN_REPLAY_MAX,
    MOTION_FACE_BG_DOMINANCE_MIN,
    REPLAY_SUSPECT_SCORE_CAP,
    TEXTURE_NATURAL_STD_MIN,
    TEXTURE_NATURAL_STD_MAX,
    TEXTURE_STD_FALLOFF_RANGE,
    TEXTURE_LAP_BASE,
    TEXTURE_LAP_RANGE,
    TEXTURE_HF_TARGET,
    TEXTURE_HF_TOLERANCE,
    ANTI_SPOOF_LOW_QUALITY_GATE,
    STRONG_SPOOF_MOTION_MAX,
    STRONG_SPOOF_TEXTURE_MAX,
    STRONG_SPOOF_MOTION_TEXTURE_MAX,
    ANTI_SPOOF_CONFIDENCE_HIGH_ACCEPT,
    ANTI_SPOOF_CONFIDENCE_HIGH_REJECT,
    MAX_FACES_ALLOWED,
)


def _clamp01(value):
    return float(np.clip(value, 0.0, 1.0))


def _normalize_face_input(face_loc):
    """
    Normalize incoming face location format.
    Supports:
      - single tuple: (top, right, bottom, left)
      - list of tuples for multi-face detection
    Returns a list of tuples.
    """
    if face_loc is None:
        return []

    if isinstance(face_loc, tuple) and len(face_loc) == 4:
        return [face_loc]

    if isinstance(face_loc, list):
        normalized = []
        for item in face_loc:
            if isinstance(item, tuple) and len(item) == 4:
                normalized.append(item)
            elif isinstance(item, list) and len(item) == 4:
                normalized.append(tuple(item))
        return normalized

    return []


def _safe_crop(gray_frame, face_box):
    top, right, bottom, left = face_box
    height, width = gray_frame.shape[:2]

    top = max(0, min(height - 1, int(top)))
    bottom = max(0, min(height, int(bottom)))
    left = max(0, min(width - 1, int(left)))
    right = max(0, min(width, int(right)))

    if bottom <= top or right <= left:
        return None, (top, right, bottom, left)

    return gray_frame[top:bottom, left:right], (top, right, bottom, left)


class FaceQualityAnalyzer:
    """Passive quality gates used before motion/texture trust."""

    def __init__(self):
        self.samples = deque(maxlen=MOTION_ANALYSIS_FRAMES)

    def add_frame(self, frame, face_location):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.samples.append((gray, face_location))

    def can_analyze(self):
        return len(self.samples) >= 2

    def analyze(self):
        if not self.can_analyze():
            return {
                'score': 0.5,
                'is_low_quality': True,
                'multiple_faces': False,
                'reasons': ['not_enough_frames'],
                'confidence': 'low'
            }

        brightness_values = []
        blur_values = []
        face_ratios = []
        reasons = []
        multiple_faces_detected = False

        for gray, raw_face_loc in self.samples:
            face_boxes = _normalize_face_input(raw_face_loc)

            if len(face_boxes) == 0:
                reasons.append('no_face')
                continue

            if len(face_boxes) > MAX_FACES_ALLOWED:
                multiple_faces_detected = True
                reasons.append('multiple_faces')
                continue

            face_region, normalized_box = _safe_crop(gray, face_boxes[0])
            if face_region is None or face_region.size == 0:
                reasons.append('invalid_face_region')
                continue

            top, right, bottom, left = normalized_box
            frame_h, frame_w = gray.shape[:2]
            face_h = max(1, bottom - top)
            face_w = max(1, right - left)

            brightness = float(np.mean(face_region))
            blur_var = float(cv2.Laplacian(face_region, cv2.CV_64F).var())
            face_ratio = float(face_w / max(1, frame_w))

            brightness_values.append(brightness)
            blur_values.append(blur_var)
            face_ratios.append(face_ratio)

        if multiple_faces_detected:
            return {
                'score': 0.05,
                'is_low_quality': True,
                'multiple_faces': True,
                'reasons': ['multiple_faces'],
                'confidence': 'high',
            }

        if not brightness_values:
            return {
                'score': 0.2,
                'is_low_quality': True,
                'multiple_faces': False,
                'reasons': list(set(reasons + ['insufficient_valid_face_regions'])),
                'confidence': 'low',
            }

        avg_brightness = float(np.mean(brightness_values))
        avg_blur = float(np.mean(blur_values))
        avg_face_ratio = float(np.mean(face_ratios))

        brightness_score = 1.0
        if avg_brightness < ANTI_SPOOF_MIN_BRIGHTNESS:
            brightness_score = _clamp01(avg_brightness / max(1.0, ANTI_SPOOF_MIN_BRIGHTNESS))
            reasons.append('too_dark')
        elif avg_brightness > ANTI_SPOOF_MAX_BRIGHTNESS:
            brightness_score = _clamp01((255.0 - avg_brightness) / max(1.0, 255.0 - ANTI_SPOOF_MAX_BRIGHTNESS))
            reasons.append('too_bright')

        blur_score = _clamp01(avg_blur / max(1.0, ANTI_SPOOF_MIN_LAPLACIAN))
        if avg_blur < ANTI_SPOOF_MIN_LAPLACIAN:
            reasons.append('blurry')

        face_size_score = _clamp01(avg_face_ratio / max(1e-6, ANTI_SPOOF_MIN_FACE_RATIO))
        if avg_face_ratio < ANTI_SPOOF_MIN_FACE_RATIO:
            reasons.append('face_too_small')

        quality_score = float(0.4 * brightness_score + 0.35 * blur_score + 0.25 * face_size_score)

        low_quality = (
            brightness_score < ANTI_SPOOF_LOW_QUALITY_GATE or
            blur_score < ANTI_SPOOF_LOW_QUALITY_GATE or
            face_size_score < ANTI_SPOOF_LOW_QUALITY_GATE
        )

        return {
            'score': quality_score,
            'is_low_quality': bool(low_quality),
            'multiple_faces': False,
            'avg_brightness': avg_brightness,
            'avg_blur_laplacian': avg_blur,
            'avg_face_ratio': avg_face_ratio,
            'brightness_score': float(brightness_score),
            'blur_score': float(blur_score),
            'face_size_score': float(face_size_score),
            'reasons': list(sorted(set(reasons))) if reasons else ['quality_ok'],
            'confidence': 'high' if not low_quality else 'medium',
        }

class MotionAnalyzer:
    """
    Analyze motion of face vs background.
    Real faces should have motion concentrated in face region.
    Screen/photo replays typically have face and background moving together.
    """
    
    def __init__(self, window_size=MOTION_ANALYSIS_FRAMES):
        self.window_size = window_size
        self.frames = deque(maxlen=window_size)
        self.face_locations = deque(maxlen=window_size)
    
    def add_frame(self, frame, face_location):
        """Add a frame and face location to the buffer."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.frames.append(gray)
        self.face_locations.append(face_location)
    
    def can_analyze(self):
        """Check if we have enough frames for motion analysis."""
        return len(self.frames) >= 3
    
    def analyze(self):
        """
        Analyze motion and return liveness score.
        Returns:
            score: 0-1, higher = more live (motion concentrated in face)
            details: dict with motion metrics
        """
        if not self.can_analyze():
            return {'score': 0.5, 'detail': 'Not enough frames', 'confidence': 'low'}

        frames_list = list(self.frames)
        face_locs = list(self.face_locations)

        face_motion_values = []
        bg_motion_values = []
        together_flags = []

        for idx in range(1, len(frames_list)):
            prev_frame = frames_list[idx - 1]
            curr_frame = frames_list[idx]

            flow = cv2.calcOpticalFlowFarneback(
                prev_frame,
                curr_frame,
                None,
                pyr_scale=0.5,
                levels=3,
                winsize=15,
                iterations=3,
                poly_n=5,
                poly_sigma=1.2,
                flags=0,
            )
            magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

            normalized_faces = _normalize_face_input(face_locs[idx])
            if not normalized_faces:
                continue

            face_box = normalized_faces[0]
            top, right, bottom, left = face_box
            top = max(0, int(top))
            bottom = min(magnitude.shape[0], int(bottom))
            left = max(0, int(left))
            right = min(magnitude.shape[1], int(right))

            if bottom <= top or right <= left:
                continue

            face_region = magnitude[top:bottom, left:right]
            if face_region.size == 0:
                continue

            face_motion = float(np.mean(face_region))

            expand = MOTION_WINDOW_EXPAND_RATIO
            face_h = bottom - top
            face_w = right - left
            bg_top = max(0, int(top - face_h * (expand - 1) / 2))
            bg_bottom = min(magnitude.shape[0], int(bottom + face_h * (expand - 1) / 2))
            bg_left = max(0, int(left - face_w * (expand - 1) / 2))
            bg_right = min(magnitude.shape[1], int(right + face_w * (expand - 1) / 2))

            ring_region = magnitude[bg_top:bg_bottom, bg_left:bg_right]
            if ring_region.size == 0:
                continue

            ring_mask = np.ones(ring_region.shape, dtype=bool)
            rel_top = top - bg_top
            rel_bottom = rel_top + face_h
            rel_left = left - bg_left
            rel_right = rel_left + face_w
            ring_mask[rel_top:rel_bottom, rel_left:rel_right] = False

            bg_pixels = ring_region[ring_mask]
            if bg_pixels.size == 0:
                continue

            bg_motion = float(np.mean(bg_pixels))

            face_motion_values.append(face_motion)
            bg_motion_values.append(bg_motion)

            high_motion_both = face_motion > REPLAY_MIN_MOTION and bg_motion > REPLAY_MIN_MOTION
            motion_similarity = min(face_motion, bg_motion) / (max(face_motion, bg_motion) + 1e-6)
            together_flags.append(bool(high_motion_both and motion_similarity >= REPLAY_TOGETHER_RATIO))

        if not face_motion_values:
            return {
                'score': 0.45,
                'face_motion': 0.0,
                'bg_motion': 0.0,
                'motion_ratio': 1.0,
                'replay_consistency': 0.0,
                'replay_suspect': False,
                'verdict': 'insufficient_motion_data',
                'confidence': 'low',
            }

        face_motion_mean = float(np.mean(face_motion_values))
        bg_motion_mean = float(np.mean(bg_motion_values))
        motion_ratio = float(face_motion_mean / (bg_motion_mean + 1e-6))
        replay_consistency = float(np.mean(together_flags)) if together_flags else 0.0

        dominance_score = _clamp01((motion_ratio - SUSPICIOUS_MOTION_RATIO) / 0.9)
        anti_replay_score = 1.0 - replay_consistency
        motion_score = float(_clamp01(0.55 * dominance_score + 0.45 * anti_replay_score))

        if face_motion_mean < MOTION_MINIMAL_MOTION_THRESHOLD and bg_motion_mean < MOTION_MINIMAL_MOTION_THRESHOLD:
            motion_verdict = 'minimal_motion'
            motion_score = min(motion_score, MOTION_MINIMAL_SCORE_CAP)
        elif replay_consistency >= REPLAY_STRONG_SUSPECT_RATIO:
            motion_verdict = 'screen_replay_suspect'
            motion_score = min(motion_score, REPLAY_SUSPECT_SCORE_CAP)
        elif motion_ratio >= MOTION_FACE_BG_DOMINANCE_MIN and replay_consistency < MOTION_CLEAN_REPLAY_MAX:
            motion_verdict = 'natural_relative_motion'
        else:
            motion_verdict = 'mixed_motion_pattern'

        return {
            'score': float(motion_score),
            'face_motion': float(face_motion_mean),
            'bg_motion': float(bg_motion_mean),
            'motion_ratio': float(motion_ratio),
            'replay_consistency': replay_consistency,
            'replay_suspect': replay_consistency >= REPLAY_STRONG_SUSPECT_RATIO,
            'verdict': motion_verdict,
            'confidence': 'high' if len(face_motion_values) >= 3 else 'medium'
        }


class TextureAnalyzer:
    """
    Analyze texture characteristics of face.
    Real faces have natural texture (skin texture).
    Printed photos have low or very uniform texture.
    Screens may have moire patterns or unnatural texture.
    """
    
    def __init__(self):
        self.samples = deque(maxlen=MOTION_ANALYSIS_FRAMES)
    
    def add_frame(self, frame, face_location):
        """Add a frame for texture analysis."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.samples.append((gray, face_location))
    
    def can_analyze(self):
        """Check if we have enough samples."""
        return len(self.samples) >= 2
    
    def analyze(self):
        """
        Analyze texture and return liveness score.
        Returns:
            score: 0-1, higher = more live (natural skin texture)
            details: dict with texture metrics
        """
        if not self.can_analyze():
            return {'score': 0.5, 'detail': 'Not enough samples', 'confidence': 'low'}

        gray, raw_face_location = list(self.samples)[len(self.samples) // 2]
        face_boxes = _normalize_face_input(raw_face_location)
        if not face_boxes:
            return {
                'score': 0.4,
                'verdict': 'no_face_texture_region',
                'screen_pattern_suspect': False,
                'printed_surface_suspect': False,
                'confidence': 'low',
            }

        face_region, _ = _safe_crop(gray, face_boxes[0])
        if face_region is None or face_region.size == 0:
            return {
                'score': 0.4,
                'verdict': 'invalid_face_texture_region',
                'screen_pattern_suspect': False,
                'printed_surface_suspect': False,
                'confidence': 'low',
            }

        h, w = face_region.shape
        focus_size = TEXTURE_ANALYSIS_FOCUS_PERCENT
        top_c = int(h * (1 - focus_size) / 2)
        bottom_c = int(h * (1 + focus_size) / 2)
        left_c = int(w * (1 - focus_size) / 2)
        right_c = int(w * (1 + focus_size) / 2)

        focus_region = face_region[top_c:bottom_c, left_c:right_c]
        if focus_region.size == 0:
            return {
                'score': 0.4,
                'verdict': 'empty_focus_region',
                'screen_pattern_suspect': False,
                'printed_surface_suspect': False,
                'confidence': 'low',
            }

        texture_std = float(np.std(focus_region))
        laplacian = cv2.Laplacian(focus_region, cv2.CV_64F)
        texture_laplacian = float(laplacian.var())

        edges = cv2.Canny(focus_region, 30, 100)
        edge_density = float(np.sum(edges > 0) / max(1, edges.size))

        # Frequency-domain high-frequency energy ratio for screen pattern detection
        float_region = focus_region.astype(np.float32)
        fft = np.fft.fft2(float_region)
        fft_shift = np.fft.fftshift(fft)
        mag = np.abs(fft_shift)

        yy, xx = np.indices(mag.shape)
        center_y = mag.shape[0] / 2.0
        center_x = mag.shape[1] / 2.0
        radius = np.sqrt((yy - center_y) ** 2 + (xx - center_x) ** 2)
        max_radius = max(1.0, np.max(radius))

        high_freq_mask = radius > (0.35 * max_radius)
        total_energy = float(np.sum(mag) + 1e-6)
        high_freq_energy = float(np.sum(mag[high_freq_mask]))
        high_freq_ratio = high_freq_energy / total_energy

        printed_surface_suspect = (
            texture_std < TEXTURE_PRINT_STD_MAX and
            texture_laplacian < TEXTURE_PRINT_LAP_MAX and
            edge_density < TEXTURE_PRINT_EDGE_MAX
        )

        screen_pattern_suspect = (
            high_freq_ratio > TEXTURE_SCREEN_HF_MIN and
            edge_density > TEXTURE_SCREEN_EDGE_MIN
        )

        std_score = 1.0 if TEXTURE_NATURAL_STD_MIN <= texture_std <= TEXTURE_NATURAL_STD_MAX else (
            _clamp01(texture_std / TEXTURE_NATURAL_STD_MIN)
            if texture_std < TEXTURE_NATURAL_STD_MIN
            else _clamp01(1.0 - (texture_std - TEXTURE_NATURAL_STD_MAX) / TEXTURE_STD_FALLOFF_RANGE)
        )
        lap_score = _clamp01((texture_laplacian - TEXTURE_LAP_BASE) / TEXTURE_LAP_RANGE)
        hf_score = _clamp01(1.0 - abs(high_freq_ratio - TEXTURE_HF_TARGET) / TEXTURE_HF_TOLERANCE)

        texture_score = float(0.45 * std_score + 0.25 * lap_score + 0.30 * hf_score)

        if printed_surface_suspect:
            texture_score = min(texture_score, 0.2)
            verdict = 'printed_surface_suspect'
        elif screen_pattern_suspect:
            texture_score = min(texture_score, 0.25)
            verdict = 'screen_pattern_suspect'
        elif texture_score >= 0.65:
            verdict = 'natural_texture'
        else:
            verdict = 'mixed_texture'

        return {
            'score': float(texture_score),
            'texture_std': float(texture_std),
            'laplacian_var': float(texture_laplacian),
            'edge_density': float(edge_density),
            'high_freq_ratio': float(high_freq_ratio),
            'screen_pattern_suspect': bool(screen_pattern_suspect),
            'printed_surface_suspect': bool(printed_surface_suspect),
            'verdict': verdict,
            'confidence': 'high' if not (screen_pattern_suspect or printed_surface_suspect) else 'medium'
        }


class LivenessScorer:
    """
    Aggregate multiple anti-spoof signals into a final liveness score.
    High score = likely real, live face
    Low score = likely spoof (photo/screen)
    """
    
    def __init__(self):
        self.quality_analyzer = FaceQualityAnalyzer()
        self.motion_analyzer = MotionAnalyzer()
        self.texture_analyzer = TextureAnalyzer()
    
    def add_frame(self, frame, face_location):
        """Add frame for analysis."""
        self.quality_analyzer.add_frame(frame, face_location)
        self.motion_analyzer.add_frame(frame, face_location)
        self.texture_analyzer.add_frame(frame, face_location)
    
    def can_score(self):
        """Check if we have enough data to compute score."""
        return (self.quality_analyzer.can_analyze() and
            self.motion_analyzer.can_analyze() and
                self.texture_analyzer.can_analyze())
    
    def score(self, quality_scores_list):
        """
        Compute final liveness score.
        quality_scores_list: list of quality scores from each frame (0-1)
        Returns:
            score: 0-1, final liveness score
            details: dict with breakdown of scores
        """
        details = {}
        
        # Get quality analysis
        quality_result = self.quality_analyzer.analyze()
        quality_score = quality_result['score']
        details['quality'] = quality_result

        # Get motion analysis
        motion_result = self.motion_analyzer.analyze()
        motion_score = motion_result['score']
        details['motion'] = motion_result

        # Get texture analysis
        texture_result = self.texture_analyzer.analyze()
        texture_score = texture_result['score']
        details['texture'] = texture_result

        # External quality from frame validator (soft influence only)
        if quality_scores_list:
            external_quality_score = float(np.mean(quality_scores_list))
        else:
            external_quality_score = 0.5
        details['external_quality'] = external_quality_score

        # Combine: keep quality influential but not over-strict
        final_score = (
            motion_score * 0.38 +
            texture_score * 0.34 +
            quality_score * 0.20 +
            external_quality_score * 0.08
        )

        strong_spoof = (
            motion_result.get('replay_suspect', False) and motion_score <= STRONG_SPOOF_MOTION_MAX
        ) or (
            (texture_result.get('screen_pattern_suspect', False) or texture_result.get('printed_surface_suspect', False))
            and texture_score <= STRONG_SPOOF_TEXTURE_MAX
            and motion_score <= STRONG_SPOOF_MOTION_TEXTURE_MAX
        )

        low_quality = quality_result.get('is_low_quality', False) or quality_result.get('multiple_faces', False)

        decision, reason, is_live = self._make_decision(
            final_score,
            strong_spoof=strong_spoof,
            low_quality=low_quality,
            quality_result=quality_result,
            motion_result=motion_result,
            texture_result=texture_result,
        )

        if decision == 'accept':
            confidence_label = 'high' if final_score >= ANTI_SPOOF_CONFIDENCE_HIGH_ACCEPT else 'medium'
        elif decision == 'reject':
            confidence_label = 'high' if final_score <= ANTI_SPOOF_CONFIDENCE_HIGH_REJECT else 'medium'
        else:
            confidence_label = 'low' if low_quality else 'medium'

        return {
            'score': float(final_score),
            'confidence': float(_clamp01(final_score)),
            'confidence_label': confidence_label,
            'is_live': bool(is_live),
            'reason': reason,
            'details': details,
            'decision': decision,
        }

    def _make_decision(self, score, strong_spoof, low_quality, quality_result, motion_result, texture_result):
        """
        Make a decision based on score.
        Returns: 'accept' (likely live), 'uncertain' (retry), or 'reject' (likely spoof)
        """
        if strong_spoof:
            if motion_result.get('replay_suspect', False):
                return 'reject', 'strong_spoof_screen_replay', False
            if texture_result.get('screen_pattern_suspect', False):
                return 'reject', 'strong_spoof_screen_texture', False
            if texture_result.get('printed_surface_suspect', False):
                return 'reject', 'strong_spoof_printed_texture', False
            return 'reject', 'strong_spoof_detected', False

        if low_quality:
            if quality_result.get('multiple_faces', False):
                return 'uncertain', 'low_quality_multiple_faces', False
            quality_reasons = quality_result.get('reasons', [])
            if quality_reasons:
                return 'uncertain', f"low_quality_{quality_reasons[0]}", False
            return 'uncertain', 'low_quality_retry', False

        if score >= LIVENESS_STRONG_THRESHOLD:
            return 'accept', 'passive_liveness_passed', True

        if score <= LIVENESS_WEAK_THRESHOLD:
            return 'reject', 'strong_spoof_low_confidence', False

        return 'uncertain', 'uncertain_retry', False


def analyze_liveness(frames, face_locations, quality_scores):
    """
    Convenience function to analyze liveness using all frames collected.
    Returns: {'score': float, 'confidence': str, 'decision': str, 'details': dict}
    """
    scorer = LivenessScorer()
    
    for frame, face_loc in zip(frames, face_locations):
        scorer.add_frame(frame, face_loc)
    
    if not scorer.can_score():
        return {
            'score': 0.5,
            'confidence': 0.5,
            'confidence_label': 'low',
            'is_live': False,
            'reason': 'not_enough_frames',
            'decision': 'uncertain',
            'detail': 'Not enough frames for robust analysis',
            'details': {}
        }

    result = scorer.score(quality_scores)
    return result

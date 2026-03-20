"""
Face detection and recognition utilities.
Uses face_recognition library (dlib-based) for 128-dimensional face embeddings.
This provides proper biometric embeddings for accurate face matching.
"""

import cv2
import numpy as np
import face_recognition
from config import (
    FACE_MODEL,
    MIN_FACE_SIZE_RATIO, MIN_FACE_SIZE,
    MAX_FACES_ALLOWED,
    FRAME_WIDTH, FRAME_HEIGHT,
    MIN_BRIGHTNESS, MAX_BRIGHTNESS, MIN_BRIGHTNESS_VARIANCE,
    MAX_BLUR,
    FACE_MATCH_THRESHOLD,
)

# Load Haar Cascade classifier for face detection (fast pre-screening)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

class FaceDetector:
    """Detect and validate faces in images."""
    
    def __init__(self, model=FACE_MODEL):
        self.model = model
        self.cascade = face_cascade
    
    def detect_faces(self, frame):
        """
        Detect faces in a frame using face_recognition library.
        Returns: list of face locations as (top, right, bottom, left) tuples
        compatible with face_recognition library
        """
        # Convert BGR to RGB for face_recognition
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Use face_recognition's detector (dlib-based, more accurate than Haar)
        # 'hog' is faster, 'cnn' is more accurate but requires GPU
        model = 'hog' if self.model.lower() == 'hog' else 'hog'
        
        try:
            # number_of_times_to_upsample=0 skips the upsampling step.
            # Default is 1 (doubles image before HOG scan) which is ~3x slower.
            # At 320px frames faces are large enough to detect without upsampling.
            face_locations = face_recognition.face_locations(
                rgb_frame, number_of_times_to_upsample=0, model=model)
        except Exception as e:
            print(f"Error in face detection: {e}")
            return []
        
        return face_locations  # Returns [(top, right, bottom, left), ...]
    
    def get_face_size(self, face_location, frame_width):
        """
        Get face size as a ratio of frame width.
        face_location: (top, right, bottom, left)
        """
        top, right, bottom, left = face_location
        face_width = right - left
        size_ratio = face_width / frame_width
        face_pixels = face_width
        return size_ratio, face_pixels
    
    def get_face_center(self, face_location):
        """Get center coordinates of a face."""
        top, right, bottom, left = face_location
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        return cx, cy



class FaceRecognizer:
    """
    Generate 128-dimensional face embeddings using dlib and match against stored embeddings.
    Uses the face_recognition library which wraps dlib's ResNet-based model.
    """
    
    def __init__(self, model_name='hog'):
        """
        Initialize face recognizer.
        model_name: 'hog' (fast) or 'cnn' (accurate, requires GPU)
        """
        self.model_name = model_name
    
    def get_embedding(self, frame, face_location):
        """
        Generate 128-dimensional embedding for a face using dlib's ResNet model.
        
        Args:
            frame: numpy array (BGR color space)
            face_location: (top, right, bottom, left) tuple
        
        Returns:
            numpy array of shape (128,) containing the face embedding
            None if embedding generation fails
        """
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Generate embedding using face_recognition
            # Returns a list of encodings (one per face location)
            encodings = face_recognition.face_encodings(
                rgb_frame,
                known_face_locations=[face_location],
                num_jitters=1  # Use 1 for speed, can increase to 5 for accuracy
            )
            
            if len(encodings) > 0:
                return np.array(encodings[0], dtype=np.float32)
            else:
                return None
                
        except Exception as e:
            print(f"Error generating face embedding: {e}")
            return None
    
    def compare_embeddings(self, embedding, stored_embeddings, tolerance=FACE_MATCH_THRESHOLD):
        """
        Compare a face embedding against multiple stored embeddings.
        Uses Euclidean distance (standard for face recognition).
        
        Args:
            embedding: numpy array of shape (128,) - live face embedding
            stored_embeddings: list of embeddings or list of lists
            tolerance: float, distance threshold (0.6 is standard for dlib)
                      Lower = stricter matching
                      0.5 = very strict, 0.6 = moderate, 0.7 = loose
        
        Returns:
            dict with:
                - min_distance: float, minimum distance to any stored embedding
                - match_count: int, number of stored embeddings that match
                - distances: list of distances to each stored embedding
                - all_distances: numpy array of all distances
        """
        if embedding is None or len(stored_embeddings) == 0:
            return {
                'min_distance': 1.0,
                'match_count': 0,
                'distances': [],
                'all_distances': np.array([])
            }
        
        # Convert to numpy arrays
        try:
            stored_embeddings = np.array(stored_embeddings, dtype=np.float32)
            embedding = np.array(embedding, dtype=np.float32)
        except Exception as e:
            print(f"Error converting embeddings to numpy arrays: {e}")
            return {
                'min_distance': 1.0,
                'match_count': 0,
                'distances': [],
                'all_distances': np.array([])
            }
        
        # Ensure proper shape
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        if stored_embeddings.ndim == 1:
            stored_embeddings = stored_embeddings.reshape(1, -1)
        
        # Use face_recognition's distance function (same as dlib)
        # This is Euclidean distance in the 128-dimensional space
        distances = face_recognition.face_distance(stored_embeddings, embedding[0])
        
        # Count matches below tolerance threshold
        match_count = np.sum(distances < tolerance)
        min_distance = float(np.min(distances)) if len(distances) > 0 else 1.0
        
        return {
            'min_distance': min_distance,
            'match_count': int(match_count),
            'distances': distances.tolist(),
            'all_distances': distances
        }



def validate_face_quality(frame, face_location, detector):
    """
    Validate if a face meets quality requirements.
    Returns: (is_valid: bool, quality_score: float, errors: list)
    quality_score: 0-1, higher is better
    """
    errors = []
    quality_checks = {}
    
    top, right, bottom, left = face_location
    
    # Check face size
    size_ratio, size_pixels = detector.get_face_size(face_location, frame.shape[1])
    if size_ratio < MIN_FACE_SIZE_RATIO or size_pixels < MIN_FACE_SIZE:
        errors.append(f"Face too small: {size_ratio:.2%} of frame width")
    quality_checks['face_size'] = min(size_ratio / MIN_FACE_SIZE_RATIO, 1.0)
    
    # Extract face region
    face_region = frame[top:bottom, left:right]
    
    # Check brightness
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    brightness_mean = np.mean(gray)
    brightness_std = np.std(gray)
    
    if brightness_mean < MIN_BRIGHTNESS or brightness_mean > MAX_BRIGHTNESS:
        errors.append(f"Poor brightness: {brightness_mean:.1f}")
    if brightness_std < MIN_BRIGHTNESS_VARIANCE:
        errors.append(f"Face too uniform (low variance): {brightness_std:.1f}")
    
    brightness_score = 1.0
    if brightness_mean < MIN_BRIGHTNESS:
        brightness_score = brightness_mean / MIN_BRIGHTNESS
    elif brightness_mean > MAX_BRIGHTNESS:
        brightness_score = (255 - brightness_mean) / (255 - MAX_BRIGHTNESS)
    
    if brightness_std < MIN_BRIGHTNESS_VARIANCE:
        brightness_score *= brightness_std / MIN_BRIGHTNESS_VARIANCE
    
    quality_checks['brightness'] = brightness_score
    
    # Check blur (Laplacian variance)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    if laplacian_var < MAX_BLUR:
        errors.append(f"Face too blurry: {laplacian_var:.1f}")
    
    blur_score = min(laplacian_var / MAX_BLUR, 1.0)
    quality_checks['blur'] = blur_score
    
    # Calculate overall quality score (average of all checks)
    quality_score = np.mean(list(quality_checks.values()))
    
    is_valid = len(errors) == 0
    
    return {
        'is_valid': is_valid,
        'quality_score': float(quality_score),
        'quality_checks': quality_checks,
        'errors': errors,
        'brightness_mean': float(brightness_mean),
        'brightness_std': float(brightness_std),
        'laplacian_var': float(laplacian_var)
    }


def validate_frame(frame, detector):
    """
    Complete frame validation:
    - Exactly one face present
    - Face quality meets requirements
    Returns: (is_valid: bool, data: dict)
    """
    # Detect faces
    face_locations = detector.detect_faces(frame)
    
    # Check face count
    if len(face_locations) == 0:
        return {
            'is_valid': False,
            'num_faces': 0,
            'error': 'no_face',
            'message': 'No face detected'
        }
    
    from config import MAX_FACES_ALLOWED
    if len(face_locations) > MAX_FACES_ALLOWED:
        return {
            'is_valid': False,
            'num_faces': len(face_locations),
            'error': 'multiple_faces',
            'message': f'Multiple faces detected ({len(face_locations)})'
        }
    
    # Validate quality of the detected face
    face_location = face_locations[0]
    quality_result = validate_face_quality(frame, face_location, detector)
    
    return {
        'is_valid': quality_result['is_valid'],
        'num_faces': 1,
        'face_location': face_location,
        'quality_score': quality_result['quality_score'],
        'quality_checks': quality_result['quality_checks'],
        'brightness_mean': quality_result['brightness_mean'],
        'brightness_std': quality_result['brightness_std'],
        'laplacian_var': quality_result['laplacian_var'],
        'errors': quality_result['errors'],
        'error': quality_result.get('error', 'low_quality') if not quality_result['is_valid'] else None
    }

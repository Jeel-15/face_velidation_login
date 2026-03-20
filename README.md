# Face Verification Login System

A production-grade face authentication system with passive anti-spoof detection, built with Flask, OpenCV, and face_recognition.

## Features

✓ **Two-step login**: Credentials verification + face matching
✓ **No user action required**: No blink/smile/head movement challenges
✓ **Passive anti-spoof**: Quality gates + motion analysis + texture analysis  
✓ **Multiple embeddings**: Stores 8-12 face embeddings per user for robust matching
✓ **Security-first**: Server-side verification, rate limiting, audit logging
✓ **Production-ready**: Clean architecture, modular code, comprehensive error handling

## Project Structure

```
face_dete_login/
├── app.py                 # Flask backend application
├── config.py              # Configuration and constants
├── database.py            # SQLite database models
├── face_utils.py          # Face detection and recognition
├── anti_spoof.py          # Passive liveness detection
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates
│   ├── login.html        # Login page
│   ├── enroll.html       # Enrollment page
│   ├── dashboard.html    # User dashboard
│   └── verify.html       # Verification status
├── static/
│   ├── css/
│   │   └── style.css     # Stylesheet
│   └── js/
│       ├── common.js     # Shared utilities
│       ├── enroll.js     # Enrollment logic
│       └── face_verify.js # Verification logic
├── logs/                 # Verification logs
├── face_login.db         # SQLite database (auto-created)
└── README.md

```

## Installation

### 1. Install Python Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Create Database

Database is automatically initialized on first run.

### 3. Verify Installation

```bash
python app.py
```

Server should start on `http://localhost:5000`

## Quick Start

### 1. Create a User (Admin Task)

Using curl or Postman:

```bash
curl -X POST http://localhost:5000/api/admin/create-user \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "john_doe",
    "password": "secure_password_123",
    "email": "john@example.com"
  }'
```

Response:
```json
{
  "success": true,
  "message": "User created. User can now enroll their face.",
  "user_id": "john_doe"
}
```

### 2. Enroll Face

1. Go to `http://localhost:5000/enroll`
2. Enter user_id and password
3. Click "Start Capture" 5-6 times (each capture = ~3 seconds, collects ~20-25 frames)
4. System will automatically complete enrollment once 8+ valid samples are collected

### 3. Login with Face

1. Go to `http://localhost:5000/`
2. Enter user_id and password
3. Click "Next: Face Verification"
4. Click "Start Capture" and look at camera for ~2 seconds
5. System verifies face and checks liveness
6. If all checks pass: Login successful!

## Configuration

All thresholds and settings are in `config.py`:

### Face Quality Gates
- `MIN_FACE_SIZE_RATIO`: Minimum face width as % of frame (default: 15%)
- `BLUR_THRESHOLD`: Laplacian variance for sharpness (default: 100)
- `MIN_BRIGHTNESS`, `MAX_BRIGHTNESS`: Acceptable brightness range (default: 30-225)
- `MAX_FACE_YAW`, `MAX_FACE_PITCH`, `MAX_FACE_ROLL`: Face angle limits

### Anti-Spoof Parameters
- `MOTION_ANALYSIS_FRAMES`: Frames for motion analysis (default: 5)
- `SUSPICIOUS_MOTION_RATIO`: Threshold for suspicious motion pattern (default: 0.7)
- `TEXTURE_ANALYSIS_FOCUS_PERCENT`: Face region to analyze (default: 30%)
- `LOW_TEXTURE_THRESHOLD`: Below = likely photo (default: 5.0)
- `HIGH_TEXTURE_THRESHOLD`: Above = possible moire artifacts (default: 120.0)

### Face Matching
- `FACE_MATCH_TOLERANCE`: Distance threshold for matching (default: 0.6)
- `MIN_MATCH_RATIO`: % of stored embeddings to match (default: 50%)

### Enrollment
- `ENROLLMENT_TARGET_SAMPLES`: Goal number of embeddings (default: 10)
- `ENROLLMENT_MIN_SAMPLES`: Minimum required for enrollment (default: 8)

### Rate Limiting
- `MAX_LOGIN_ATTEMPTS_PER_HOUR`: Login attempt limit (default: 10)
- `MAX_VERIFY_ATTEMPTS_PER_LOGIN`: Face verification retries (default: 3)

## Testing Guide

### Test 1: Real Face (Expected: ✓ Login Success)

1. Enroll with your actual face
2. Ensure good lighting (not too dark, not backlighting)
3. Keep face at normal distance (~30-60cm)
4. Login and let system analyze
5. **Result**: High motion score, natural texture, face matches → Success

### Test 2: Printed Photo (Expected: ✗ Spoof Rejected)

1. Print a high-quality color photo of the enrolled face
2. Hold photo at camera
3. Slightly move the photo
4. System will analyze
5. **Expected**: Low motion score (background moves with face), uniform texture, no match → Rejected

### Test 3: Phone Screen Replay (Expected: ✗ Spoof Rejected)

1. Open a video of the enrolled face on a phone/tablet
2. Play video at camera
3. System will capture several frames
4. **Expected**: Motion pattern suspicious, texture looks artificial, frame-to-frame inconsistency → Rejected

### Test 4: Poor Lighting (Expected: ✗ Low Quality → Retry)

1. Turn off lights or cover camera light
2. Attempt login
3. **Expected**: Quality check fails (low brightness + low variance), shows retry message

### Test 5: Small/Far Face (Expected: ✗ Low Quality → Retry)

1. Sit far from camera (>1 meter)
2. Attempt login
3. **Expected**: Face size check fails, shows retry message

### Test 6: Extreme Face Angle (Expected: ✗ Low Quality → Retry)

1. Turn head ~45 degrees while logging in
2. **Expected**: Face angle check fails during enrollment or verification

### Test 7: Blurry Face (Expected: ✗ Low Quality → Retry)

1. Quickly move head during capture
2. **Expected**: Blur detection (low Laplacian variance) fails, shows retry message

### Test 8: Multiple Retries (Expected: ✗ Max Attempts → Locked)

1. Try spoof 3 times (max attempts)
2. **Expected**: System locks and shows "Too many attempts"

## Security Considerations

### Backend-Side Verification
- All face matching is done on server (never trust frontend only)
- Embeddings are stored as binary blobs in database
- Quality and anti-spoof decisions are made server-side

### Rate Limiting
- 10 login attempts per hour per user
- 3 verification retries per login session
- Prevents brute force attacks

### Audit Logging
Every verification attempt is logged with:
- User ID
- Timestamp
- Match distance
- Anti-spoof scores
- Quality scores
- Success/failure
- IP address
- User agent

Access logs at: `logs/verification.log`

### Password Security
- Passwords hashed with Werkzeug's PBKDF2 implementation
- Never sent to frontend after login

## Architecture

### Frontend -> Backend Flow

```
User enters credentials
    ↓
[Backend] Verify password hash
    ↓
[Frontend] Open webcam, capture 2 seconds of video
    ↓
[Frontend] Encode frames as JPEG + base64
    ↓
[Backend] Receive frames, decode
    ↓
[Backend] Quality validation (brightness, blur, face size, face angle)
    ↓
[Backend] Liveness analysis:
  ├─ Motion analysis (face vs background movement)
  ├─ Texture analysis (skin texture characteristics)
  └─ Temporal consistency
    ↓
[Backend] Face matching (compare with stored embeddings)
    ↓
[Backend] Log attempt and return decision
    ↓
[Frontend] Display result or ask for retry
```

### Anti-Spoof Logic Flow

For each captured frame:
1. **Quality Gate**: Check brightness, blur, face size, face angle
2. **Quality Processing**: Only use frames that pass quality gate
3. **Motion Analysis**: Compare face movement vs background movement
   - Real face → concentrated motion in face region
   - Photo/screen → similar motion in face and background
4. **Texture Analysis**: Analyze skin texture in face center
   - Real skin → natural texture variance (10-80)
   - Photo → low texture variance (<5)
   - Screen → either very low or very high variance (>120)
5. **Temporal Analysis**: Aggregate across all frames
6. **Decision**: Combine motion + texture + quality scores
   - Score ≥ 0.75: Accept (likely live)
   - Score ≤ 0.35: Reject (likely spoof)
   - Between: Ask to retry (uncertain)

## Database Schema

### Users Table
```sql
- id (primary key)
- user_id (unique)
- password_hash
- email
- is_enrolled (boolean)
- created_at
- enrollment_completed_at
```

### Face Embeddings Table
```sql
- id (primary key)
- user_id (foreign key)
- embedding (binary 128-byte vector)
- embedding_json (JSON string for uniqueness check)
- quality_score (0-1)
- created_at
- is_active (boolean)
```

### Verification Logs Table
```sql
- id (primary key)
- user_id (foreign key)
- attempt_type (enrollment/login)
- success (boolean)
- match_distance (0-1)
- anti_spoof_score (0-1)
- quality_score (0-1)
- motion_score (0-1)
- texture_score (0-1)
- num_frames (integer)
- error_reason (string)
- timestamp
- ip_address
- user_agent
```

## Troubleshooting

### "Could not access webcam"
- Check browser camera permissions
- On Windows: Settings → Privacy → Camera
- On Mac: System Preferences → Security & Privacy → Camera
- Ensure no other app is using camera

### "Face too small"
- Move closer to camera (30-60cm optimal)
- Ensure face is clearly visible
- Check camera resolution

### "Face too blurry"
- Ensure good lighting
- Keep camera steady
- Face should be sharp and clear

### "Multiple faces detected"
- Only one person in frame
- Remove background people or objects
- Ensure clean background

### Enrollment stuck at low sample count
- Check lighting in enrollment room
- Ensure face is clearly visible each capture
- Try different angles/positions each time

### Login always fails with same user
- Verify user is actually enrolled (check `is_enrolled` in database)
- Try re-enrollment if embeddings seem poor

## Production Deployment

### Checklist

1. **Change Secret Key**
   ```python
   # In app.py or environment
   os.environ['SECRET_KEY'] = 'your-strong-random-key'
   ```

2. **Add Admin Authentication**
   - Implement proper auth for `/api/admin/create-user` endpoint
   - Use JWT tokens or similar

3. **Use Production Database**
   - Consider PostgreSQL instead of SQLite
   - Update connection string in config

4. **Use Production Server**
   - Don't use Flask dev server (set `debug=False`)
   - Use Gunicorn, uWSGI, or similar
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

5. **Use HTTPS**
   - SSL certificates (Let's Encrypt)
   - Reverse proxy (nginx)

6. **Rate Limiting**
   - Implement Redis-backed rate limiting for production scale
   - Consider API gateway (e.g., nginx)

7. **Monitoring**
   - Log analysis and alerting
   - Monitor verification logs for patterns
   - Alert on high spoof detection rates

8. **Backup**
   - Regular database backups
   - Backup face embeddings

9. **GDPR Compliance**
   - Implement data retention policies
   - Allow users to request face data deletion

## Known Limitations & Future Improvements

### Current Limitations
- Single quality model (no expression variation)
- No face anti-spoofing with advanced techniques (though passive checks are good)
- Basic texture analysis (could use CNN-based features)
- No multi-face support (by design)
- Enrollment requires 8+ samples

### Future Improvements

1. **Advanced Anti-Spoof**
   - Use pre-trained CNN models (e.g., MobileNetV2)
   - Frequency domain analysis (FFT for screen artifacts)
   - Reflection detection for glass/screen covers
   - Remote photoplethysmography (rPPG) for blood flow detection

2. **Better Face Matching**
   - Use larger face encodings (512-d instead of 128)
   - Try other models: VGGFace2, ArcFace, FaceNet
   - Implement adaptive thresholding per user

3. **Enrollment Improvements**
   - Collect embeddings across multiple sessions
   - Require different face angles (yaw, pitch)
   - Update embeddings after successful logins (continual learning)

4. **UI/UX Enhancements**
   - Real-time quality feedback during enrollment
   - Live face overlay with quality visualization
   - Mobile app support
   - Progressive enrollment (add more samples over time)

5. **Scalability**
   - Implement caching for embeddings
   - Use clustering for faster face matching
   - Parallel frame processing

6. **Analytics**
   - Dashboard for admins to view verification statistics
   - Detect suspicious patterns
   - False positive/negative analysis

7. **Liveness**
   - Eye gaze direction (look at specific points)
   - But without explicit user action required

## Performance Notes

- Face detection: ~50-100ms per frame (HoG model)
- Face embedding: ~50ms per frame
- Face matching: <1ms for 10 stored embeddings
- Total login time: ~3-5 seconds (capture + processing)
- Total enrollment time: ~30-40 seconds (5-6 captures)

## License

Designed as a reference implementation. Modify and use as needed.

## Support & Questions

Check logs at `logs/verification.log` for detailed debugging information.

---

**Built with**: Flask, OpenCV, face_recognition, SQLite
**Python Version**: 3.8+

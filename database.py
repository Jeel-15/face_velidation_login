"""
Database initialization and models for face verification system.
Using SQLite with a clean, production-ready schema.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn
    
    def init_db(self):
        """Initialize database schema if not exists."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                is_admin BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_enrolled BOOLEAN DEFAULT 0,
                enrollment_completed_at DATETIME,
                last_login_at DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Face embeddings table (multiple embeddings per user for robust matching)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                embedding_json TEXT NOT NULL,
                quality_score REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                UNIQUE(user_id, embedding_json)
            )
        ''')
        
        # Verification attempts log (for security audit and rate limiting)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                attempt_type TEXT,
                success BOOLEAN,
                match_distance REAL,
                min_distance REAL,
                avg_distance REAL,
                anti_spoof_score REAL,
                quality_score REAL,
                motion_score REAL,
                texture_score REAL,
                num_frames INTEGER,
                error_reason TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Enrollment progress (for ongoing enrollments)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enrollment_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT UNIQUE NOT NULL,
                num_samples_collected INTEGER DEFAULT 0,
                embeddings_json TEXT,
                status TEXT DEFAULT 'in_progress',
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Create indexes for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_embeddings_user_id ON face_embeddings(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_user_id ON verification_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON verification_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_user_id ON enrollment_sessions(user_id)')

        # Safe migration for older database files.
        self.migrate_face_verification_toggle(conn=conn)
        
        conn.commit()
        conn.close()

    def migrate_face_verification_toggle(self, conn=None):
        """
        Add face_verification_enabled column to users table.
        Safe to call multiple times.
        """
        owns_connection = conn is None
        connection = conn or self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA table_info(users)")
            existing_columns = {row['name'] for row in cursor.fetchall()}
            if 'face_verification_enabled' not in existing_columns:
                cursor.execute(
                    "ALTER TABLE users ADD COLUMN face_verification_enabled INTEGER DEFAULT 1"
                )
                logger.info("[MIGRATION] Added face_verification_enabled column to users table")
            elif owns_connection:
                logger.debug("[MIGRATION] face_verification_enabled column already exists")

            if owns_connection:
                connection.commit()
        except sqlite3.OperationalError as exc:
            if 'duplicate column' in str(exc).lower():
                if owns_connection:
                    connection.commit()
                logger.debug("[MIGRATION] face_verification_enabled column already exists")
            else:
                if owns_connection:
                    connection.rollback()
                logger.error(f"[MIGRATION] Failed adding face_verification_enabled: {exc}")
                raise
        finally:
            if owns_connection:
                connection.close()
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, user_id, password_hash, email=None):
        """Create a new user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (user_id, password_hash, email)
                VALUES (?, ?, ?)
            ''', (user_id, password_hash, email))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_user(self, user_id):
        """Get user by user_id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    def get_user_by_id(self, id):
        """Get user by database id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (id,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    def mark_enrollment_complete(self, user_id):
        """Mark user as enrolled."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET is_enrolled = 1, enrollment_completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    # ==================== EMBEDDING OPERATIONS ====================
    
    def add_face_embedding(self, user_id, embedding, embedding_json, quality_score=None):
        """
        Add a face embedding for a user.
        embedding: numpy array or bytes
        embedding_json: JSON string of embedding for unique constraint
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Convert numpy array to bytes if needed
            if isinstance(embedding, list):
                embedding_bytes = json.dumps(embedding).encode()
            else:
                embedding_bytes = embedding
            
            cursor.execute('''
                INSERT INTO face_embeddings (user_id, embedding, embedding_json, quality_score)
                VALUES (?, ?, ?, ?)
            ''', (user_id, embedding_bytes, embedding_json, quality_score))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplicate embedding, skip
            return False
        finally:
            conn.close()
    
    def get_user_embeddings(self, user_id, active_only=True):
        """Get all embeddings for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('''
                SELECT embedding_json FROM face_embeddings 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at ASC
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT embedding_json FROM face_embeddings 
                WHERE user_id = ?
                ORDER BY created_at ASC
            ''', (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        embeddings = []
        for row in rows:
            try:
                embedding = json.loads(row['embedding_json'])
                embeddings.append(embedding)
            except:
                pass
        
        return embeddings
    
    def count_user_embeddings(self, user_id):
        """Count active embeddings for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM face_embeddings 
            WHERE user_id = ? AND is_active = 1
        ''', (user_id,))
        count = cursor.fetchone()['count']
        conn.close()
        return count
    
    # ==================== ENROLLMENT SESSION ====================
    
    def create_enrollment_session(self, user_id):
        """Create a new enrollment session."""
        import uuid
        session_id = str(uuid.uuid4())
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO enrollment_sessions (user_id, session_id)
            VALUES (?, ?)
        ''', (user_id, session_id))
        conn.commit()
        conn.close()
        return session_id
    
    def get_enrollment_session(self, session_id):
        """Get enrollment session details."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM enrollment_sessions WHERE session_id = ?', (session_id,))
        session = cursor.fetchone()
        conn.close()
        return dict(session) if session else None
    
    def update_enrollment_session(self, session_id, num_samples, embeddings_json=None):
        """Update enrollment session with new samples."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE enrollment_sessions 
            SET num_samples_collected = ?, embeddings_json = ?
            WHERE session_id = ?
        ''', (num_samples, embeddings_json, session_id))
        conn.commit()
        conn.close()
    
    def complete_enrollment_session(self, session_id):
        """Mark enrollment session as complete."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE enrollment_sessions 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
        ''', (session_id,))
        conn.commit()
        conn.close()
    
    def clear_old_enrollment_sessions(self, user_id):
        """Clear old enrollment sessions for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM enrollment_sessions 
            WHERE user_id = ? AND status = 'in_progress'
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    # ==================== VERIFICATION LOGGING ====================
    
    def get_recent_login_attempts(self, user_id, hours=1):
        """Get recent FAILED login attempts for rate limiting."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM verification_logs
            WHERE user_id = ? AND attempt_type = 'login' AND success = 0
            AND timestamp > datetime('now', ? || ' hours')
        ''', (user_id, -hours))
        count = cursor.fetchone()['count']
        conn.close()
        return count
    
    def get_verification_logs(self, user_id, limit=100):
        """Get verification logs for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM verification_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return logs
    
    # ==================== ADMIN FUNCTIONS ====================
    
    def set_admin_status(self, user_id, is_admin=True):
        """Set or remove admin privileges for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET is_admin = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (1 if is_admin else 0, user_id))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    
    def is_admin(self, user_id):
        """Check if user has admin privileges."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result['is_admin'] == 1 if result else False
    
    def get_all_users_admin(self, include_inactive=False):
        """Get all users with detailed info (admin view)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if include_inactive:
            cursor.execute('''
                SELECT 
                    user_id, email, is_admin, is_active, is_enrolled, face_verification_enabled,
                    created_at, enrollment_completed_at, last_login_at,
                    (SELECT COUNT(*) FROM face_embeddings WHERE user_id = users.user_id) as num_embeddings,
                    (SELECT COUNT(*) FROM verification_logs WHERE user_id = users.user_id AND success = 1) as successful_logins,
                    (SELECT COUNT(*) FROM verification_logs WHERE user_id = users.user_id AND success = 0) as failed_logins
                FROM users
                ORDER BY created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT 
                    user_id, email, is_admin, is_active, is_enrolled, face_verification_enabled,
                    created_at, enrollment_completed_at, last_login_at,
                    (SELECT COUNT(*) FROM face_embeddings WHERE user_id = users.user_id) as num_embeddings,
                    (SELECT COUNT(*) FROM verification_logs WHERE user_id = users.user_id AND success = 1) as successful_logins,
                    (SELECT COUNT(*) FROM verification_logs WHERE user_id = users.user_id AND success = 0) as failed_logins
                FROM users
                WHERE is_active = 1
                ORDER BY created_at DESC
            ''')
        
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return users
    
    def toggle_user_status(self, user_id, is_active):
        """Enable or disable a user account."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (1 if is_active else 0, user_id))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def set_face_verification_enabled(self, user_id, enabled):
        """Enable or disable biometric verification requirement for a user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE users
            SET face_verification_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (1 if enabled else 0, user_id)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0

    def update_user_profile(self, user_id, new_user_id=None, new_password_hash=None, new_email=None):
        """
        Update user profile and optionally rename user_id across related tables.
        Returns final user_id.
        """
        final_user_id = user_id
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN')

            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                raise ValueError('User not found')

            if new_password_hash is not None:
                cursor.execute(
                    '''
                    UPDATE users
                    SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (new_password_hash, user_id)
                )

            if new_email is not None:
                email_value = (new_email or '').strip() or None
                cursor.execute(
                    '''
                    UPDATE users
                    SET email = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (email_value, user_id)
                )

            if new_user_id and new_user_id != user_id:
                cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (new_user_id,))
                if cursor.fetchone():
                    raise ValueError(f"User ID '{new_user_id}' already exists")

                related_tables = [
                    'face_embeddings',
                    'verification_logs',
                    'enrollment_sessions',
                ]
                for table in related_tables:
                    cursor.execute(
                        f"UPDATE {table} SET user_id = ? WHERE user_id = ?",
                        (new_user_id, user_id)
                    )

                cursor.execute(
                    '''
                    UPDATE users
                    SET user_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (new_user_id, user_id)
                )
                final_user_id = new_user_id

            conn.commit()
            return final_user_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def log_verification_attempt(self, user_id, attempt_type, success, **kwargs):
        """
        Log a verification attempt for audit trail.
        attempt_type: 'enrollment' or 'login'
        success: boolean
        **kwargs: match_distance, min_distance, avg_distance, anti_spoof_score, quality_score, etc.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO verification_logs (
                user_id, attempt_type, success, match_distance, min_distance, avg_distance,
                anti_spoof_score, quality_score, motion_score, texture_score, num_frames,
                error_reason, ip_address, user_agent, session_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            attempt_type,
            success,
            kwargs.get('match_distance'),
            kwargs.get('min_distance'),
            kwargs.get('avg_distance'),
            kwargs.get('anti_spoof_score'),
            kwargs.get('quality_score'),
            kwargs.get('motion_score'),
            kwargs.get('texture_score'),
            kwargs.get('num_frames'),
            kwargs.get('error_reason'),
            kwargs.get('ip_address'),
            kwargs.get('user_agent'),
            kwargs.get('session_id'),
        ))
        conn.commit()
        conn.close()
    
    def get_system_stats(self):
        """Get system statistics for admin dashboard."""
        conn = self.get_connection()
        cursor = conn.cursor()
        stats = {}
        
        # Total users
        cursor.execute('SELECT COUNT(*) as count FROM users')
        stats['total_users'] = cursor.fetchone()['count']
        
        # Active users
        cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1')
        stats['active_users'] = cursor.fetchone()['count']
        
        # Enrolled users
        cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_enrolled = 1')
        stats['enrolled_users'] = cursor.fetchone()['count']
        
        # Admin users
        cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 1')
        stats['admin_users'] = cursor.fetchone()['count']
        
        # Total verification attempts today
        cursor.execute('''
            SELECT COUNT(*) as count FROM verification_logs
            WHERE DATE(timestamp) = DATE('now')
        ''')
        stats['verifications_today'] = cursor.fetchone()['count']
        
        # Successful logins today
        cursor.execute('''
            SELECT COUNT(*) as count FROM verification_logs
            WHERE DATE(timestamp) = DATE('now') AND success = 1 AND attempt_type = 'login'
        ''')
        stats['successful_logins_today'] = cursor.fetchone()['count']
        
        # Failed logins today
        cursor.execute('''
            SELECT COUNT(*) as count FROM verification_logs
            WHERE DATE(timestamp) = DATE('now') AND success = 0 AND attempt_type = 'login'
        ''')
        stats['failed_logins_today'] = cursor.fetchone()['count']
        
        # Total face embeddings
        cursor.execute('SELECT COUNT(*) as count FROM face_embeddings')
        stats['total_embeddings'] = cursor.fetchone()['count']
        
        # Total verification logs
        cursor.execute('SELECT COUNT(*) as count FROM verification_logs')
        stats['total_verifications'] = cursor.fetchone()['count']
        
        conn.close()
        return stats
    
    def delete_user(self, user_id):
        """Permanently delete a user and all their data."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Check user exists
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            conn.close()
            return False
        # Delete all related data
        cursor.execute('DELETE FROM face_embeddings WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM verification_logs WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True

    def get_user_verification_logs(self, user_id, limit=50):
        """Get verification logs for a specific user (for admin detail view)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM verification_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return logs

    def update_last_login(self, user_id):
        """Update user's last login timestamp."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET last_login_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()


# Singleton instance
_db = None

def get_db():
    """Get the database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db

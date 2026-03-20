#!/usr/bin/env python3
"""
Admin utility script for managing users in face verification system.
Useful for creating users from command line without HTTP requests.

Usage (run from the project root):
  python tools/admin.py create
  python tools/admin.py create john_doe
  python tools/admin.py list
  python tools/admin.py info john_doe
  python tools/admin.py reset john_doe
  python tools/admin.py delete john_doe
  python tools/admin.py make-admin john_doe
  python tools/admin.py remove-admin john_doe
"""

import sys
import os

# Allow imports from the project root regardless of where this script is run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from getpass import getpass
from werkzeug.security import generate_password_hash
from database import get_db

def create_user(user_id, password, email=None):
    """Create a new user."""
    db = get_db()
    
    # Check if user exists
    if db.get_user(user_id):
        print(f"❌ User '{user_id}' already exists")
        return False
    
    # Hash password
    password_hash = generate_password_hash(password)
    
    # Create user
    if db.create_user(user_id, password_hash, email):
        print(f"✓ User '{user_id}' created successfully")
        if email:
            print(f"  Email: {email}")
        print(f"\nNext steps:")
        print(f"1. Open http://localhost:5000/enroll")
        print(f"2. Enter credentials")
        print(f"3. Complete face enrollment")
        return True
    else:
        print(f"❌ Failed to create user '{user_id}'")
        return False

def list_users():
    """List all users in database."""
    db = get_db()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, email, is_enrolled, is_admin, is_active, created_at FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        print("No users found")
        return
    
    print(f"\n{'ID':<4} {'User ID':<20} {'Email':<25} {'Role':<12} {'Enrolled':<10} {'Status':<10} {'Created':<19}")
    print("-" * 105)
    
    for user in users:
        user_id = user['user_id']
        email = user['email'] or '-'
        role = '🛡️ Admin' if user['is_admin'] else 'User'
        enrolled = '✓' if user['is_enrolled'] else '✗'
        status = 'Active' if user['is_active'] else 'Inactive'
        created = user['created_at'][:19]
        print(f"{user['id']:<4} {user_id:<20} {email:<25} {role:<12} {enrolled:<10} {status:<10} {created:<19}")

def show_user_info(user_id):
    """Show detailed info about a user."""
    db = get_db()
    user = db.get_user(user_id)
    
    if not user:
        print(f"❌ User '{user_id}' not found")
        return
    
    embeddings_count = db.count_user_embeddings(user_id)
    logs = db.get_verification_logs(user_id, limit=10)
    
    print(f"\n--- User: {user_id} ---")
    print(f"Email: {user['email'] or 'Not set'}")
    print(f"Enrolled: {'Yes' if user['is_enrolled'] else 'No'}")
    print(f"Face Embeddings: {embeddings_count}")
    print(f"Created: {user['created_at']}")
    print(f"Enrollment Completed: {user['enrollment_completed_at'] or 'Not enrolled yet'}")
    
    if logs:
        print(f"\nRecent Verification Attempts (last 10):")
        print(f"{'Timestamp':<19} {'Type':<10} {'Success':<7} {'Reason':<30}")
        print("-" * 70)
        for log in logs:
            timestamp = log['timestamp'][:19]
            attempt_type = log['attempt_type']
            success = '✓' if log['success'] else '✗'
            reason = log['error_reason'] or 'Success'
            print(f"{timestamp:<19} {attempt_type:<10} {success:<7} {reason:<30}")

def reset_user_embeddings(user_id):
    """Delete all embeddings for a user (allows re-enrollment)."""
    db = get_db()
    user = db.get_user(user_id)
    
    if not user:
        print(f"❌ User '{user_id}' not found")
        return False
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM face_embeddings WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE users SET is_enrolled = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    print(f"✓ Cleared all embeddings for '{user_id}'")
    print(f"  User can now re-enroll their face.")
    return True

def delete_user(user_id, confirm=False):
    """Delete a user completely."""
    db = get_db()
    user = db.get_user(user_id)
    
    if not user:
        print(f"❌ User '{user_id}' not found")
        return False
    
    if not confirm:
        response = input(f"⚠ Are you sure you want to delete user '{user_id}'? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            return False
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM face_embeddings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM enrollment_sessions WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    print(f"✓ User '{user_id}' deleted successfully")
    return True

def make_admin(user_id):
    """Grant admin privileges to a user."""
    db = get_db()
    
    user = db.get_user(user_id)
    if not user:
        print(f"❌ User '{user_id}' not found")
        return False
    
    if db.is_admin(user_id):
        print(f"ℹ️  User '{user_id}' is already an admin")
        return True
    
    if db.set_admin_status(user_id, True):
        print(f"✓ Admin privileges granted to user '{user_id}'")
        print(f"\n{user_id} can now access:")
        print(f"- Admin Panel: http://localhost:5000/admin")
        print(f"- User Management")
        print(f"- System Statistics")
        print(f"- Activity Logs")
        return True
    else:
        print(f"❌ Failed to grant admin privileges")
        return False

def remove_admin(user_id):
    """Remove admin privileges from a user."""
    db = get_db()
    
    user = db.get_user(user_id)
    if not user:
        print(f"❌ User '{user_id}' not found")
        return False
    
    if not db.is_admin(user_id):
        print(f"ℹ️  User '{user_id}' is not an admin")
        return True
    
    if db.set_admin_status(user_id, False):
        print(f"✓ Admin privileges removed from user '{user_id}'")
        return True
    else:
        print(f"❌ Failed to remove admin privileges")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Admin utility for face verification system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python tools/admin.py create                    # Interactive user creation
  python tools/admin.py create john_doe           # Create with prompt for password
  python tools/admin.py list                      # List all users
  python tools/admin.py info john_doe             # Show user details
  python tools/admin.py reset john_doe            # Reset user embeddings
  python tools/admin.py delete john_doe           # Delete user
  python tools/admin.py make-admin john_doe       # Grant admin privileges
  python tools/admin.py remove-admin john_doe     # Revoke admin privileges
        '''
    )
    
    parser.add_argument('command', choices=['create', 'list', 'info', 'reset', 'delete', 'make-admin', 'remove-admin'],
                       help='Command to execute')
    parser.add_argument('user_id', nargs='?', help='User ID')
    parser.add_argument('--password', help='Password (will prompt if not provided)')
    parser.add_argument('--email', help='Email address')
    parser.add_argument('--force', action='store_true', help='Skip confirmations')
    
    args = parser.parse_args()
    
    if args.command == 'create':
        if not args.user_id:
            args.user_id = input("Enter user ID: ").strip()
        
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        
        if args.password:
            password = args.password
        else:
            password = getpass("Enter password: ")
            password_confirm = getpass("Confirm password: ")
            if password != password_confirm:
                print("❌ Passwords don't match")
                sys.exit(1)
        
        if not password or len(password) < 6:
            print("❌ Password must be at least 6 characters")
            sys.exit(1)
        
        if args.email:
            email = args.email
        else:
            email = input("Enter email (optional, press Enter to skip): ").strip() or None
        
        create_user(args.user_id, password, email)
    
    elif args.command == 'list':
        list_users()
    
    elif args.command == 'info':
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        show_user_info(args.user_id)
    
    elif args.command == 'reset':
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        reset_user_embeddings(args.user_id)
    
    elif args.command == 'delete':
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        delete_user(args.user_id, confirm=args.force)
    
    elif args.command == 'make-admin':
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        make_admin(args.user_id)
    
    elif args.command == 'remove-admin':
        if not args.user_id:
            print("❌ User ID required")
            sys.exit(1)
        remove_admin(args.user_id)

if __name__ == '__main__':
    main()

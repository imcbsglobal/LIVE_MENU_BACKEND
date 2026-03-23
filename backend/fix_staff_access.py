"""
fix_staff_access.py
==================
Run this ONCE on your server to add the allowed_pages column to the app_users table.
This enables per-staff sidebar page access control by the Company Admin.

USAGE (on the server, in the backend/ folder):
    python fix_staff_access.py

It will:
  1. Add the allowed_pages column to app_users table in PostgreSQL
  2. Verify the column exists
  3. Check views.py and urls.py have the new endpoint
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.db import connection

print("\n🔧 fix_staff_access.py — Starting...\n")

# ── Step 1: Add the column if it doesn't exist ────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'app_users'
          AND column_name = 'allowed_pages'
    """)
    exists = cursor.fetchone()

    if exists:
        print("✅ Column 'allowed_pages' already exists in app_users table.")
    else:
        print("➕ Adding 'allowed_pages' column to app_users table...")
        cursor.execute("""
            ALTER TABLE app_users
            ADD COLUMN allowed_pages JSONB DEFAULT NULL
        """)
        print("✅ Column added successfully!")

# ── Step 2: Verify ────────────────────────────────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'app_users'
          AND column_name = 'allowed_pages'
    """)
    row = cursor.fetchone()
    if row:
        print(f"✅ Verified: column '{row[0]}' type '{row[1]}' exists in app_users.")
    else:
        print("❌ Column NOT found after insert — something went wrong.")
        sys.exit(1)

# ── Step 3: Check urls.py has the route ──────────────────────────────────────
urls_path = BASE_DIR / 'api' / 'urls.py'
if urls_path.exists():
    content = urls_path.read_text()
    if 'save_staff_access' in content:
        print("✅ urls.py already has save_staff_access route.")
    else:
        print("❌ urls.py is missing save_staff_access route!")
        print("   → Please replace api/urls.py with the updated version.")
else:
    print("⚠️  Could not find api/urls.py to check.")

# ── Step 4: Check views.py has the function ───────────────────────────────────
views_path = BASE_DIR / 'api' / 'views.py'
if views_path.exists():
    content = views_path.read_text()
    if 'def save_staff_access' in content:
        print("✅ views.py already has save_staff_access function.")
    else:
        print("❌ views.py is missing save_staff_access function!")
        print("   → Please replace api/views.py with the updated version.")
else:
    print("⚠️  Could not find api/views.py to check.")

print("\n🎉 Done! Now restart your server:")
print("   sudo systemctl restart gunicorn")
print("   OR: kill daphne and restart it\n")
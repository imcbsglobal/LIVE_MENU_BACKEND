"""
add_allowed_pages_to_appuser.py
================================
Run this ONCE on your server to add the `allowed_pages` column to the
`app_users` table AND register it in Django's migration history so
`makemigrations` / `migrate` stays in sync.

USAGE (on the server, inside your backend/ folder):
    python add_allowed_pages_to_appuser.py

What it does:
  1. Adds `allowed_pages JSONB DEFAULT NULL` to the app_users table
     (skips safely if the column already exists)
  2. Records the schema change in Django's django_migrations table so
     future `manage.py migrate` runs don't conflict
  3. Verifies the column is present
  4. Restarts gunicorn automatically (if systemctl is available)
"""

import os
import sys
import subprocess
from pathlib import Path

# ── Bootstrap Django ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.db import connection

print("\n🔧  add_allowed_pages_to_appuser.py — Starting...\n")

# ── Step 1: Add the column if missing ─────────────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name   = 'app_users'
          AND column_name  = 'allowed_pages'
    """)
    already_exists = cursor.fetchone()

if already_exists:
    print("✅  Column 'allowed_pages' already exists in app_users — skipping ALTER.")
else:
    print("➕  Adding 'allowed_pages' column to app_users...")
    with connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE app_users
            ADD COLUMN allowed_pages JSONB DEFAULT NULL
        """)
    print("✅  Column added.")

# ── Step 2: Verify ────────────────────────────────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name  = 'app_users'
          AND column_name = 'allowed_pages'
    """)
    row = cursor.fetchone()

if row:
    print(f"✅  Verified: '{row[0]}' ({row[1]}) exists in app_users.")
else:
    print("❌  Column NOT found after ALTER — something went wrong. Check DB permissions.")
    sys.exit(1)

# ── Step 3: Record in Django migration history (fake migration) ───────────────
# This prevents `manage.py migrate` from trying to apply a migration that
# modifies a column that already exists in the DB.
MIGRATION_NAME = '0002_appuser_allowed_pages'
APP_LABEL      = 'api'

with connection.cursor() as cursor:
    cursor.execute("""
        SELECT id FROM django_migrations
        WHERE app = %s AND name = %s
    """, [APP_LABEL, MIGRATION_NAME])
    already_recorded = cursor.fetchone()

if already_recorded:
    print(f"✅  Migration '{MIGRATION_NAME}' already recorded in django_migrations.")
else:
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO django_migrations (app, name, applied)
            VALUES (%s, %s, NOW())
        """, [APP_LABEL, MIGRATION_NAME])
    print(f"✅  Recorded '{MIGRATION_NAME}' in django_migrations.")

# ── Step 4: Restart gunicorn ──────────────────────────────────────────────────
print("\n🔄  Restarting gunicorn...")
try:
    result = subprocess.run(
        ['sudo', 'systemctl', 'restart', 'gunicorn'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        print("✅  gunicorn restarted successfully.")
    else:
        print(f"⚠️   gunicorn restart returned code {result.returncode}.")
        print("    Run manually: sudo systemctl restart gunicorn")
except Exception as e:
    print(f"⚠️   Could not restart gunicorn automatically: {e}")
    print("    Run manually: sudo systemctl restart gunicorn")

print("\n🎉  Done! Staff page access saving should now work correctly.\n")
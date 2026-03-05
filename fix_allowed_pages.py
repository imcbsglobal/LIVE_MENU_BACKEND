"""
fix_allowed_pages.py
====================
Run this ONCE on your server to add the allowed_pages column
AND register the new URL — no migrations needed.

USAGE (on the server, in the backend/ folder):
    python fix_allowed_pages.py

It will:
  1. Add the allowed_pages column to company_info table in PostgreSQL
  2. Print success/failure clearly
"""

import os
import sys
from pathlib import Path

# ── Load Django settings ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.db import connection

print("\n🔧 fix_allowed_pages.py — Starting...\n")

# ── Step 1: Add the column if it doesn't exist ────────────────────────────────
with connection.cursor() as cursor:
    # Check if column already exists
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'company_info'
          AND column_name = 'allowed_pages'
    """)
    exists = cursor.fetchone()

    if exists:
        print("✅ Column 'allowed_pages' already exists in company_info table.")
    else:
        print("➕ Adding 'allowed_pages' column to company_info table...")
        cursor.execute("""
            ALTER TABLE company_info
            ADD COLUMN allowed_pages JSONB DEFAULT NULL
        """)
        print("✅ Column added successfully!")

# ── Step 2: Verify ────────────────────────────────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'company_info'
          AND column_name = 'allowed_pages'
    """)
    row = cursor.fetchone()
    if row:
        print(f"✅ Verified: column '{row[0]}' type '{row[1]}' exists.")
    else:
        print("❌ Column NOT found after insert — something went wrong.")
        sys.exit(1)

# ── Step 3: Check urls.py has the route ──────────────────────────────────────
urls_path = BASE_DIR / 'api' / 'urls.py'
if urls_path.exists():
    content = urls_path.read_text()
    if 'save_user_pages' in content:
        print("✅ urls.py already has save_user_pages route.")
    else:
        print("❌ urls.py is missing save_user_pages route!")
        print("   → Please replace api/urls.py with the updated version.")
else:
    print("⚠️  Could not find api/urls.py to check.")

# ── Step 4: Check views.py has the function ───────────────────────────────────
views_path = BASE_DIR / 'api' / 'views.py'
if views_path.exists():
    content = views_path.read_text(encoding='utf-8', errors='ignore')
    if 'def save_user_pages' in content:
        print("✅ views.py already has save_user_pages function.")
    else:
        print("❌ views.py is missing save_user_pages function!")
        print("   → Please replace api/views.py with the updated version.")
else:
    print("⚠️  Could not find api/views.py to check.")

# ── Step 5: Print all users so admin can see correct IDs ─────────────────────
from api.models import AppUser
print("\n── Current AppUser records ──────────────────────────────")
for u in AppUser.objects.select_related('company').order_by('id'):
    print(f"  id={u.id:4d}  username={u.username:20s}  client_id={u.company.client_id}  user_type={u.user_type}")
print("─────────────────────────────────────────────────────────\n")

print("\n🎉 Done! Now restart your server:")
print("   sudo systemctl restart gunicorn")
print("   OR: kill daphne and restart it\n")
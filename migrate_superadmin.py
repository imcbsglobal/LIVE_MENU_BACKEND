"""
migrate_superadmin.py
=====================
Run ONCE on your server to:
  1. Add 'superadmin' to the user_type column choices
  2. Make the client_id (company FK) column nullable in app_users
  3. Create the first Super Admin user

USAGE (from backend/ folder):
    python migrate_superadmin.py

It uses raw SQL so you don't need a new Django migration.
"""
import os, sys, getpass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.db import connection
from django.contrib.auth.hashers import make_password
from api.models import AppUser

print("\n=== migrate_superadmin.py ===\n")

# ── Step 1: Make client_id column nullable ─────────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT is_nullable
        FROM information_schema.columns
        WHERE table_name = 'app_users' AND column_name = 'client_id'
    """)
    row = cursor.fetchone()
    if row and row[0] == 'NO':
        print("Making app_users.client_id nullable...")
        cursor.execute("ALTER TABLE app_users ALTER COLUMN client_id DROP NOT NULL")
        print("Done.")
    else:
        print("client_id is already nullable.")

# ── Step 2: Expand user_type column if needed ──────────────────────────────
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'app_users' AND column_name = 'user_type'
    """)
    row = cursor.fetchone()
    if row and row[0] and row[0] < 20:
        print("Expanding user_type column to varchar(20)...")
        cursor.execute("ALTER TABLE app_users ALTER COLUMN user_type TYPE varchar(20)")
        print("Done.")
    else:
        print("user_type column size is fine.")

# ── Step 3: Show existing users ────────────────────────────────────────────
print("\nExisting AppUser records:")
for u in AppUser.objects.all().order_by('id'):
    cid = u.company.client_id if u.company else 'NULL'
    print(f"  id={u.id:3d}  type={u.user_type:12s}  username={u.username:25s}  client_id={cid}")

# ── Step 4: Create Super Admin ─────────────────────────────────────────────
print("\n--- Create Super Admin ---")
if AppUser.objects.filter(user_type='superadmin').exists():
    print("A Super Admin already exists. Skipping creation.")
else:
    username  = input("Super Admin username: ").strip()
    password  = getpass.getpass("Password: ")
    confirm   = getpass.getpass("Confirm password: ")

    if not username:
        print("Username cannot be empty. Skipping.")
    elif password != confirm:
        print("Passwords do not match. Skipping.")
    elif AppUser.objects.filter(username=username).exists():
        print(f'Username "{username}" already taken. Skipping.')
    else:
        AppUser.objects.create(
            company=None,
            username=username,
            password=make_password(password),
            full_name='Super Admin',
            user_type='superadmin',
            is_active=True,
        )
        print(f"\nSuper Admin '{username}' created successfully!")
        print(f"Secret code for login: {os.environ.get('SUPER_ADMIN_SECRET', 'ADMIN@2024')}")

print("\nDone! Restart your server:")
print("  sudo systemctl restart gunicorn  (or restart daphne)")
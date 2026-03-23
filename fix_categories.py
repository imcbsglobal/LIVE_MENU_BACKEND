import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from django.db import connection

print("\n=== Step 2: Backfill client_id ===")
with connection.cursor() as cursor:
    cursor.execute("""
        UPDATE api_category c
        SET client_id = ci.client_id
        FROM app_users u
        JOIN company_info ci ON ci.client_id = u.client_id
        WHERE c.username = u.username
          AND c.client_id = ''
    """)
    print(f"Backfilled {cursor.rowcount} categories")

print("\n=== Step 3: Show categories ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT c.id, c.name, c.client_id, COUNT(m.id) as items
        FROM api_category c
        LEFT JOIN api_menuitem m ON m.category_id = c.id
        GROUP BY c.id, c.name, c.client_id
        ORDER BY c.name, c.id
    """)
    for r in cursor.fetchall():
        print(f"  id={r[0]}  name='{r[1]}'  client_id='{r[2]}'  items={r[3]}")

print("\n=== Step 4: Fix duplicates ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT name, client_id, array_agg(id ORDER BY id)
        FROM api_category
        GROUP BY name, client_id
        HAVING COUNT(*) > 1
    """)
    groups = cursor.fetchall()
    print(f"Found {len(groups)} duplicate group(s)")

with connection.cursor() as cursor:
    for name, client_id, ids in groups:
        keeper_id = ids[0]
        dupe_ids = ids[1:]
        print(f"\n  '{name}': keep id={keeper_id}, delete={dupe_ids}")
        cursor.execute("UPDATE api_menuitem SET category_id=%s WHERE category_id=ANY(%s)", [keeper_id, dupe_ids])
        print(f"    Reassigned {cursor.rowcount} menu item(s)")
        cursor.execute("DELETE FROM api_category WHERE id=ANY(%s)", [dupe_ids])
        print(f"    Deleted {cursor.rowcount} duplicate(s)")

print("\n=== Step 5: Verify ===")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT client_id, name FROM api_category
            GROUP BY client_id, name HAVING COUNT(*) > 1
        ) x
    """)
    print(f"Remaining duplicates: {cursor.fetchone()[0]} (should be 0)")

print("\nDone! Now run: python manage.py migrate api")
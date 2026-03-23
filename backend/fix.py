import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS allowed_pages JSONB DEFAULT NULL")
print("Done! Column added.")
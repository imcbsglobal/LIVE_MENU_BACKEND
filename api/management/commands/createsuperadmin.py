# api/management/commands/createsuperadmin.py
#
# UPDATED:
#   - user_type = 'superadmin'  (was 'admin')
#   - company   = None          (Super Admin is not tied to any company)
#   - No client_id required     (Super Admin has no company)
#
# Place this file at:
#   backend/api/management/commands/createsuperadmin.py
#
# Also create these two empty files if not already present:
#   backend/api/management/__init__.py
#   backend/api/management/commands/__init__.py
#
# ─────────────────────────────────────────────
# USAGE (from backend/ folder):
#
#   python manage.py createsuperadmin
#
#   Or non-interactive:
#   python manage.py createsuperadmin \
#       --username   superadmin \
#       --password   yourpassword \
#       --full_name  "Platform Admin"
#
# ─────────────────────────────────────────────

import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.conf import settings
from api.models import AppUser


class Command(BaseCommand):
    help = (
        'Create a Super Admin user (user_type=superadmin, company=None). '
        'This is a platform-level account — NOT tied to any company. '
        'It can see all companies and create Company Admins from the dashboard.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--username',  type=str, help='Super Admin username')
        parser.add_argument('--password',  type=str, help='Super Admin password')
        parser.add_argument('--full_name', type=str, default='Super Admin', help='Display name')

    def handle(self, *args, **options):

        self.stdout.write('\n─── Create Super Admin ───────────────────────────')
        self.stdout.write(
            'This creates a PLATFORM-LEVEL Super Admin.\n'
            'The account has no company — it manages all companies.\n'
        )

        # ── Username ──────────────────────────────────────────────────
        username = options.get('username') or input('Username: ').strip()
        if not username:
            raise CommandError('username is required.')

        if AppUser.objects.filter(username=username).exists():
            raise CommandError(
                f"Username '{username}' already exists. "
                "Choose a different one, or use migrate_superadmin.py to check existing users."
            )

        # ── Password ──────────────────────────────────────────────────
        password = options.get('password')
        if not password:
            password = getpass.getpass('Password: ')
            confirm  = getpass.getpass('Password (again): ')
            if password != confirm:
                raise CommandError('Passwords do not match.')
        if not password:
            raise CommandError('password is required.')
        if len(password) < 6:
            raise CommandError('Password must be at least 6 characters.')

        # ── Full name ─────────────────────────────────────────────────
        full_name = options.get('full_name') or 'Super Admin'

        # ── Create Super Admin ────────────────────────────────────────
        # company=None  → Super Admin is NOT tied to any company
        # user_type='superadmin' → gives platform-level access in views
        super_admin = AppUser.objects.create(
            company   = None,
            username  = username,
            password  = make_password(password),
            full_name = full_name,
            user_type = 'superadmin',
            is_active = True,
        )

        secret = getattr(settings, 'SUPER_ADMIN_SECRET', 'ADMIN@2024')

        self.stdout.write(self.style.SUCCESS(
            f'\n Super Admin created successfully!\n'
            f'   Username   : {super_admin.username}\n'
            f'   Full Name  : {super_admin.full_name}\n'
            f'   User Type  : {super_admin.user_type}\n'
            f'   Company    : None (platform-level)\n'
            f'\n'
            f'   Login URL    : /superadmin\n'
            f'   Secret code  : {secret}\n'
            f'   (Set SUPER_ADMIN_SECRET in settings.py to change this)\n'
        ))
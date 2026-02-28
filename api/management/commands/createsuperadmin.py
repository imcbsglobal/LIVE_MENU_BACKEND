# api/management/commands/createsuperadmin.py
#
# Place this file at:
#   backend/api/management/commands/createsuperadmin.py
#
# Also create these two empty files:
#   backend/api/management/__init__.py
#   backend/api/management/commands/__init__.py
#
# ─────────────────────────────────────────────
# USAGE (run from backend/ folder):
#
#   python manage.py createsuperadmin \
#       --client_id  ABC123 \
#       --username   admin \
#       --password   yourpassword \
#       --firm_name  "My Restaurant" \
#       --place      "Chennai"
#
# If you don't pass arguments, it will prompt you for each one.
# ─────────────────────────────────────────────

import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from api.models import CompanyInfo, AppUser


class Command(BaseCommand):
    help = 'Create a Super Admin user. Client ID comes from the licensing software.'

    def add_arguments(self, parser):
        parser.add_argument('--client_id',  type=str, help='Client ID from licensing software')
        parser.add_argument('--username',   type=str, help='Super Admin username')
        parser.add_argument('--password',   type=str, help='Super Admin password')
        parser.add_argument('--full_name',  type=str, default='', help='Full name (optional)')
        parser.add_argument('--firm_name',  type=str, default='', help='Company name (optional)')
        parser.add_argument('--place',      type=str, default='', help='Company place (optional)')

    def handle(self, *args, **options):

        # ── Get client_id ─────────────────────────────────────────────
        client_id = options.get('client_id') or input('Client ID (from licensing software): ').strip()
        if not client_id:
            raise CommandError('client_id is required.')

        # ── Get username ──────────────────────────────────────────────
        username = options.get('username') or input('Username: ').strip()
        if not username:
            raise CommandError('username is required.')

        # ── Get password (hidden prompt if not passed) ─────────────────
        password = options.get('password')
        if not password:
            password = getpass.getpass('Password: ')
            confirm  = getpass.getpass('Password (again): ')
            if password != confirm:
                raise CommandError('Passwords do not match.')
        if not password:
            raise CommandError('password is required.')

        # ── Check username is unique ──────────────────────────────────
        if AppUser.objects.filter(username=username).exists():
            raise CommandError(f"Username '{username}' already exists. Choose a different one.")

        # ── Get or create CompanyInfo for this client_id ──────────────
        try:
            company = CompanyInfo.objects.get(client_id=client_id)
            self.stdout.write(f"  Found company: {company.firm_name} ({company.place})")
        except CompanyInfo.DoesNotExist:
            # Company not in DB yet — create it now
            firm_name   = options.get('firm_name') or input('Company / Firm Name: ').strip() or 'My Company'
            place       = options.get('place')     or input('Place / City: ').strip()        or 'HQ'
            leasing_key = input('Leasing Key (press Enter to use ADMIN@2024): ').strip() or 'ADMIN@2024'

            company = CompanyInfo.objects.create(
                client_id   = client_id,
                firm_name   = firm_name,
                place       = place,
                leasing_key = leasing_key,
                is_active   = True,
            )
            self.stdout.write(self.style.SUCCESS(f"  Created company: {firm_name} ({place})"))

        # ── Create the Super Admin AppUser ─────────────────────────────
        full_name = options.get('full_name') or f'{company.firm_name} Administrator'

        super_admin = AppUser.objects.create(
            company   = company,
            username  = username,
            password  = make_password(password),
            full_name = full_name,
            user_type = 'admin',
            is_active = True,
        )

        self.stdout.write(self.style.SUCCESS(
            f"\n Super Admin created successfully!\n"
            f"   Client ID  : {company.client_id}\n"
            f"   Username   : {super_admin.username}\n"
            f"   Full Name  : {super_admin.full_name}\n"
            f"   Company    : {company.firm_name} ({company.place})\n"
            f"\n"
            f"   Secret code for login : {company.leasing_key}\n"
            f"   (Enter this in the secret code modal on the login page)\n"
        ))
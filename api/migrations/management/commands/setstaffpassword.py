# api/management/commands/setstaffpassword.py
#
# Interactive command to set (or change) the shared staff password.
# It generates a Django-safe PBKDF2 hash and writes it directly into
# settings.py so the admin never has to touch the shell manually.
#
# Place at:
#   backend/api/management/commands/setstaffpassword.py
#
# ── Usage ────────────────────────────────────────────────────────────────────
#
#   python manage.py setstaffpassword
#       → prompts for new password (hidden input), writes hash to settings.py
#
#   python manage.py setstaffpassword --username waiter --password mynewpass
#       → non-interactive, useful for CI / Docker entrypoints
#
# ── What it does ─────────────────────────────────────────────────────────────
#   1. Reads the current settings.py
#   2. Replaces the STAFF_USERNAME and STAFF_PASSWORD_HASH lines in-place
#   3. Prints the new hash so you can copy it elsewhere if needed
# ─────────────────────────────────────────────────────────────────────────────

import getpass
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password


# Path to the project settings file — adjust if your layout differs
SETTINGS_PATH = Path(__file__).resolve().parents[4] / 'backend' / 'settings.py'
# Fallback: walk up and find the first settings.py
def _find_settings():
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / 'settings.py'
        if candidate.exists():
            return candidate
        # Also check <parent>/backend/settings.py
        candidate2 = parent / 'backend' / 'settings.py'
        if candidate2.exists():
            return candidate2
    return None


class Command(BaseCommand):
    help = (
        'Set the shared staff login password (and optionally username) '
        'stored in settings.py. Both Waiter and Kitchen panels use these '
        'same credentials.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username', type=str, default=None,
            help='New shared staff username (default: keep existing / "staff")'
        )
        parser.add_argument(
            '--password', type=str, default=None,
            help='New plaintext password (will be hashed before saving). '
                 'Omit to be prompted securely.'
        )

    def handle(self, *args, **options):
        settings_file = _find_settings()
        if not settings_file or not settings_file.exists():
            raise CommandError(
                f'Could not locate settings.py. Searched from {Path(__file__)}. '
                'Set SETTINGS_PATH manually in this command file.'
            )

        self.stdout.write(f'  Settings file: {settings_file}')

        # ── Get new username ──────────────────────────────────────────────────
        new_username = options.get('username')
        if not new_username:
            existing = self._read_current_username(settings_file)
            prompted  = input(f'Staff username [{existing}]: ').strip()
            new_username = prompted or existing

        # ── Get new password ──────────────────────────────────────────────────
        new_password = options.get('password')
        if not new_password:
            new_password = getpass.getpass('New staff password: ')
            confirm      = getpass.getpass('Confirm password:   ')
            if new_password != confirm:
                raise CommandError('Passwords do not match. No changes made.')
        if not new_password:
            raise CommandError('Password cannot be empty.')
        if len(new_password) < 6:
            raise CommandError('Password must be at least 6 characters.')

        # ── Hash the password ─────────────────────────────────────────────────
        hashed = make_password(new_password)

        # ── Write to settings.py ──────────────────────────────────────────────
        self._write_to_settings(settings_file, new_username, hashed)

        self.stdout.write(self.style.SUCCESS(
            f'\n  Staff credentials updated successfully!\n'
            f'  Username : {new_username}\n'
            f'  Hash     : {hashed[:40]}…\n'
            f'\n'
            f'  Restart the Django server for the change to take effect.\n'
        ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _read_current_username(self, path: Path) -> str:
        text = path.read_text(encoding='utf-8')
        m = re.search(r'^STAFF_USERNAME\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
        return m.group(1) if m else 'staff'

    def _write_to_settings(self, path: Path, username: str, hashed: str):
        text = path.read_text(encoding='utf-8')

        # Replace existing STAFF_USERNAME line
        text, n1 = re.subn(
            r'^(STAFF_USERNAME\s*=\s*).*$',
            f'STAFF_USERNAME      = "{username}"',
            text, flags=re.MULTILINE
        )

        # Replace existing STAFF_PASSWORD_HASH line
        text, n2 = re.subn(
            r'^(STAFF_PASSWORD_HASH\s*=\s*).*$',
            f'STAFF_PASSWORD_HASH = "{hashed}"',
            text, flags=re.MULTILINE
        )

        if n1 == 0 or n2 == 0:
            # Lines don't exist yet — append the whole block
            text += f'\n\n# ── Staff shared credentials (written by setstaffpassword) ──\n'
            text += f'STAFF_USERNAME      = "{username}"\n'
            text += f'STAFF_PASSWORD_HASH = "{hashed}"\n'

        path.write_text(text, encoding='utf-8')
"""
Django settings for backend project with PostgreSQL.
"""

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-g1@x=5suku6)8_2!8w4*a6*_f*t03__r)l1we=-xm80nit-@1d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.23', '192.168.1.144']

# Application definition
INSTALLED_APPS = [
    'daphne',          # ← only here, at the top
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'channels',
    'api',
]

ASGI_APPLICATION = 'backend.asgi.application'

# ── Channel Layers ───────────────────────────────────────────────────────────
# Using InMemoryChannelLayer — no Redis needed for single-server deployments.
# For multi-server production, switch back to RedisChannelLayer.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Redis config (disabled — uncomment if you install and run Redis)
# CHANNEL_LAYERS = {
#     'default': {
#         'BACKEND': 'channels_redis.core.RedisChannelLayer',
#         'CONFIG': {
#             'hosts': [('127.0.0.1', 6379)],
#         },
#     },
# }

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # ── Explicit DB connection cleanup for ASGI/Daphne ──────────────────────
    # Calls django.db.close_old_connections() on every request start and end.
    # Prevents stale/leaked connections under high-concurrency async workloads.
    'backend.middleware.CloseOldConnectionsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'


# ============================================
# DATABASE - PostgreSQL Configuration
# ============================================
# ✅ FIX: Added CONN_MAX_AGE=60 so Django reuses DB connections instead of
#         opening a new connection on every request.
#         Without this, under load Django exhausts PostgreSQL's max_connections
#         limit (default 100), causing "sorry, too many clients already" errors.

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'Menu_db',
        'USER': 'postgres',
        'PASSWORD': '12345',
        'HOST': 'localhost',
        'PORT': '5432',
        # ── IMPORTANT: CONN_MAX_AGE must be 0 when running under ASGI/Daphne ──
        # Under WSGI, persistent connections are fine because each worker process
        # handles one request at a time. Under ASGI, many coroutine threads share
        # the same process — each gets its own DB connection with CONN_MAX_AGE>0,
        # exhausting PostgreSQL's max_connections (default 100) very quickly.
        # With CONN_MAX_AGE=0, Django closes the connection after every request.
        'CONN_MAX_AGE': 0,
        # Optional: also set connection pool limits at the PostgreSQL level by
        # running: ALTER SYSTEM SET max_connections = 200; (then restart PG)
    }
}

# Alternative: If you want to use SQLite for testing (comment PostgreSQL config above)
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'  # Indian Standard Time
USE_I18N = True
USE_TZ = True


# ============================================
# STATIC FILES (CSS, JavaScript, Images)
# ============================================
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# ============================================
# MEDIA FILES (User Uploaded Images)
# ============================================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================
# CORS Configuration
# ============================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# For production, use this instead (more secure):
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:3000",
#     "http://localhost:5173",
#     "http://localhost:5174",
# ]


# ============================================
# REST FRAMEWORK Configuration
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',  # For file uploads
        'rest_framework.parsers.FormParser',
    ],
}


# ============================================
# SUPER ADMIN SECRET CODE
# ============================================
# Change this to your desired super admin master key
# This allows super admin access to all companies
SUPER_ADMIN_SECRET = "ADMIN@2024"

# ============================================
# STAFF SHARED CREDENTIALS
# ============================================
# One shared login for ALL staff (waiter + kitchen).
# Staff only type username + password — no client ID on the form.
#
# STAFF_CLIENT_ID   — the client_id of your restaurant (from CompanyInfo).
# STAFF_USERNAME    — the shared username every staff member types.
# STAFF_PASSWORD_HASH — hashed password. To change it run:
#
#   python manage.py setstaffpassword
#
# or generate a hash manually:
#   python manage.py shell -c "from django.contrib.auth.hashers import make_password; print(make_password('yourpassword'))"
#
# Default password is "staff1234" — CHANGE THIS before going live!
STAFF_CLIENT_ID     = "CLI005"   # ← set this to your restaurant's client_id
STAFF_USERNAME      = "userstaff"
STAFF_PASSWORD_HASH = "pbkdf2_sha256$720000$JGbQtfAmpICpkInQ$nstKfjCXI/aOl1w81nadO7yPItSiOB3zgHVYQT0/ENo="
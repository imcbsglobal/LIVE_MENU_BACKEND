"""
Django settings for backend project with PostgreSQL + Cloudflare R2.

Project structure:
    D:\LIVE MENU PROJECT\
    └── backend\                  <- BASE_DIR / where .env lives / where manage.py lives
        ├── .env
        ├── manage.py
        └── backend\
            └── settings.py      <- this file
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR = D:\LIVE MENU PROJECT\backend\
BASE_DIR = Path(__file__).resolve().parent.parent

# .env is at D:\LIVE MENU PROJECT\backend\.env  ->  BASE_DIR / '.env'
load_dotenv(BASE_DIR / '.env', override=True)

# Read R2 flag immediately after dotenv loads
CLOUDFLARE_R2_ENABLED = os.getenv("CLOUDFLARE_R2_ENABLED", "false").strip().lower() == "true"

# Debug lines — shows on every server start so you can confirm .env loaded
print(f"[settings] BASE_DIR    = {BASE_DIR}")
print(f"[settings] .env exists = {(BASE_DIR / '.env').exists()}")
print(f"[settings] R2 enabled  = {CLOUDFLARE_R2_ENABLED}")
print(f"[settings] DB_NAME     = {os.getenv('DB_NAME')}")

# ============================================
# SECURITY
# ============================================
SECRET_KEY = 'django-insecure-g1@x=5suku6)8_2!8w4*a6*_f*t03__r)l1we=-xm80nit-@1d'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.23', '192.168.1.144']

# ============================================
# INSTALLED APPS
# ============================================
INSTALLED_APPS = [
    'daphne',
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
    'storages',
]

ASGI_APPLICATION = 'backend.asgi.application'

# ============================================
# CHANNEL LAYERS
# ============================================
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
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
# DATABASE - PostgreSQL
# ============================================
DATABASES = {
    'default': {
        'ENGINE':       'django.db.backends.postgresql',
        'NAME':         os.getenv('DB_NAME'),
        'USER':         os.getenv('DB_USER'),
        'PASSWORD':     os.getenv('DB_PASSWORD'),
        'HOST':         os.getenv('DB_HOST'),
        'PORT':         os.getenv('DB_PORT'),
        'CONN_MAX_AGE': 60,
    }
}

# ============================================
# PASSWORD VALIDATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================
# INTERNATIONALISATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kolkata'
USE_I18N      = True
USE_TZ        = True

# ============================================
# STATIC FILES
# ============================================
STATIC_URL  = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# ============================================
# REST FRAMEWORK
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
}

# ============================================
# FILE STORAGE - Cloudflare R2 or local media
# ============================================
if CLOUDFLARE_R2_ENABLED:
    # Use STORAGES for Django 4.2+
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    AWS_ACCESS_KEY_ID       = os.getenv('CLOUDFLARE_R2_ACCESS_KEY', '').strip()
    AWS_SECRET_ACCESS_KEY   = os.getenv('CLOUDFLARE_R2_SECRET_KEY', '').strip()
    AWS_STORAGE_BUCKET_NAME = os.getenv('CLOUDFLARE_R2_BUCKET', '').strip()

    _account_id             = os.getenv('CLOUDFLARE_R2_ACCOUNT_ID', '').strip()
    AWS_S3_ENDPOINT_URL     = f'https://{_account_id}.r2.cloudflarestorage.com'
    AWS_S3_REGION_NAME      = 'auto'

    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE  = 'path'

    AWS_S3_FILE_OVERWRITE    = False
    AWS_DEFAULT_ACL          = None
    AWS_QUERYSTRING_AUTH     = False

    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

    _public_url              = os.getenv('CLOUDFLARE_R2_PUBLIC_URL', '').replace('https://', '').rstrip('/')
    AWS_S3_CUSTOM_DOMAIN     = _public_url
    MEDIA_URL                = f'https://{_public_url}/'
    MEDIA_ROOT               = ''

    print(f"[settings] R2 STORAGE ACTIVE  -> bucket: {AWS_STORAGE_BUCKET_NAME} | cdn: {MEDIA_URL}")

else:
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

    print(f"[settings] LOCAL STORAGE -> {MEDIA_ROOT}")

# ============================================
# SUPER ADMIN SECRET CODE
# ============================================
SUPER_ADMIN_SECRET = "ADMIN@2024"

# ============================================
# STAFF SHARED CREDENTIALS
# ============================================
STAFF_CLIENT_ID     = "CLI005"
STAFF_USERNAME      = "userstaff"
STAFF_PASSWORD_HASH = "pbkdf2_sha256$720000$JGbQtfAmpICpkInQ$nstKfjCXI/aOl1w81nadO7yPItSiOB3zgHVYQT0/ENo="
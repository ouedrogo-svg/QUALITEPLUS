"""
Configuration Django — plateforme de SUJET en ligne.
Force redeploy: 2026-05-24-v2
"""
import socket
import mimetypes
from decouple import config
import os

mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("application/pdf", ".pdf", True)

# Security: Allow iframes from same origin for PDF reader
X_FRAME_OPTIONS = "SAMEORIGIN"
import dj_database_url
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = True

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "courses.apps.CoursesConfig",
    "accounts.apps.AccountsConfig",
    "cloudinary_storage",
    "cloudinary",
]

if not DEBUG:
    INSTALLED_APPS.insert(0, "whitenoise.runserver_nostatic")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "courses.middleware.PrefetchUserSubscriptionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.static",
                "django.template.context_processors.media",
                "courses.context_processors.admin_exam_recap",
                "courses.context_processors.formateur_nav",
                "courses.context_processors.formateur_space",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
"""
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        # Évite « database is locked » (admin + import PDF / runserver sur Windows).
        "OPTIONS": {"timeout": 60},
    }
}
"""

DATABASES = {
    "default": dj_database_url.parse(config("DATABASE_URL")),
}

# Connexion persistante (surtout si PostgreSQL distant) : moins de latence par page.
_db = DATABASES["default"]
if "postgresql" in _db.get("ENGINE", ""):
    # 600 secondes (10 minutes) pour minimiser l'impact de la latence réseau (handshake TCP/SSL).
    _db.setdefault("CONN_MAX_AGE", 600)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cour-ligne",
    }
}




AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Cloudinary — stockage persistant des fichiers média (PDF, images)
# Les fichiers survivent aux redéploiements / suspensions de Render.
# Variables d'environnement requises : CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY,
# CLOUDINARY_API_SECRET  (à définir dans le dashboard Render → Environment).
# ---------------------------------------------------------------------------
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": config("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY": config("CLOUDINARY_API_KEY", default=""),
    "API_SECRET": config("CLOUDINARY_API_SECRET", default=""),
    # Stocker les PDF tels quels (pas de transformation image)
    "RESOURCE_TYPE": "raw",
}

_use_cloudinary = bool(CLOUDINARY_STORAGE["CLOUD_NAME"])

STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.RawMediaCloudinaryStorage"
            if _use_cloudinary
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# En local (pas de Cloudinary), s'assurer que le dossier media existe.
if not _use_cloudinary and not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.NomBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_REDIRECT_URL = "courses:home"
LOGOUT_REDIRECT_URL = "courses:home"
LOGIN_URL = "accounts:login"

# En développement, les e-mails s’affichent dans la console du serveur.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@sujetligne.local"
SERVER_EMAIL = DEFAULT_FROM_EMAIL

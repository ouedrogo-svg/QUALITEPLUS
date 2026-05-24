"""
Configuration Django — plateforme de SUJET en ligne.
"""
import socket
from decouple import config
import os
import dj_database_url
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
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

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

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

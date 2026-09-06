"""Configuration (SPEC Section 6). Resolution: environment variables only.

Core fields (Section 6.5): LICENSE_LISTEN_HOST / LICENSE_LISTEN_PORT (defaults
127.0.0.1:8000, used by `manage.py runserver $LISTEN_HOST:$LISTEN_PORT`),
LICENSE_STORE_* (the `store` bundle), LICENSE_SESSION_SECRET (required when
LICENSE_DEBUG=0), LICENSE_DEBUG. Changing any store field requires a restart.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("LICENSE_DEBUG", "0") == "1"
DEV_SECRET_KEY = "django-insecure-development-default"
SECRET_KEY = os.environ.get("LICENSE_SESSION_SECRET", DEV_SECRET_KEY)
LISTEN_HOST = os.environ.get("LICENSE_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LICENSE_LISTEN_PORT", "8000"))
ALLOWED_HOSTS = os.environ.get("LICENSE_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
if not DEBUG and SECRET_KEY == DEV_SECRET_KEY:
    raise ImproperlyConfigured("config_invalid: licenses.E001: LICENSE_SESSION_SECRET is required.")
if DEBUG and LISTEN_HOST not in {"localhost", "127.0.0.1", "::1"}:
    raise ImproperlyConfigured("config_invalid: debug mode requires a loopback listener.")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
# Opt in only behind an edge that strips and replaces X-Forwarded-Proto.
if os.environ.get("LICENSE_TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 16384
LICENSE_REGISTRATION_SOURCE_LIMIT = int(os.environ.get("LICENSE_REGISTRATION_SOURCE_LIMIT", "5"))
LICENSE_REGISTRATION_GLOBAL_LIMIT = int(os.environ.get("LICENSE_REGISTRATION_GLOBAL_LIMIT", "100"))
LICENSE_ACCOUNT_LIMIT = int(os.environ.get("LICENSE_ACCOUNT_LIMIT", "10000"))
LICENSE_DEVICE_HISTORY_LIMIT = int(os.environ.get("LICENSE_DEVICE_HISTORY_LIMIT", "100"))
if (
    min(
        LICENSE_REGISTRATION_SOURCE_LIMIT,
        LICENSE_REGISTRATION_GLOBAL_LIMIT,
        LICENSE_DEVICE_HISTORY_LIMIT,
        LICENSE_ACCOUNT_LIMIT,
    )
    < 1
):
    raise ImproperlyConfigured("config_invalid: abuse limits must be positive.")

# `store` bundle (Section 6.2): which durable engine and how to open it.
# Supported engines: "sqlite3" (default; LICENSE_STORE_NAME = file path) and
# "postgresql" (LICENSE_STORE_NAME/USER/PASSWORD/HOST/PORT).
_engine = os.environ.get("LICENSE_STORE_ENGINE", "sqlite3")
if _engine == "sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("LICENSE_STORE_NAME", str(BASE_DIR / "license_store.sqlite3")),
            "TEST": {"NAME": BASE_DIR / "test_license_store.sqlite3"},
        }
    }
elif _engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("LICENSE_STORE_NAME", "licenses"),
            "USER": os.environ.get("LICENSE_STORE_USER", ""),
            "PASSWORD": os.environ.get("LICENSE_STORE_PASSWORD", ""),
            "HOST": os.environ.get("LICENSE_STORE_HOST", "127.0.0.1"),
            "PORT": os.environ.get("LICENSE_STORE_PORT", "5432"),
        }
    }
else:
    raise ImproperlyConfigured(f"config_invalid: unknown LICENSE_STORE_ENGINE {_engine!r}")

INSTALLED_APPS = [
    "unfold",  # before django.contrib.admin so its templates win
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "admin_extra_buttons",
    "django_tailwind_cli",
    "licenses",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "licenses.audit.AuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("zh-hans", "简体中文")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "assets"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Tailwind via django-tailwind-cli (standalone CLI, no Node). Source CSS lives
# outside STATICFILES_DIRS so collectstatic never picks up `@import "tailwindcss"`.
TAILWIND_CLI_VERSION = "4.3.3"
TAILWIND_CLI_SRC_CSS = "src/styles.css"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# The first backend enforces durable account/source login throttles. Keep the
# stock backend configured so sessions created before this backend was added
# remain valid; PermissionDenied prevents failed logins from falling through.
AUTHENTICATION_BACKENDS = ["licenses.auth.ThrottledModelBackend", "django.contrib.auth.backends.ModelBackend"]
# Admin theme matches the customer pages: Geist, grayscale surface, one blue accent.
UNFOLD = {
    "SITE_TITLE": "License Service",
    "SITE_HEADER": "License Service",
    "SITE_URL": "/admin/",
    "SITE_SYMBOL": "key",
    "THEME": "light",
    "BORDER_RADIUS": "6px",
    "STYLES": [lambda request: static("css/admin-theme.css")],
    "COLORS": {
        "base": {
            "50": "#fafafa",
            "100": "#f5f5f5",
            "200": "#eaeaea",
            "300": "#c9c9c9",
            "400": "#8f8f8f",
            "500": "#666666",
            "600": "#4d4d4d",
            "700": "#333333",
            "800": "#262626",
            "900": "#171717",
            "950": "#0a0a0a",
        },
        "primary": {
            "50": "#f0f6ff",
            "100": "#e0edff",
            "200": "#c2daff",
            "300": "#8cbcff",
            "400": "#4a93ff",
            "500": "#1a7aff",
            "600": "#006bff",
            "700": "#005ff2",
            "800": "#004dcc",
            "900": "#003d99",
            "950": "#002866",
        },
        "font": {
            "subtle-light": "var(--color-base-400)",
            "subtle-dark": "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark": "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark": "var(--color-base-100)",
        },
    },
}
# Password hash: PBKDF2-SHA256 (Django default). Sessions: server-side, stored
# in the License Store DB (durable across restarts), cookie name "sessionid".
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"licenses": {"handlers": ["console"], "level": "INFO"}},
}

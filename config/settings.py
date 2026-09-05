"""Configuration (SPEC Section 6). Resolution: environment variables only.

Core fields (Section 6.5): LICENSE_LISTEN_HOST / LICENSE_LISTEN_PORT (defaults
127.0.0.1:8000, used by `manage.py runserver $LISTEN_HOST:$LISTEN_PORT`),
LICENSE_STORE_* (the `store` bundle), LICENSE_SESSION_SECRET (required when
LICENSE_DEBUG=0), LICENSE_DEBUG. Changing any store field requires a restart.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("LICENSE_DEBUG", "1") == "1"
DEV_SECRET_KEY = "django-insecure-development-default"
SECRET_KEY = os.environ.get("LICENSE_SESSION_SECRET", DEV_SECRET_KEY)
LISTEN_HOST = os.environ.get("LICENSE_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LICENSE_LISTEN_PORT", "8000"))
ALLOWED_HOSTS = os.environ.get("LICENSE_ALLOWED_HOSTS", "*").split(",")

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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tailwind_cli",
    "licenses",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
LANGUAGE_CODE = "en-us"
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
# Password hash: PBKDF2-SHA256 (Django default). Sessions: server-side, stored
# in the License Store DB (durable across restarts), cookie name "sessionid".
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"licenses": {"handlers": ["console"], "level": "INFO"}},
}

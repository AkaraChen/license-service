"""Production defaults; local development opts in with LICENSE_DEBUG=1."""

import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static


class ExtraFormatter(logging.Formatter):
    _standard = set(logging.LogRecord("n", 0, "", 0, "", (), None).__dict__) | {
        "message",
        "asctime",
        "taskName",
    }

    def format(self, record):
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._standard and not key.startswith("_")
        }
        formatted = super().format(record)
        if extras:
            return f"{formatted} {json.dumps(extras, default=str, ensure_ascii=True)}"
        return formatted


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEBUG = os.environ.get("LICENSE_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("LICENSE_SESSION_SECRET", "")
ALLOWED_HOSTS = os.environ.get("LICENSE_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
if DEBUG:
    SECRET_KEY = SECRET_KEY or "django-insecure-development-default"
elif not SECRET_KEY or SECRET_KEY == "django-insecure-development-default":
    raise ImproperlyConfigured("config_invalid: licenses.E001: LICENSE_SESSION_SECRET is required.")

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
# Opt in only behind an edge that strips and replaces X-Forwarded-Proto.
if os.environ.get("LICENSE_TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DATA_UPLOAD_MAX_MEMORY_SIZE = 16384
DATABASES = {
    "default": dj_database_url.config(
        env="LICENSE_DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'license_store.sqlite3'}"
    )
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"]["timeout"] = 20
    DATABASES["default"]["OPTIONS"]["transaction_mode"] = "IMMEDIATE"

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
    "axes",
    "django_ratelimit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "licenses.middleware.RequestIdMiddleware",
    "licenses.middleware.JsonWritePolicyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
    "axes.middleware.AxesMiddleware",
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
# Packages own all rate counters, lockouts and expiry.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("LICENSE_REDIS_URL", "redis://127.0.0.1:6379/0"),
        "KEY_PREFIX": "license-service",
        "OPTIONS": {"SOCKET_CONNECT_TIMEOUT": 2, "SOCKET_TIMEOUT": 2},
    }
}
AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]
AXES_HANDLER = "axes.handlers.cache.AxesCacheHandler"
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_LOCKOUT_CALLABLE = "licenses.accounts.lockout_response"
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
RATELIMIT_VIEW = "licenses.accounts.ratelimited"
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
    "filters": {"request_id": {"()": "licenses.middleware.RequestIdFilter"}},
    "formatters": {
        "console": {
            "()": "config.settings.ExtraFormatter",
            "format": "{levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console", "filters": ["request_id"]}
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "licenses": {"handlers": ["console"], "level": "INFO", "filters": ["request_id"]},
        "axes": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

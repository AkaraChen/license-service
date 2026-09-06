"""Explicit local profile for pytest; production defaults remain fail-closed."""

import os
import uuid

os.environ.setdefault("LICENSE_DEBUG", "1")
os.environ.setdefault("LICENSE_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

from .settings import *  # noqa: F403

CACHES["default"]["KEY_PREFIX"] = "license-test-" + uuid.uuid4().hex  # noqa: F405
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":  # noqa: F405
    DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / "test_license_store.sqlite3"}  # noqa: F405

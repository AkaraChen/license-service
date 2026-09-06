"""Explicit local profile for pytest; production defaults remain fail-closed."""

import os
import uuid

os.environ.setdefault("LICENSE_DEBUG", "1")
os.environ.setdefault("LICENSE_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

os.environ.setdefault("LICENSE_CACHE_PREFIX", "license-test-" + uuid.uuid4().hex)

from .settings import *  # noqa: F403

"""Explicit local profile for pytest; production defaults remain fail-closed."""

import os

os.environ.setdefault("LICENSE_DEBUG", "1")
os.environ.setdefault("LICENSE_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

from .settings import *  # noqa: F403

"""Single-host Kamal profile; only readiness bypasses domain validation."""

from .settings import *  # noqa: F403

# kamal-proxy probes the container ID rather than the public domain.
# The readiness response is fixed, contains no user data and never uses Host.
MIDDLEWARE = ["licenses.views.health.HealthcheckMiddleware", *MIDDLEWARE]  # noqa: F405

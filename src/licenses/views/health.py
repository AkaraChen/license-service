"""Low-cost readiness check without exposing dependency details."""

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@require_safe
@never_cache
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        # Check writes as well as reads: Redis PING still succeeds at maxmemory.
        # Concurrent probes share an identical value; the key expires automatically.
        cache.set("healthcheck", "ok", timeout=60)
        if cache.get("healthcheck") != "ok":
            raise RuntimeError("Cache probe failed")
    except Exception:  # noqa: BLE001 - dependency failures must produce a generic 503
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


class HealthcheckMiddleware:
    """Allow internal Kamal probes before Host-dependent middleware runs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == "/healthz":
            return health(request)
        return self.get_response(request)

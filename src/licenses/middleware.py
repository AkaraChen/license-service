import contextvars
import logging

from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure

_request_id = contextvars.ContextVar("request_id", default=None)


class RequestIdMiddleware:
    """Copy X-Request-ID onto log records when the client sent one. Never generate."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_id.set(request.headers.get("X-Request-ID"))
        try:
            return self.get_response(request)
        finally:
            _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        request_id = _request_id.get()
        if request_id:
            record.request_id = request_id
        return True


def csrf_failure(request, reason=""):
    from .services.errors import Forbidden

    if not request.path.startswith("/api/"):
        return django_csrf_failure(request, reason=reason)
    return JsonResponse(Forbidden("CSRF verification failed.").envelope(), status=403)

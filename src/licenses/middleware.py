import contextvars
import logging

from django.http import JsonResponse

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


class SameOriginCookieWriteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view, args, kwargs):
        from .services.errors import Forbidden

        origin = request.headers.get("Origin")
        if (
            request.path.startswith("/api/")
            and request.method in {"POST", "PATCH"}
            and request.path not in {"/api/activate", "/api/validate"}
            and origin is not None
            and origin != f"{request.scheme}://{request.get_host()}"
        ):
            forbidden = Forbidden("Cross-origin writes are not allowed.")
            return JsonResponse(forbidden.envelope(), status=forbidden.status)
        return None

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


class JsonWritePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and response.status_code == 405:
            return JsonResponse(
                {"error": "validation_error", "message": "Method not allowed."},
                status=405,
                headers={"Allow": response.get("Allow", "")},
            )
        return response

    def process_view(self, request, view, args, kwargs):
        if not request.path.startswith("/api/") or request.method not in {"POST", "PATCH"}:
            return None
        from .services.errors import Forbidden, ValidationError
        from .views.api import handle_error

        origin = request.headers.get("Origin")
        if request.path not in {"/api/activate", "/api/validate"} and origin is not None:
            if origin != f"{request.scheme}://{request.get_host()}":
                return handle_error(request, Forbidden("Cross-origin writes are not allowed."))
        if request.content_type != "application/json":
            return handle_error(request, ValidationError("Write bodies must be application/json."))
        return None

"""Shared HTTP policy for the JSON API; routing and business logic stay in views."""

from functools import wraps
from typing import Literal

from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import audit
from .services import Failure

HTTP_STATUS = {
    "validation_error": 400,
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "unknown_key": 404,
    "unknown_device": 404,
    "conflict": 409,
    "already_entitled": 409,
    "key_already_redeemed": 409,
    "key_revoked": 409,
    "seat_exhausted": 409,
    "entitlement_suspended": 409,
    "entitlement_revoked": 409,
    "entitlement_expired": 409,
    "store_unavailable": 503,
    "rate_limited": 429,
}


def api_view(methods: tuple[str, ...], *, access: Literal["anonymous", "application", "session", "admin"]):
    """Apply JSON method/auth/error/audit policy without registering or dispatching views."""

    if access not in {"anonymous", "application", "session", "admin"}:
        raise ValueError(f"Unknown API access policy: {access}")

    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse(
                    {"error": "validation_error", "message": "Method not allowed."}, status=405
                )
            operation = wrapped.openapi[request.method]["operationId"]
            context = {
                "actor": "application" if access == "application" else "anonymous",
                "rid": audit.request_id(request),
            }
            request.audit_context = context
            try:
                if request.method in {"POST", "PATCH"} and access != "application":
                    origin = request.headers.get("Origin")
                    if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
                        raise Failure("forbidden", "Cross-origin writes are not allowed.")
                if access in {"session", "admin"}:
                    user = request.user
                    if not user.is_authenticated:
                        raise Failure("unauthenticated", "A session cookie is required.")
                    if access == "admin" and not user.is_staff:
                        raise Failure("forbidden", "Admin privileges required.")
                    context.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
                if request.method in {"POST", "PATCH"} and request.content_type != "application/json":
                    raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
                response = view(request, *args, **kwargs)
                context["outcome"] = "success"
            except (
                Failure,
                Http404,
                OperationalError,
                IntegrityError,
                DataError,
                RequestDataTooBig,
                UnicodeError,
            ) as exc:
                if isinstance(exc, Failure):
                    error, message = exc.error, exc.message
                elif isinstance(exc, Http404):
                    error, message = "not_found", "Not found."
                elif isinstance(exc, OperationalError):
                    error, message = "store_unavailable", "The license store is unavailable."
                elif isinstance(exc, IntegrityError):
                    error, message = "conflict", "The requested change conflicts with existing data."
                else:
                    error, message = "validation_error", "The request body is invalid or too large."
                context["outcome"] = error
                response = JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])
            audit.emit(operation, context)
            return response

        wrapped.allowed_methods = tuple(methods)
        wrapped.access = access
        return wrapped

    return decorate

"""License-specific HTTP policy around Ninja's request lifecycle."""

import structlog
from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError
from django.http import Http404, JsonResponse
from django_ratelimit.exceptions import Ratelimited
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError
from ninja.security import SessionAuth
from redis.exceptions import RedisError

from ..services import Failure

log = structlog.get_logger(__name__)

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
    "rate_limited": 429,
    "store_unavailable": 503,
}


class LicenseAPI(NinjaAPI):
    # Public Ninja hook: keep the SPEC operation names without repeating 25 IDs.
    def get_openapi_operation_id(self, operation):
        return operation.view_func.__name__


api = LicenseAPI(title="License Service", version="3.0.0", openapi_url="/openapi.json", docs_url="/docs")


class AdminSession(SessionAuth):
    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is not None and not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        return user


customer_session = SessionAuth(csrf=False)
admin_session = AdminSession(csrf=False)


def api_error(request, exc):
    if isinstance(exc, Failure):
        error, message = exc.error, exc.message
    elif isinstance(exc, AuthenticationError):
        error, message = "unauthenticated", "A session cookie is required."
    elif isinstance(exc, Http404):
        error, message = "not_found", "Not found."
    elif isinstance(exc, (OperationalError, RedisError)):
        error, message = "store_unavailable", "The license store is unavailable."
    elif isinstance(exc, IntegrityError):
        error, message = "conflict", "The requested change conflicts with existing data."
    elif isinstance(exc, Ratelimited):
        error, message = "rate_limited", "Registration limit reached. Please try again later."
    else:
        error, message = "validation_error", "The request body is invalid or too large."
    log.warning("api_error", outcome=error)
    return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


for exception in (
    Failure,
    Http404,
    OperationalError,
    RedisError,
    IntegrityError,
    Ratelimited,
    DataError,
    RequestDataTooBig,
    UnicodeError,
    ValidationError,
    HttpError,
):
    api.add_exception_handler(exception, api_error)

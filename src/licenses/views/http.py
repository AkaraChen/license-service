"""License-specific HTTP policy around Ninja's request lifecycle."""

from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError
from django.http import Http404, JsonResponse
from django_ratelimit.exceptions import Ratelimited
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError
from ninja.security import SessionAuth
from redis.exceptions import RedisError

from .. import audit
from ..services import HTTP_STATUS, Failure


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


def envelope(request, error, message):
    audit.resources(request, outcome=error)
    return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


def api_error(request, exc):
    """Same envelope as exception handlers; used by same-origin middleware."""
    return envelope(request, exc.error, exc.message)


@api.exception_handler(HttpError)
def http_error(request, exc):
    if isinstance(exc, Failure):
        return envelope(request, exc.error, exc.message)
    return envelope(request, "validation_error", "The request body is invalid or too large.")


@api.exception_handler(AuthenticationError)
def unauthenticated(request, exc):
    return envelope(request, "unauthenticated", "A session cookie is required.")


@api.exception_handler(Http404)
def not_found(request, exc):
    return envelope(request, "not_found", "Not found.")


@api.exception_handler(IntegrityError)
def conflict(request, exc):
    return envelope(request, "conflict", "The requested change conflicts with existing data.")


@api.exception_handler(OperationalError)
@api.exception_handler(RedisError)
def store_unavailable(request, exc):
    return envelope(request, "store_unavailable", "The license store is unavailable.")


@api.exception_handler(Ratelimited)
def rate_limited(request, exc):
    return envelope(request, "rate_limited", "Registration limit reached. Please try again later.")


@api.exception_handler(ValidationError)
@api.exception_handler(DataError)
@api.exception_handler(RequestDataTooBig)
@api.exception_handler(UnicodeError)
def invalid_request(request, exc):
    return envelope(request, "validation_error", "The request body is invalid or too large.")

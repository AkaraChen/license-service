"""Account registration and case-insensitive login; packages own rate limiting."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.shortcuts import render
from django.utils.translation import gettext
from django_ratelimit.decorators import ratelimit

from . import audit
from .services import Failure, validate_text

MAX_ACCOUNTS = 10_000
USERNAME_MAX_LENGTH = 150


def register_account(username, password, request=None):
    """Open self-registration. Invariant 4: always is_admin=False."""
    username = (username or "").strip()
    if not username or len(username) > USERNAME_MAX_LENGTH:
        raise Failure("validation_error", gettext("username must be 1-150 characters."))
    if not password:
        raise Failure("validation_error", gettext("password must not be empty."))
    if len(password) > 1024:
        raise Failure("validation_error", "password exceeds 1024 characters.")
    validate_text(username)
    validate_text(password)
    if request is not None:
        admit_registration(request)

    def work():
        if User.objects.count() >= MAX_ACCOUNTS:
            raise Failure("rate_limited", "Account capacity reached. Contact the operator.")
        if User.objects.alias(canonical=Lower("username")).filter(canonical=Lower(Value(username))).exists():
            raise Failure("conflict", gettext("This username is already taken."))
        return User.objects.create_user(username=username, password=password)

    try:
        with cache.lock("registration", timeout=30, blocking_timeout=2):
            with transaction.atomic():
                return work()
    except IntegrityError:
        raise Failure("conflict", gettext("This username is already taken.")) from None


def drop_account_sessions(account):
    """Delete this account's server-side sessions. Call after is_active changes."""
    account_id = str(account.pk)
    for session in Session.objects.iterator():
        if session.get_decoded().get("_auth_user_id") == account_id:
            session.delete()


def set_account_active(account, active):
    """Set is_active and drop sessions when the flag actually changes."""
    if account.is_active == active:
        return account
    account.is_active = active
    account.save(update_fields=("is_active",))
    drop_account_sessions(account)
    return account


def canonical_username(username):
    username = (username or "").strip()
    account = (
        get_user_model()
        .objects.alias(canonical=Lower("username"))
        .filter(canonical=Lower(Value(username)))
        .first()
    )
    return account.username if account is not None else username


class CaseInsensitiveBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        return super().authenticate(
            request, username=canonical_username(username), password=password, **kwargs
        )


def axes_username(request, credentials):
    return canonical_username((credentials or {}).get("username"))


def lockout_response(request, response, credentials=None):
    # Keep the adapters' generic invalid-credentials response, including Admin.
    return response


@ratelimit(group="registration.global", key=lambda g, r: "all", rate="100/h")
@ratelimit(group="registration.source", key="ip", rate="5/h")
def admit_registration(request):
    pass


def ratelimited(request, exception):
    audit.resources(request, outcome="rate_limited")
    return render(
        request,
        "licenses/error.html",
        {"error": "Registration limit reached. Please try again later."},
        status=429,
    )

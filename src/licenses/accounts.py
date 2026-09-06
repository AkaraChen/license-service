"""Account registration and rate limiting."""

import structlog
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.shortcuts import render
from django.utils.translation import gettext
from django_ratelimit.decorators import ratelimit

from .services import Failure

log = structlog.get_logger(__name__)

MAX_ACCOUNTS = 10_000


def register_account(username, password, request=None):
    """Open self-registration. Invariant 4: always is_admin=False."""
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


def lockout_response(request, response, credentials=None):
    log.warning("lockout")
    return response


@ratelimit(group="registration.global", key=lambda g, r: "all", rate="100/h")
@ratelimit(group="registration.source", key="ip", rate="5/h")
def admit_registration(request):
    pass


def ratelimited(request, exception):
    log.warning("register", outcome="rate_limited")
    return render(
        request,
        "licenses/error.html",
        {"error": "Registration limit reached. Please try again later."},
        status=429,
    )

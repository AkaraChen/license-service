"""Account registration and rate limiting."""

import logging

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import render
from django.utils.translation import gettext
from django_ratelimit.decorators import ratelimit
from user_sessions.models import Session

from .services.errors import Conflict, RateLimited

log = logging.getLogger(__name__)

MAX_ACCOUNTS = 10_000


def register_account(username, password, request=None):
    """Open self-registration. Invariant 4: always is_admin=False."""
    if request is not None:
        admit_registration(request)
    if User.objects.count() >= MAX_ACCOUNTS:
        raise RateLimited("Account capacity reached. Contact the operator.")
    try:
        with transaction.atomic():
            return User.objects.create_user(username=username, password=password)
    except IntegrityError:
        raise Conflict(gettext("This username is already taken.")) from None


def drop_account_sessions(account):
    """Delete this account's server-side sessions. Call after is_active changes."""
    Session.objects.filter(user_id=account.pk).delete()


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
    log.warning("register", extra={"outcome": "rate_limited"})
    return render(
        request,
        "licenses/error.html",
        {"error": "Registration limit reached. Please try again later."},
        status=429,
    )

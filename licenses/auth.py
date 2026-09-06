"""Django authentication backend with durable login abuse controls."""

import hmac
import ipaddress
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.db import OperationalError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.encoding import force_bytes

from .models import LoginThrottle

LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT_DURATION = timedelta(minutes=15)
LOGIN_THROTTLE_RETENTION = LOGIN_FAILURE_WINDOW + LOGIN_LOCKOUT_DURATION


def _digest(scope, identity):
    return hmac.digest(
        force_bytes(settings.SECRET_KEY), force_bytes(f"login-throttle:{scope}:{identity}"), "sha256"
    ).hex()


def _source_identity(request):
    """Use only the direct peer address; forwarded headers are attacker-controlled."""
    raw = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.compressed


def _normalize_state(state, now):
    if state.locked_until is not None:
        if state.locked_until > now:
            return True
        state.failure_count = 0
        state.window_started_at = now
        state.locked_until = None
        state.save(update_fields=("failure_count", "window_started_at", "locked_until", "updated_at"))
    elif state.window_started_at + LOGIN_FAILURE_WINDOW <= now:
        state.failure_count = 0
        state.window_started_at = now
        state.save(update_fields=("failure_count", "window_started_at", "updated_at"))
    return False


def _reserve_failure(state, now):
    state.failure_count += 1
    if state.failure_count >= LOGIN_FAILURE_LIMIT:
        state.locked_until = now + LOGIN_LOCKOUT_DURATION
    state.save(update_fields=("failure_count", "locked_until", "updated_at"))


def _reset_account_state(state, now):
    state.failure_count = 0
    state.window_started_at = now
    state.locked_until = None
    state.save(update_fields=("failure_count", "window_started_at", "locked_until", "updated_at"))


def _prune_stale(now):
    LoginThrottle.objects.filter(updated_at__lt=now - LOGIN_THROTTLE_RETENTION).delete()


def _retry_locked(work):
    """SQLite cannot row-lock, so retry a contended counter transaction."""
    for attempt in range(10):
        try:
            return work()
        except LoginThrottle.DoesNotExist:
            # A concurrent stale-state prune can remove a row before it is locked.
            if attempt == 9:
                raise
            continue
        except OperationalError as exc:
            if "locked" not in str(exc) or attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


class ThrottledModelBackend(ModelBackend):
    """Protect every Django password-login adapter, including Django Admin."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        supplied_username = username if username is not None else kwargs.get(UserModel.USERNAME_FIELD)
        normalized_username = (supplied_username or "").strip()
        account = (
            UserModel._default_manager.alias(canonical=Lower("username"))
            .filter(canonical=Lower(Value(normalized_username)))
            .first()
        )
        canonical_username = account.get_username() if account is not None else normalized_username

        keys = [("source", _digest("source", _source_identity(request)))]
        if account is not None and account.is_active:
            keys.append(("account", _digest("account", str(account.pk))))
        keys.sort()

        def authenticate_once():
            now = timezone.now()
            _prune_stale(now)
            for scope, key_digest in keys:
                LoginThrottle.objects.get_or_create(scope=scope, key_digest=key_digest)

            authenticated = None
            blocked_scopes = set()
            with transaction.atomic():
                states = [
                    LoginThrottle.objects.select_for_update().get(scope=scope, key_digest=key_digest)
                    for scope, key_digest in keys
                ]
                now = timezone.now()
                for state in states:
                    if _normalize_state(state, now):
                        blocked_scopes.add(state.scope)
                if not blocked_scopes:
                    source_snapshot = None
                    for state in states:
                        if state.scope == "source":
                            source_snapshot = (
                                state.failure_count,
                                state.window_started_at,
                                state.locked_until,
                            )
                        _reserve_failure(state, now)

                    authenticated = super(ThrottledModelBackend, self).authenticate(
                        request, username=canonical_username, password=password, **kwargs
                    )
                    if authenticated is not None:
                        for state in states:
                            if state.scope == "account":
                                _reset_account_state(state, now)
                            else:
                                state.failure_count, state.window_started_at, state.locked_until = (
                                    source_snapshot
                                )
                                state.save(
                                    update_fields=(
                                        "failure_count",
                                        "window_started_at",
                                        "locked_until",
                                        "updated_at",
                                    )
                                )
            return authenticated, blocked_scopes

        authenticated, blocked_scopes = _retry_locked(authenticate_once)
        if "account" in blocked_scopes and "source" not in blocked_scopes:
            # Match Django's nonexistent-user work without checking the locked account's hash.
            UserModel().set_password(password)
        if blocked_scopes or authenticated is None:
            # Stop Django from falling through to the compatibility backend.
            raise PermissionDenied
        return authenticated

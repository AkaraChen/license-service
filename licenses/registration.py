"""Bound anonymous password hashing and account growth across workers."""

from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .auth import _digest, _source_identity
from .models import RegistrationThrottle
from .services import Failure, _atomic

WINDOW = timedelta(hours=1)


def admit_registration(request):
    def work():
        now = timezone.now()
        # Lock the shared bucket first: source churn cannot allocate unlimited rows,
        # and admitted hashes have a process-independent hourly budget.
        global_key = _digest("registration", "global")
        RegistrationThrottle.objects.get_or_create(key_digest=global_key)
        global_state = RegistrationThrottle.objects.select_for_update().get(key_digest=global_key)
        if global_state.window_started_at + WINDOW <= now:
            global_state.count = 0
            global_state.window_started_at = now
        if global_state.count >= settings.LICENSE_REGISTRATION_GLOBAL_LIMIT:
            return False
        RegistrationThrottle.objects.filter(window_started_at__lt=now - WINDOW).exclude(
            pk=global_state.pk
        ).delete()
        source_key = _digest("registration-source", _source_identity(request))
        source, _ = RegistrationThrottle.objects.get_or_create(key_digest=source_key)
        source = RegistrationThrottle.objects.select_for_update().get(pk=source.pk)
        if source.window_started_at + WINDOW <= now:
            source.count = 0
            source.window_started_at = now
        # Count attempts, including rejected source attempts, to bound source churn.
        global_state.count += 1
        global_state.save(update_fields=("count", "window_started_at"))
        if source.count >= settings.LICENSE_REGISTRATION_SOURCE_LIMIT:
            return False
        source.count += 1
        source.save(update_fields=("count", "window_started_at"))
        return True

    if not _atomic(work):
        raise Failure("rate_limited", "Registration limit reached. Please try again later.")


def lock_registration():
    # Called inside the account-creation transaction. The no-op UPDATE locks
    # the shared row on PostgreSQL and reserves the writer on SQLite, bounding
    # concurrent registration hashes to one across processes.
    RegistrationThrottle.objects.filter(key_digest=_digest("registration", "global")).update(count=F("count"))

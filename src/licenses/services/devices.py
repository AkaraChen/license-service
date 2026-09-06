from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from ..models import Entitlement, LicenseKey
from .errors import (
    EntitlementExpired,
    EntitlementRevoked,
    EntitlementSuspended,
    KeyRevoked,
    SeatExhausted,
    UnknownDevice,
    UnknownKey,
)
from .keys import hash_key

DEVICE_HISTORY_LIMIT = 100


def check_active(entitlement):
    """Section 7.5 step 2 / 7.7: status and expiry gate for bind and validate."""
    if entitlement.status == "suspended":
        raise EntitlementSuspended(gettext("This entitlement is suspended."))
    if entitlement.status == "revoked":
        raise EntitlementRevoked(gettext("This entitlement has been revoked."))
    if entitlement.expires_at is not None and timezone.now() > entitlement.expires_at:
        raise EntitlementExpired(gettext("This entitlement has expired."))


def bind(entitlement, fingerprint, display_name=None, *, source_key_id=None):
    """Section 7.5. Returns (device, created); same fingerprint is idempotent."""

    def work():
        if source_key_id is not None:
            key = LicenseKey.objects.select_for_update().get(pk=source_key_id)
            if key.status == "revoked":
                raise KeyRevoked(gettext("This license key has been revoked."))
            if key.status != "redeemed":
                raise UnknownKey(gettext("This license key is not recognized."))
        locked = Entitlement.objects.select_for_update().get(pk=entitlement.pk)
        if source_key_id is not None and locked.source_key_id != source_key_id:
            raise UnknownKey(gettext("This license key is not recognized."))
        check_active(locked)
        existing = locked.devices.filter(device_fingerprint=fingerprint, status="bound").first()
        if existing is not None:
            return existing, False
        if locked.devices.filter(status="bound").count() >= locked.max_devices:
            raise SeatExhausted(gettext("This entitlement has no remaining device seats."))
        from licenses import services as license_services

        budget = max(license_services.DEVICE_HISTORY_LIMIT, locked.max_devices)
        excess = locked.devices.count() - budget + 1
        if excess > 0:
            stale_ids = list(
                locked.devices.filter(status="unbound").order_by("pk").values_list("pk", flat=True)[:excess]
            )
            locked.devices.filter(pk__in=stale_ids).delete()
        return locked.devices.create(device_fingerprint=fingerprint, display_name=display_name), True

    with transaction.atomic():
        return work()


def unbind(device):
    """Section 7.6. Idempotent; frees one seat."""
    if device.status != "unbound":
        device.status = "unbound"
        device.save(update_fields=("status",))
    return device


def resolve_redeemed_key(plaintext):
    """Licensed Application key resolution (7.5 step 1 / 7.7). An `issued` key
    reports unknown_key so key existence is not leaked before redeem."""
    key = LicenseKey.objects.filter(key_hash=hash_key(plaintext)).first()
    if key is None or key.status == "issued":
        raise UnknownKey(gettext("This license key is not recognized."))
    if key.status == "revoked":
        raise KeyRevoked(gettext("This license key has been revoked."))
    entitlement = getattr(key, "entitlement", None)
    if entitlement is None:
        raise UnknownKey(gettext("This license key is not recognized."))
    return key, entitlement


def validate(plaintext, fingerprint):
    """Section 7.7. Read-only: MUST NOT create rows."""
    _, entitlement = resolve_redeemed_key(plaintext)
    check_active(entitlement)
    device = entitlement.devices.filter(device_fingerprint=fingerprint, status="bound").first()
    if device is None:
        raise UnknownDevice(gettext("No bound device matches this fingerprint."))
    return device


def rename_device(device, display_name):
    device.display_name = display_name
    device.save(update_fields=("display_name",))
    return device

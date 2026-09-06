"""Policy layer (SPEC 7, 16). The License Store (ORM) is the single mutation
authority; every mutation runs atomically in the deciding request."""

import hashlib
import secrets
import time

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext

from .models import Entitlement, LicenseKey

FINGERPRINT_MAX_LENGTH = 128
USERNAME_MAX_LENGTH = 150
_KEY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # 32 chars from 29 symbols: ~155 bits (4.1.3)


class Failure(Exception):
    """One SPEC Section 14.1 error class plus a human-readable message."""

    def __init__(self, error, message):
        super().__init__(message)
        self.error = error
        self.message = message


def hash_key(plaintext):
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


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
    from .registration import admit_registration, lock_registration

    admit_registration(request)

    def work():
        lock_registration()
        if User.objects.count() >= settings.LICENSE_ACCOUNT_LIMIT:
            raise Failure("rate_limited", "Account capacity reached. Contact the operator.")
        if User.objects.alias(canonical=Lower("username")).filter(canonical=Lower(Value(username))).exists():
            raise Failure("conflict", gettext("This username is already taken."))
        return User.objects.create_user(username=username, password=password)

    try:
        return _atomic(work)
    except IntegrityError:
        raise Failure("conflict", gettext("This username is already taken.")) from None


def authenticate_account(request, username, password):
    user = authenticate(request, username=(username or "").strip(), password=password or "")
    if user is None or not user.is_active:
        raise Failure("unauthenticated", gettext("Invalid username or password."))
    return user


def issue_key(product, max_devices, expires_at=None):
    """Returns (key, plaintext). The plaintext is returned once and never stored."""
    if type(max_devices) is not int or max_devices < 1:
        raise Failure("validation_error", gettext("max_devices must be an integer >= 1."))
    plaintext = "lic_" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(32))
    key = LicenseKey.objects.create(
        product=product,
        key_hash=hash_key(plaintext),
        key_prefix=plaintext[:12],
        max_devices=max_devices,
        expires_at=expires_at,
    )
    return key, plaintext


def revoke_key(key):
    """Idempotent. Revoking a redeemed key does not alter its Entitlement (7.1)."""
    if key.status != "revoked":
        key.status = "revoked"
        key.save(update_fields=("status",))
    return key


def _atomic(work):
    """One transaction per mutation. PostgreSQL serializes concurrent binds via
    select_for_update row locks; SQLite serializes writers at the database
    level, so a busy write retries the whole check-and-insert (Invariant 3)."""
    for attempt in range(10):
        try:
            with transaction.atomic():
                return work()
        except OperationalError as exc:
            if "locked" not in str(exc) or attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


def redeem(account, plaintext):
    """Section 7.4. Returns (entitlement, created); idempotent for the same Account."""

    def work():
        key = LicenseKey.objects.select_for_update().filter(key_hash=hash_key(plaintext)).first()
        if key is None:
            raise Failure("unknown_key", gettext("This license key is not recognized."))
        if key.status == "revoked":
            raise Failure("key_revoked", gettext("This license key has been revoked."))
        if key.status == "redeemed":
            if key.redeemed_by_id == account.id:
                return key.entitlement, False
            raise Failure(
                "key_already_redeemed", gettext("This license key was already redeemed by another account.")
            )
        if Entitlement.objects.filter(account=account, product=key.product).exists():
            raise Failure(
                "already_entitled", gettext("This account already has an entitlement for this product.")
            )
        entitlement = Entitlement.objects.create(
            account=account,
            product=key.product,
            max_devices=key.max_devices,
            expires_at=key.expires_at,
            source_key=key,
        )
        key.status = "redeemed"
        key.redeemed_by = account
        key.save(update_fields=("status", "redeemed_by"))
        return entitlement, True

    return _atomic(work)


def check_active(entitlement):
    """Section 7.5 step 2 / 7.7: status and expiry gate for bind and validate."""
    if entitlement.status == "suspended":
        raise Failure("entitlement_suspended", gettext("This entitlement is suspended."))
    if entitlement.status == "revoked":
        raise Failure("entitlement_revoked", gettext("This entitlement has been revoked."))
    if entitlement.expires_at is not None and timezone.now() > entitlement.expires_at:
        raise Failure("entitlement_expired", gettext("This entitlement has expired."))


def normalize_fingerprint(raw):
    """Section 4.2: trim only; never HTML-decode; case-sensitive; bounded length."""
    fp = (raw or "").strip()
    if not fp:
        raise Failure("validation_error", gettext("device_fingerprint must not be empty."))
    if len(fp) > FINGERPRINT_MAX_LENGTH:
        raise Failure("validation_error", gettext("device_fingerprint exceeds 128 characters."))
    return fp


def bind(entitlement, raw_fingerprint, display_name=None, *, source_key_id=None):
    """Section 7.5. Returns (device, created); same fingerprint is idempotent."""
    fp = normalize_fingerprint(raw_fingerprint)
    display_name = normalize_display_name(display_name)

    def work():
        if source_key_id is not None:
            key = LicenseKey.objects.select_for_update().get(pk=source_key_id)
            if key.status == "revoked":
                raise Failure("key_revoked", gettext("This license key has been revoked."))
            if key.status != "redeemed":
                raise Failure("unknown_key", gettext("This license key is not recognized."))
        locked = Entitlement.objects.select_for_update().get(pk=entitlement.pk)
        if source_key_id is not None and locked.source_key_id != source_key_id:
            raise Failure("unknown_key", gettext("This license key is not recognized."))
        check_active(locked)
        existing = locked.devices.filter(device_fingerprint=fp, status="bound").first()
        if existing is not None:
            return existing, False
        if locked.devices.filter(status="bound").count() >= locked.max_devices:
            raise Failure("seat_exhausted", gettext("This entitlement has no remaining device seats."))
        budget = max(settings.LICENSE_DEVICE_HISTORY_LIMIT, locked.max_devices)
        excess = locked.devices.count() - budget + 1
        if excess > 0:
            stale_ids = list(
                locked.devices.filter(status="unbound").order_by("pk").values_list("pk", flat=True)[:excess]
            )
            locked.devices.filter(pk__in=stale_ids).delete()
        return locked.devices.create(device_fingerprint=fp, display_name=display_name), True

    return _atomic(work)


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
        raise Failure("unknown_key", gettext("This license key is not recognized."))
    if key.status == "revoked":
        raise Failure("key_revoked", gettext("This license key has been revoked."))
    entitlement = getattr(key, "entitlement", None)
    if entitlement is None:
        raise Failure("unknown_key", gettext("This license key is not recognized."))
    return key, entitlement


def validate(plaintext, raw_fingerprint):
    """Section 7.7. Read-only: MUST NOT create rows."""
    _, entitlement = resolve_redeemed_key(plaintext)
    check_active(entitlement)
    device = entitlement.devices.filter(
        device_fingerprint=normalize_fingerprint(raw_fingerprint), status="bound"
    ).first()
    if device is None:
        raise Failure("unknown_device", gettext("No bound device matches this fingerprint."))
    return device


def validate_text(value):
    if "\x00" in value:
        raise Failure("validation_error", "Text must not contain null characters.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise Failure("validation_error", "Text must contain valid Unicode characters.") from None


def normalize_display_name(value):
    if value is not None:
        validate_text(value)
        if len(value) > 200:
            raise Failure("validation_error", "display_name exceeds 200 characters.")
    return value or None


def rename_device(device, display_name):
    device.display_name = normalize_display_name(display_name)
    device.save(update_fields=("display_name",))
    return device

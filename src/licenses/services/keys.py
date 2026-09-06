import hashlib
import secrets

from ..models import LicenseKey

_KEY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # 32 chars from 29 symbols: ~155 bits (4.1.3)


def hash_key(plaintext):
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def issue_key(product, max_devices, expires_at=None):
    """Returns (key, plaintext). The plaintext is returned once and never stored."""
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

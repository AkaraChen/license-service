from django.db import transaction

from ..models import Entitlement, LicenseKey
from .errors import AlreadyEntitled, KeyAlreadyRedeemed, KeyRevoked, UnknownKey
from .keys import hash_key


def redeem(account, plaintext):
    """Section 7.4. Returns (entitlement, created); idempotent for the same Account."""

    def work():
        key = LicenseKey.objects.select_for_update().filter(key_hash=hash_key(plaintext)).first()
        if key is None:
            raise UnknownKey()
        if key.status == "revoked":
            raise KeyRevoked()
        if key.status == "redeemed":
            if key.redeemed_by_id == account.id:
                return key.entitlement, False
            raise KeyAlreadyRedeemed()
        if Entitlement.objects.filter(account=account, product=key.product).exists():
            raise AlreadyEntitled()
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

    with transaction.atomic():
        return work()

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .product import Product


class LicenseKey(models.Model):
    STATUSES = (("issued", _("issued")), ("redeemed", _("redeemed")), ("revoked", _("revoked")))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="license_keys")
    key_hash = models.CharField(
        max_length=64, unique=True
    )  # SHA-256 hex of plaintext; plaintext never persists
    key_prefix = models.CharField(max_length=16)  # non-secret recognition prefix, cannot authenticate
    max_devices = models.PositiveIntegerField()
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="issued")
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .license_key import LicenseKey
from .product import Product


class Entitlement(models.Model):
    STATUSES = (("active", _("active")), ("suspended", _("suspended")), ("revoked", _("revoked")))
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    max_devices = models.PositiveIntegerField()  # immutable after insert (Invariant 7)
    expires_at = models.DateTimeField(null=True, blank=True)  # immutable after insert
    status = models.CharField(max_length=10, choices=STATUSES, default="active")
    source_key = models.OneToOneField(LicenseKey, on_delete=models.PROTECT, related_name="entitlement")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def seats_available(self):
        bound = self.devices.filter(status="bound").count()
        return max(0, self.max_devices - bound)

    class Meta:
        # Invariant 1: at most one Entitlement per (account_id, product_id).
        constraints = [
            models.UniqueConstraint(fields=("account", "product"), name="one_entitlement_per_pair")
        ]

from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual
from django.utils.translation import gettext_lazy as _

from .entitlement import Entitlement


class Device(models.Model):
    STATUSES = (("bound", _("bound")), ("unbound", _("unbound")))
    entitlement = models.ForeignKey(Entitlement, on_delete=models.CASCADE, related_name="devices")
    device_fingerprint = models.CharField(max_length=128)  # trimmed, case-sensitive, max 128 chars
    display_name = models.CharField(max_length=200, null=True, blank=True)
    bound_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10, choices=STATUSES, default="bound"
    )  # only "bound" occupies a seat

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(display_name__isnull=True)
                | models.Q(LessThanOrEqual(Length("display_name"), 200)),
                name="device_display_name_max_length",
            ),
            models.UniqueConstraint(
                fields=("entitlement", "device_fingerprint"),
                condition=models.Q(status="bound"),
                name="device_bound_fingerprint_unique",
            ),
        ]

"""Core domain model (SPEC 4.1); the Django ORM is the engine-agnostic License
Store. Account = django.contrib.auth.models.User: account_id = User.pk,
is_admin = User.is_staff, password_hash = User.password (PBKDF2-SHA256),
created_at = User.date_joined. One Account type for Admin and Customer."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    code = models.CharField(max_length=64, unique=True)  # trimmed, unique (compared case-insensitively)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


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

    class Meta:
        # Invariant 1: at most one Entitlement per (account_id, product_id).
        constraints = [  # noqa: RUF012 - Django Meta idiom
            models.UniqueConstraint(fields=("account", "product"), name="one_entitlement_per_pair")
        ]


class Device(models.Model):
    STATUSES = (("bound", _("bound")), ("unbound", _("unbound")))
    entitlement = models.ForeignKey(Entitlement, on_delete=models.CASCADE, related_name="devices")
    device_fingerprint = models.CharField(max_length=128)  # trimmed, case-sensitive, max 128 chars
    display_name = models.CharField(max_length=200, null=True, blank=True)
    bound_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10, choices=STATUSES, default="bound"
    )  # only "bound" occupies a seat

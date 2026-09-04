"""Admin console (SPEC 3.1.4): Django Admin, restricted to Admin sessions
(is_staff) by Django itself. Key plaintext is shown once at issue time via a
flash message and never stored; password hashes are never displayed.
"""
from django.contrib import admin, messages
from django.contrib.auth.models import User

from . import services
from .models import Device, Entitlement, LicenseKey, Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")

@admin.register(LicenseKey)
class LicenseKeyAdmin(admin.ModelAdmin):
    list_display = ("key_prefix", "product", "status", "max_devices", "expires_at",
                    "redeemed_by", "created_at")
    fields = ("product", "max_devices", "expires_at")  # add form; key_hash is never shown
    actions = ("revoke_keys",)

    def has_change_permission(self, request, obj=None):
        return False  # issued keys are immutable; revoke via the action below

    def save_model(self, request, obj, form, change):
        key, plaintext = services.issue_key(obj.product, obj.max_devices, obj.expires_at)
        obj.pk = key.pk
        messages.success(request, f"License key issued (shown once, then only the hash is kept): {plaintext}")

    @admin.action(description="Revoke selected license keys")
    def revoke_keys(self, request, queryset):
        for key in queryset:
            services.revoke_key(key)

@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ("account", "product", "status", "max_devices", "expires_at", "created_at")
    fields = ("account", "product", "status", "max_devices", "expires_at", "source_key", "created_at")
    readonly_fields = ("account", "product", "max_devices", "expires_at", "source_key", "created_at")
    # status is the only mutable field (Invariant 7); add is disabled: redeem creates Entitlements.

    def has_add_permission(self, request):
        return False

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_fingerprint", "entitlement", "status", "display_name", "bound_at")
    actions = ("unbind_devices",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Unbind selected devices")
    def unbind_devices(self, request, queryset):
        for device in queryset:
            services.unbind(device)

admin.site.unregister(User)

@admin.register(User)
class AccountAdmin(admin.ModelAdmin):
    """One Account type (4.1.1). Password hashes are never rendered."""

    list_display = ("username", "is_staff", "is_active", "date_joined")
    fields = ("username", "email", "is_staff", "is_active")

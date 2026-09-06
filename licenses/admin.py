"""Admin console (SPEC 3.1.4): Django Admin, restricted to Admin sessions
(is_staff) by Django itself. Key plaintext is shown once at issue time via a
flash message and never stored; password hashes are never displayed.
"""

from admin_extra_buttons.api import ExtraButtonsMixin, button
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _

from . import services
from .models import Device, Entitlement, LicenseKey, Product

BATCH_ISSUE_MAX = 50
_ISSUED_ONCE_SESSION_KEY = "_issued_license_keys_once"


class BatchIssueForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.order_by("code"), label=_("Product"))
    max_devices = forms.IntegerField(min_value=1, initial=1, label=_("Max devices"))
    expires_at = forms.SplitDateTimeField(
        required=False, widget=admin.widgets.AdminSplitDateTime(), label=_("Expires at")
    )
    count = forms.IntegerField(
        min_value=1,
        max_value=BATCH_ISSUE_MAX,
        initial=1,
        label=_("Number of keys"),
        help_text=_("At most 50 keys per batch."),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")


@admin.register(LicenseKey)
class LicenseKeyAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    list_display = (
        "key_prefix",
        "product",
        "status",
        "max_devices",
        "expires_at",
        "redeemed_by",
        "created_at",
    )
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

    @button(
        label=_("Issue batch"),
        permission="licenses.add_licensekey",
        change_list=True,
        change_form=False,
        decorators=[staff_member_required],
    )
    def issue_batch(self, request):
        context = self.get_common_context(request, title=_("Issue batch"))
        issued = request.session.pop(_ISSUED_ONCE_SESSION_KEY, None)
        if issued is not None:
            context["issued"] = issued
            return TemplateResponse(request, "admin/licenses/licensekey/issue_batch.html", context)

        form = BatchIssueForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            product = form.cleaned_data["product"]
            max_devices = form.cleaned_data["max_devices"]
            expires_at = form.cleaned_data["expires_at"]
            count = form.cleaned_data["count"]
            keys = []
            with transaction.atomic():
                for _n in range(count):
                    _key, plaintext = services.issue_key(product, max_devices, expires_at)
                    keys.append(plaintext)
            request.session[_ISSUED_ONCE_SESSION_KEY] = keys
            return redirect("admin:licenses_licensekey_issue_batch")

        context["form"] = form
        return TemplateResponse(request, "admin/licenses/licensekey/issue_batch.html", context)


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

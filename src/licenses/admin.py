"""Admin console (SPEC 3.1.4): Django Admin, restricted to Admin sessions
(is_staff) by Django itself. Key plaintext is shown once at issue time in
the immediate response and never stored; password hashes are never displayed.
"""

import logging

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminSplitDateTimeWidget,
)

from . import accounts, services
from .models import Device, Entitlement, LicenseKey, Product

log = logging.getLogger(__name__)

BATCH_ISSUE_MAX = 50


class BatchIssueForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.order_by("code"), label=_("Product"), widget=UnfoldAdminSelectWidget
    )
    max_devices = forms.IntegerField(
        min_value=1, initial=1, label=_("Max devices"), widget=UnfoldAdminIntegerFieldWidget
    )
    expires_at = forms.SplitDateTimeField(
        required=False, widget=UnfoldAdminSplitDateTimeWidget, label=_("Expires at")
    )
    count = forms.IntegerField(
        min_value=1,
        max_value=BATCH_ISSUE_MAX,
        initial=1,
        label=_("Number of keys"),
        help_text=_("At most 50 keys per batch."),
        widget=UnfoldAdminIntegerFieldWidget,
    )


def issued_response(request, context, keys):
    response = TemplateResponse(
        request, "admin/licenses/licensekey/issue_batch.html", {**context, "issued": keys}
    )
    response["Cache-Control"] = "no-store, private"
    return response


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("code", "name", "created_at")


@admin.register(LicenseKey)
class LicenseKeyAdmin(ModelAdmin):
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
    actions_list = ("issue_batch",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "max_devices":
            kwargs["min_value"] = 1
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return False  # issued keys are immutable; revoke via the action below

    def save_model(self, request, obj, form, change):
        key, plaintext = services.issue_key(obj.product, obj.max_devices, obj.expires_at)
        obj.pk = key.pk
        request._issued_license_key = plaintext
        log.info("issue", extra={"product_id": key.product_id, "key_id": key.pk})

    def response_add(self, request, obj, post_url_continue=None):
        context = {**self.admin_site.each_context(request), "title": _("Issue batch")}
        return issued_response(request, context, [request._issued_license_key])

    @admin.action(description="Revoke selected license keys")
    def revoke_keys(self, request, queryset):
        log.info("revoke", extra={"key_ids": list(queryset.values_list("pk", flat=True))})
        for key in queryset:
            services.revoke_key(key)

    @action(description=_("Issue batch"), permissions=["add"], url_path="issue_batch")
    def issue_batch(self, request):
        context = {**self.admin_site.each_context(request), "title": _("Issue batch")}
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
            log.info("issue_batch", extra={"product_id": product.pk, "count": count})
            return issued_response(request, context, keys)

        context["form"] = form
        return TemplateResponse(request, "admin/licenses/licensekey/issue_batch.html", context)


@admin.register(Entitlement)
class EntitlementAdmin(ModelAdmin):
    list_display = ("account", "product", "status", "max_devices", "expires_at", "created_at")
    fields = ("account", "product", "status", "max_devices", "expires_at", "source_key", "created_at")
    readonly_fields = ("account", "product", "max_devices", "expires_at", "source_key", "created_at")
    # status is the only mutable field (Invariant 7); add is disabled: redeem creates Entitlements.

    def has_add_permission(self, request):
        return False


@admin.register(Device)
class DeviceAdmin(ModelAdmin):
    list_display = ("device_fingerprint", "entitlement", "status", "display_name", "bound_at")
    actions = ("unbind_devices",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Unbind selected devices")
    def unbind_devices(self, request, queryset):
        log.info("unbind", extra={"device_ids": list(queryset.values_list("pk", flat=True))})
        for device in queryset:
            services.unbind(device)


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class AccountAdmin(ModelAdmin):
    """One Account type (4.1.1). Password hashes are never rendered."""

    list_display = ("username", "is_staff", "is_active", "date_joined")
    fields = ("username", "email", "is_staff", "is_active")

    def save_model(self, request, obj, form, change):
        previous = (
            User.objects.filter(pk=obj.pk).values_list("is_active", flat=True).first() if change else None
        )
        super().save_model(request, obj, form, change)
        if previous is not None and previous != obj.is_active:
            accounts.drop_account_sessions(obj)


@admin.register(Group)
class UnfoldGroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

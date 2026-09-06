"""Machine endpoints; Django Ninja owns routing, parsing, serialization and OpenAPI."""

import logging

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import RequestDataTooBig
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404 as django_get_object_or_404
from django.views.decorators.cache import never_cache
from django_ratelimit.exceptions import Ratelimited
from ninja import NinjaAPI, Router, Status
from ninja.decorators import decorate_view
from ninja.errors import ValidationError as SchemaError
from ninja.security import SessionAuth

from .. import accounts, services
from ..models import Device, Entitlement, LicenseKey, Product
from ..services.errors import (
    Conflict,
    Failure,
    Forbidden,
    NotFound,
    RateLimited,
    Unauthenticated,
    ValidationError,
)
from . import schemas as s


class LicenseAPI(NinjaAPI):
    def get_openapi_operation_id(self, operation):
        return operation.view_func.__name__

    def on_exception(self, request, exc):
        if isinstance(exc, Failure):
            return exc.as_response(request)
        if isinstance(exc, (SchemaError, UnicodeError, RequestDataTooBig)):
            return ValidationError().as_response(request)
        return super().on_exception(request, exc)


api = LicenseAPI(title="License Service", version="3.0.0", openapi_url="/openapi.json", docs_url="/docs")


def get_object_or_404(klass, *args, **kwargs):
    try:
        return django_get_object_or_404(klass, *args, **kwargs)
    except Http404:
        raise NotFound() from None


class CustomerSession(SessionAuth):
    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if user is None:
            raise Unauthenticated()
        return user


class AdminSession(CustomerSession):
    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if not user.is_staff:
            raise Forbidden()
        return user


customer_session = CustomerSession(csrf=False)
admin_session = AdminSession(csrf=False)

log = logging.getLogger(__name__)

admin = Router(auth=admin_session)
customer = Router(auth=customer_session)
public = Router()


@public.post("/auth/register", response={201: dict[str, s.Account], **s.ERROR_RESPONSES})
def register(request, data: s.Credentials):
    try:
        user = accounts.register_account(data.username, data.password, request=request)
    except Ratelimited:
        raise RateLimited() from None
    log.info("register", extra={"account_id": user.pk})
    return Status(201, {"account": user})


@public.post("/auth/login", response={200: dict[str, s.Account], **s.ERROR_RESPONSES})
def login(request, data: s.Credentials):
    form = AuthenticationForm(request, data=data.model_dump())
    if not form.is_valid():
        raise Unauthenticated("Invalid username or password.")
    user = form.get_user()
    auth_login(request, user)
    log.info("login", extra={"account_id": user.pk})
    return Status(200, {"account": user})


@customer.post("/auth/logout", response={200: dict[str, bool], **s.ERROR_RESPONSES})
def logout(request, data: s.Empty = s.Empty()):
    auth_logout(request)
    return Status(200, {"ok": True})


@admin.post("/products", response={201: dict[str, s.Product], **s.ERROR_RESPONSES})
def create_product(request, data: s.ProductCreate):
    code = data.code.strip()
    if not code:
        raise ValidationError("code must not be empty.")
    try:
        with transaction.atomic():
            product = Product.objects.create(code=code, name=data.name)
    except IntegrityError:
        raise Conflict() from None
    log.info("create_product", extra={"product_id": product.pk})
    return Status(201, {"product": product})


@admin.patch("/products/{pk}", response={200: dict[str, s.Product], **s.ERROR_RESPONSES})
def update_product(request, pk: int, data: s.ProductUpdate):
    product = get_object_or_404(Product, pk=pk)
    if "name" in data.model_fields_set:
        product.name = data.name
        product.save(update_fields=("name",))
    log.info("update_product", extra={"product_id": product.pk})
    return Status(200, {"product": product})


@admin.post("/license-keys", response={201: s.IssuedKey, **s.ERROR_RESPONSES})
@decorate_view(never_cache)
def issue_license_key(request, data: s.KeyIssue):
    product = get_object_or_404(Product, pk=data.product_id)
    key, plaintext = services.issue_key(product, data.max_devices, data.expires_at)
    log.info("issue", extra={"product_id": product.pk, "key_id": key.pk})
    return Status(201, {"key": key, "license_key": plaintext})


@admin.post("/license-keys/{pk}/revoke", response={200: dict[str, s.Key], **s.ERROR_RESPONSES})
def revoke_license_key(request, pk: int, data: s.Empty = s.Empty()):
    key = services.revoke_key(get_object_or_404(LicenseKey, pk=pk))
    log.info("revoke", extra={"product_id": key.product_id, "key_id": key.pk})
    return Status(200, {"key": key})


@admin.post("/entitlements/{pk}/status", response={200: dict[str, s.Entitlement], **s.ERROR_RESPONSES})
def set_entitlement_status(request, pk: int, data: s.EntitlementStatus):
    entitlement = get_object_or_404(Entitlement, pk=pk)
    entitlement.status = data.status
    entitlement.save(update_fields=("status",))
    log.info(
        "entitlement_status", extra={"product_id": entitlement.product_id, "entitlement_id": entitlement.pk}
    )
    return Status(200, {"entitlement": entitlement})


@admin.post("/devices/{pk}/unbind", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
def unbind_device(request, pk: int, data: s.Empty = s.Empty()):
    device = services.unbind(get_object_or_404(Device, pk=pk))
    log.info("unbind", extra={"entitlement_id": device.entitlement_id, "device_id": device.pk})
    return Status(200, {"device": device})


@admin.get("/products", response={200: dict[str, list[s.Product]], **s.ERROR_RESPONSES})
def list_products(request):
    return {"products": Product.objects.order_by("pk")}


@admin.get("/license-keys", response={200: dict[str, list[s.Key]], **s.ERROR_RESPONSES})
def list_license_keys(request):
    return {"license_keys": LicenseKey.objects.order_by("pk")}


@admin.get("/accounts", response={200: dict[str, list[s.Account]], **s.ERROR_RESPONSES})
def list_accounts(request):
    return {"accounts": User.objects.order_by("pk")}


@admin.get("/entitlements", response={200: dict[str, list[s.Entitlement]], **s.ERROR_RESPONSES})
def list_entitlements(request):
    return {"entitlements": Entitlement.objects.order_by("pk")}


@admin.get("/devices", response={200: dict[str, list[s.Device]], **s.ERROR_RESPONSES})
def list_devices(request):
    return {"devices": Device.objects.order_by("pk")}


@admin.get("/products/{pk}", response={200: dict[str, s.Product], **s.ERROR_RESPONSES})
def get_product(request, pk: int):
    return {"product": get_object_or_404(Product, pk=pk)}


@admin.get("/accounts/{pk}", response={200: dict[str, s.Account], **s.ERROR_RESPONSES})
def get_account(request, pk: int):
    return {"account": get_object_or_404(User, pk=pk)}


@customer.post(
    "/me/redeem", response={200: dict[str, s.Entitlement], 201: dict[str, s.Entitlement], **s.ERROR_RESPONSES}
)
def redeem_license_key(request, data: s.Redeem):
    entitlement, created = services.redeem(request.user, data.license_key)
    log.info("redeem", extra={"product_id": entitlement.product_id, "entitlement_id": entitlement.pk})
    return Status(201 if created else 200, {"entitlement": entitlement})


@customer.get("/me/entitlements", response={200: dict[str, list[s.Entitlement]], **s.ERROR_RESPONSES})
def list_my_entitlements(request):
    return Status(200, {"entitlements": request.user.entitlements.order_by("pk")})


@customer.get("/me/entitlements/{pk}", response={200: dict[str, s.Entitlement], **s.ERROR_RESPONSES})
def get_my_entitlement(request, pk: int):
    return Status(200, {"entitlement": (get_object_or_404(Entitlement, pk=pk, account=request.user))})


@customer.get("/me/entitlements/{pk}/devices", response={200: dict[str, list[s.Device]], **s.ERROR_RESPONSES})
def list_my_devices(request, pk: int):
    entitlement = get_object_or_404(Entitlement, pk=pk, account=request.user)
    return Status(200, {"devices": entitlement.devices.order_by("pk")})


@customer.post(
    "/me/entitlements/{pk}/devices",
    response={200: dict[str, s.Device], 201: dict[str, s.Device], **s.ERROR_RESPONSES},
)
def bind_my_device(request, pk: int, data: s.DeviceBind):
    entitlement = get_object_or_404(Entitlement, pk=pk, account=request.user)
    device, created = services.bind(entitlement, data.device_fingerprint, data.display_name)
    log.info(
        "bind",
        extra={
            "product_id": entitlement.product_id,
            "entitlement_id": entitlement.pk,
            "device_id": device.pk,
        },
    )
    return Status(201 if created else 200, {"device": device})


@customer.post("/me/devices/{pk}/unbind", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
def unbind_my_device(request, pk: int, data: s.Empty = s.Empty()):
    device = services.unbind(get_object_or_404(Device, pk=pk, entitlement__account=request.user))
    log.info("unbind", extra={"entitlement_id": device.entitlement_id, "device_id": device.pk})
    return Status(200, {"device": device})


@customer.patch("/me/devices/{pk}", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
def set_my_device_display_name(request, pk: int, data: s.DeviceName):
    device = get_object_or_404(Device, pk=pk, entitlement__account=request.user)
    services.rename_device(device, data.display_name)
    log.info("rename", extra={"entitlement_id": device.entitlement_id, "device_id": device.pk})
    return Status(200, {"device": device})


@public.post("/activate", response={200: dict[str, s.Device], 201: dict[str, s.Device], **s.ERROR_RESPONSES})
def activate_device(request, data: s.Activate):
    key, entitlement = services.resolve_redeemed_key(data.license_key)
    device, created = services.bind(
        entitlement, data.device_fingerprint, data.display_name, source_key_id=key.pk
    )
    log.info(
        "activate",
        extra={
            "product_id": entitlement.product_id,
            "entitlement_id": entitlement.pk,
            "device_id": device.pk,
        },
    )
    return Status(201 if created else 200, {"device": device})


@public.post("/validate", response={200: s.ValidatedDevice, **s.ERROR_RESPONSES})
def validate_device(request, data: s.Validate):
    device = services.validate(data.license_key, data.device_fingerprint)
    log.info("validate", extra={"entitlement_id": device.entitlement_id, "device_id": device.pk})
    return Status(200, {"valid": True, "device": device})


api.add_router("/api", admin)
api.add_router("/api", customer)
api.add_router("/api", public)

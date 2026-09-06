"""Machine endpoints; Django Ninja owns routing, parsing, serialization and OpenAPI."""

from functools import wraps

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django_ratelimit.exceptions import Ratelimited
from ninja import Router, Status
from ninja.decorators import decorate_view
from ninja.errors import AuthenticationError, ValidationError
from redis.exceptions import RedisError

from .. import accounts, audit, services
from ..models import Device, Entitlement, LicenseKey, Product
from ..services import Failure
from . import schemas as s
from .http import admin_session, api, customer_session

admin = Router(auth=admin_session)
customer = Router(auth=customer_session)
public = Router()


def as_error(request, exc):
    audit.resources(request, outcome=exc.error)
    return Status(exc.status, {"error": exc.error, "message": exc.message})


def staff_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_staff", False):
            audit.resources(request, outcome="forbidden")
            return Status(403, {"error": "forbidden", "message": "Admin privileges required."})
        return view(request, *args, **kwargs)

    return wrapped


def found(model, **lookup):
    try:
        return get_object_or_404(model, **lookup)
    except Http404 as exc:
        raise Failure("not_found", "Not found.") from exc


def _framework_error(request, error, message, status):
    audit.resources(request, outcome=error)
    return JsonResponse({"error": error, "message": message}, status=status)


def invalid_request(request, exc):
    return _framework_error(request, "validation_error", "The request body is invalid or too large.", 400)


def store_unavailable(request, exc):
    return _framework_error(request, "store_unavailable", "The license store is unavailable.", 503)


def unauthenticated(request, exc):
    return _framework_error(request, "unauthenticated", "A session cookie is required.", 401)


api.add_exception_handler(AuthenticationError, unauthenticated)
api.add_exception_handler(ValidationError, invalid_request)
api.add_exception_handler(DataError, invalid_request)
api.add_exception_handler(RequestDataTooBig, invalid_request)
api.add_exception_handler(UnicodeError, invalid_request)
api.add_exception_handler(OperationalError, store_unavailable)
api.add_exception_handler(RedisError, store_unavailable)


@public.post("/auth/register", response={201: dict[str, s.Account], **s.ERROR_RESPONSES})
def register(request, data: s.Credentials):
    try:
        user = accounts.register_account(data.username, data.password, request=request)
    except Failure as exc:
        return as_error(request, exc)
    except Ratelimited:
        audit.resources(request, outcome="rate_limited")
        return Status(
            429, {"error": "rate_limited", "message": "Registration limit reached. Please try again later."}
        )
    audit.resources(request, actor="customer", account_id=user.pk)
    return Status(201, {"account": user})


@public.post("/auth/login", response={200: dict[str, s.Account], **s.ERROR_RESPONSES})
def login(request, data: s.Credentials):
    form = AuthenticationForm(request, data=data.model_dump())
    if not form.is_valid():
        audit.resources(request, outcome="unauthenticated")
        return Status(401, {"error": "unauthenticated", "message": "Invalid username or password."})
    user = form.get_user()
    auth_login(request, user)
    audit.resources(request, actor="admin" if user.is_staff else "customer", account_id=user.pk)
    return Status(200, {"account": user})


@customer.post("/auth/logout", response={200: dict[str, bool], **s.ERROR_RESPONSES})
def logout(request, data: s.Empty = s.Empty()):
    auth_logout(request)
    return Status(200, {"ok": True})


@admin.post("/products", response={201: dict[str, s.Product], **s.ERROR_RESPONSES})
@staff_only
def create_product(request, data: s.ProductCreate):
    code = data.code.strip()
    if not code:
        audit.resources(request, outcome="validation_error")
        return Status(400, {"error": "validation_error", "message": "code must not be empty."})
    try:
        with transaction.atomic():
            product = Product.objects.create(code=code, name=data.name)
    except IntegrityError:
        audit.resources(request, outcome="conflict")
        return Status(
            409, {"error": "conflict", "message": "The requested change conflicts with existing data."}
        )
    audit.resources(request, product_id=product.pk)
    return Status(201, {"product": product})


@admin.patch("/products/{pk}", response={200: dict[str, s.Product], **s.ERROR_RESPONSES})
@staff_only
def update_product(request, pk: int, data: s.ProductUpdate):
    try:
        product = found(Product, pk=pk)
    except Failure as exc:
        return as_error(request, exc)
    if "name" in data.model_fields_set:
        product.name = data.name
        product.save(update_fields=("name",))
    audit.resources(request, product_id=product.pk)
    return Status(200, {"product": product})


@admin.post("/license-keys", response={201: s.IssuedKey, **s.ERROR_RESPONSES})
@decorate_view(never_cache)
@staff_only
def issue_license_key(request, data: s.KeyIssue):
    try:
        product = found(Product, pk=data.product_id)
        key, plaintext = services.issue_key(product, data.max_devices, data.expires_at)
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, product_id=product.pk)
    return Status(201, {"key": key, "license_key": plaintext})


@admin.post("/license-keys/{pk}/revoke", response={200: dict[str, s.Key], **s.ERROR_RESPONSES})
@staff_only
def revoke_license_key(request, pk: int, data: s.Empty = s.Empty()):
    try:
        key = services.revoke_key(found(LicenseKey, pk=pk))
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, product_id=key.product_id)
    return Status(200, {"key": key})


@admin.post("/entitlements/{pk}/status", response={200: dict[str, s.Entitlement], **s.ERROR_RESPONSES})
@staff_only
def set_entitlement_status(request, pk: int, data: s.EntitlementStatus):
    try:
        entitlement = found(Entitlement, pk=pk)
    except Failure as exc:
        return as_error(request, exc)
    entitlement.status = data.status
    entitlement.save(update_fields=("status",))
    audit.resources(request, product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return Status(200, {"entitlement": entitlement})


@admin.post("/devices/{pk}/unbind", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
@staff_only
def unbind_device(request, pk: int, data: s.Empty = s.Empty()):
    try:
        device = services.unbind(found(Device, pk=pk))
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, entitlement_id=device.entitlement_id, device_id=device.pk)
    return Status(200, {"device": device})


@admin.get("/products", response={200: dict[str, list[s.Product]], **s.ERROR_RESPONSES})
@staff_only
def list_products(request):
    return {"products": Product.objects.order_by("pk")}


@admin.get("/license-keys", response={200: dict[str, list[s.Key]], **s.ERROR_RESPONSES})
@staff_only
def list_license_keys(request):
    return {"license_keys": LicenseKey.objects.order_by("pk")}


@admin.get("/accounts", response={200: dict[str, list[s.Account]], **s.ERROR_RESPONSES})
@staff_only
def list_accounts(request):
    return {"accounts": User.objects.order_by("pk")}


@admin.get("/entitlements", response={200: dict[str, list[s.Entitlement]], **s.ERROR_RESPONSES})
@staff_only
def list_entitlements(request):
    return {"entitlements": Entitlement.objects.order_by("pk")}


@admin.get("/devices", response={200: dict[str, list[s.Device]], **s.ERROR_RESPONSES})
@staff_only
def list_devices(request):
    return {"devices": Device.objects.order_by("pk")}


@admin.get("/products/{pk}", response={200: dict[str, s.Product], **s.ERROR_RESPONSES})
@staff_only
def get_product(request, pk: int):
    try:
        return {"product": found(Product, pk=pk)}
    except Failure as exc:
        return as_error(request, exc)


@admin.get("/accounts/{pk}", response={200: dict[str, s.Account], **s.ERROR_RESPONSES})
@staff_only
def get_account(request, pk: int):
    try:
        return {"account": found(User, pk=pk)}
    except Failure as exc:
        return as_error(request, exc)


@customer.post(
    "/me/redeem", response={200: dict[str, s.Entitlement], 201: dict[str, s.Entitlement], **s.ERROR_RESPONSES}
)
def redeem_license_key(request, data: s.Redeem):
    try:
        entitlement, created = services.redeem(request.user, data.license_key)
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return Status(201 if created else 200, {"entitlement": entitlement})


@customer.get("/me/entitlements", response={200: dict[str, list[s.Entitlement]], **s.ERROR_RESPONSES})
def list_my_entitlements(request):
    return Status(200, {"entitlements": request.user.entitlements.order_by("pk")})


@customer.get("/me/entitlements/{pk}", response={200: dict[str, s.Entitlement], **s.ERROR_RESPONSES})
def get_my_entitlement(request, pk: int):
    try:
        return Status(200, {"entitlement": found(Entitlement, pk=pk, account=request.user)})
    except Failure as exc:
        return as_error(request, exc)


@customer.get("/me/entitlements/{pk}/devices", response={200: dict[str, list[s.Device]], **s.ERROR_RESPONSES})
def list_my_devices(request, pk: int):
    try:
        entitlement = found(Entitlement, pk=pk, account=request.user)
    except Failure as exc:
        return as_error(request, exc)
    return Status(200, {"devices": entitlement.devices.order_by("pk")})


@customer.post(
    "/me/entitlements/{pk}/devices",
    response={200: dict[str, s.Device], 201: dict[str, s.Device], **s.ERROR_RESPONSES},
)
def bind_my_device(request, pk: int, data: s.DeviceBind):
    try:
        entitlement = found(Entitlement, pk=pk, account=request.user)
        device, created = services.bind(entitlement, data.device_fingerprint, data.display_name)
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(
        request, product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk
    )
    return Status(201 if created else 200, {"device": device})


@customer.post("/me/devices/{pk}/unbind", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
def unbind_my_device(request, pk: int, data: s.Empty = s.Empty()):
    try:
        device = services.unbind(found(Device, pk=pk, entitlement__account=request.user))
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, entitlement_id=device.entitlement_id, device_id=device.pk)
    return Status(200, {"device": device})


@customer.patch("/me/devices/{pk}", response={200: dict[str, s.Device], **s.ERROR_RESPONSES})
def set_my_device_display_name(request, pk: int, data: s.DeviceName):
    try:
        device = found(Device, pk=pk, entitlement__account=request.user)
        services.rename_device(device, data.display_name)
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, entitlement_id=device.entitlement_id, device_id=device.pk)
    return Status(200, {"device": device})


@public.post("/activate", response={200: dict[str, s.Device], 201: dict[str, s.Device], **s.ERROR_RESPONSES})
def activate_device(request, data: s.Activate):
    try:
        key, entitlement = services.resolve_redeemed_key(data.license_key)
        device, created = services.bind(
            entitlement, data.device_fingerprint, data.display_name, source_key_id=key.pk
        )
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(
        request, product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk
    )
    return Status(201 if created else 200, {"device": device})


@public.post("/validate", response={200: s.ValidatedDevice, **s.ERROR_RESPONSES})
def validate_device(request, data: s.Validate):
    try:
        device = services.validate(data.license_key, data.device_fingerprint)
    except Failure as exc:
        return as_error(request, exc)
    audit.resources(request, entitlement_id=device.entitlement_id, device_id=device.pk)
    return Status(200, {"valid": True, "device": device})


api.add_router("/api", admin)
api.add_router("/api", customer)
api.add_router("/api", public)

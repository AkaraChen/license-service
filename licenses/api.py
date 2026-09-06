"""JSON machine API (SPEC 5, 11). The OPERATIONS registry is the single source
for URL patterns, validation, and OpenAPI (Section 12). Handlers return ORM
rows; schemas.py / openapi_gen dump them. Error envelope (5.3); session cookie."""

import json
import logging
import uuid

from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.db import OperationalError
from django.http import JsonResponse
from django.urls import path
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from openapi_gen import dump_model

from . import schemas, services
from .models import Device, Entitlement, LicenseKey, Product
from .services import Failure

log = logging.getLogger("licenses.api")
HTTP_STATUS = {  # Section 5.3 (normative) error class -> HTTP status
    cls: int(code)
    for cls, code in (
        pair.split(":")
        for pair in (
            "validation_error:400 unauthenticated:401 forbidden:403 not_found:404 unknown_key:404 "
            "unknown_device:404 conflict:409 already_entitled:409 key_already_redeemed:409 key_revoked:409 "
            "seat_exhausted:409 entitlement_suspended:409 entitlement_revoked:409 entitlement_expired:409 "
            "store_unavailable:503"
        ).split()
    )
}
OPERATIONS = []  # (name, method, path, auth, fields, handler, responses)


def op(name, method, op_path, auth, fields=()):
    def register(handler):
        OPERATIONS.append((name, method, op_path, auth, fields, handler, schemas.RESPONSES[name]))
        return handler

    return register


def _error(error, message, status=None):
    body = dump_model(schemas.ErrorBody, {"error": error, "message": message})
    return JsonResponse(body, status=status or HTTP_STATUS[error])


def parse_body(request, fields):
    """Section 5.2: strict JSON object; unknown fields rejected; no partial mutation."""
    if request.method not in ("POST", "PATCH"):
        return {}
    if not request.body:
        data = {}
    elif request.content_type != "application/json":
        raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
    else:
        try:
            data = json.loads(request.body)
        except ValueError:
            raise Failure("validation_error", "Body must be a JSON object.")
    if not isinstance(data, dict):
        raise Failure("validation_error", "Body must be a JSON object.")
    unknown = sorted(set(data) - {name for name, _, _ in fields})
    if unknown:
        raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
    for name, kind, required in fields:
        if name not in data:
            if required:
                raise Failure("validation_error", f"Missing required field: {name}.")
            continue
        value = data[name]
        valid = {
            "str": type(value) is str,
            "int": type(value) is int,
            "str?": value is None or type(value) is str,
            "dt?": value is None or (type(value) is str and parse_datetime(value) is not None),
        }[kind]
        if not valid:
            raise Failure("validation_error", f"Field {name} has an invalid value.")
        if kind == "dt?":
            data[name] = parse_datetime(value) if value else None
    return data


@csrf_exempt  # writes require a JSON content type; browsers use the CSRF-protected HTML pages
def dispatch(request, op_path, **path_params):
    by_method = _BY_PATH[op_path]
    if request.method not in by_method:
        return _error("validation_error", "Method not allowed.", 405)
    name, _, _, auth, fields, handler, responses = by_method[request.method]
    ctx = {"actor": "anonymous", "rid": request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])}
    try:
        user = request.user
        if auth in ("session", "admin"):
            if not user.is_authenticated:
                raise Failure("unauthenticated", "A session cookie is required.")
            if auth == "admin" and not user.is_staff:
                raise Failure("forbidden", "Admin privileges required.")
            ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        payload, status = handler(request, parse_body(request, fields), ctx, **path_params)
        ctx["outcome"] = "success"
        _audit(name, ctx)
        return JsonResponse(dump_model(responses[status], payload), status=status)
    except (Failure, OperationalError) as exc:
        error = exc.error if isinstance(exc, Failure) else "store_unavailable"
        message = exc.message if isinstance(exc, Failure) else "The license store is unavailable."
        ctx["outcome"] = error
        _audit(name, ctx)
        return _error(error, message)


def _audit(op_name, ctx):
    """Section 13 fields per mutating/validate call; never logs secrets or raw fingerprints."""
    log.info("op=%s %s", op_name, " ".join(f"{k}={v}" for k, v in ctx.items()))


def _get(model, pk):
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise Failure("not_found", f"Unknown {model.__name__.lower()} id.")
    return obj


def _mine(model, pk, user):
    """Invariant 6: foreign rows answer not_found and never leak existence."""
    obj = model.objects.filter(pk=pk).first()
    if (
        obj is None
        or (hasattr(obj, "account_id") and obj.account_id != user.pk)
        or (hasattr(obj, "entitlement") and obj.entitlement.account_id != user.pk)
    ):
        raise Failure("not_found", "Not found.")
    return obj


def _list_op(name, op_path, auth, model):
    op(name, "GET", op_path, auth)(lambda request, data, ctx: (model.objects.order_by("pk"), 200))


def _get_op(name, op_path, auth, model):
    op(name, "GET", op_path, auth)(lambda request, data, ctx, pk: (_get(model, pk), 200))


@op("register", "POST", "auth/register", "anonymous", (("username", "str", True), ("password", "str", True)))
def register(request, data, ctx):
    user = services.register_account(data["username"], data["password"])
    ctx.update(actor="customer", account_id=user.pk)
    return user, 201


@op("login", "POST", "auth/login", "anonymous", (("username", "str", True), ("password", "str", True)))
def login_op(request, data, ctx):
    user = services.authenticate_account(request, data["username"], data["password"])
    login(request, user)
    ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
    return user, 200


@op("logout", "POST", "auth/logout", "session")
def logout_op(request, data, ctx):
    logout(request)
    return None, 200


@op("create_product", "POST", "products", "admin", (("code", "str", True), ("name", "str", True)))
def create_product(request, data, ctx):
    code = data["code"].strip()
    if not code:
        raise Failure("validation_error", "code must not be empty.")
    if Product.objects.filter(code__iexact=code).exists():
        raise Failure("conflict", "A product with this code already exists.")
    product = Product.objects.create(code=code, name=data["name"])
    ctx["product_id"] = product.pk
    return product, 201


@op("update_product", "PATCH", "products/{pk}", "admin", (("name", "str", False),))  # code never changes
def update_product(request, data, ctx, pk):
    product = _get(Product, pk)
    if "name" in data:
        product.name = data["name"]
        product.save(update_fields=("name",))
    ctx["product_id"] = product.pk
    return product, 200


@op(
    "issue_license_key",
    "POST",
    "license-keys",
    "admin",
    (("product_id", "int", True), ("max_devices", "int", True), ("expires_at", "dt?", False)),
)
def issue_license_key(request, data, ctx):
    product = _get(Product, data["product_id"])
    key, plaintext = services.issue_key(product, data["max_devices"], data.get("expires_at"))
    ctx["product_id"] = product.pk
    return {"key": key, "license_key": plaintext}, 201  # plaintext returned once, here only


@op("revoke_license_key", "POST", "license-keys/{pk}/revoke", "admin")
def revoke_license_key(request, data, ctx, pk):
    key = services.revoke_key(_get(LicenseKey, pk))
    ctx["product_id"] = key.product_id
    return key, 200


@op("set_entitlement_status", "POST", "entitlements/{pk}/status", "admin", (("status", "str", True),))
def set_entitlement_status(request, data, ctx, pk):  # max_devices/expires_at are unknown fields (Invariant 7)
    entitlement = _get(Entitlement, pk)
    if data["status"] not in ("active", "suspended", "revoked"):
        raise Failure("validation_error", "status must be active, suspended, or revoked.")
    entitlement.status = data["status"]
    entitlement.save(update_fields=("status",))
    ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return entitlement, 200


@op("unbind_device", "POST", "devices/{pk}/unbind", "admin")
def unbind_device(request, data, ctx, pk):
    device = services.unbind(_get(Device, pk))
    ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return device, 200


_list_op("list_products", "products", "admin", Product)
_list_op("list_license_keys", "license-keys", "admin", LicenseKey)
_list_op("list_accounts", "accounts", "admin", User)
_list_op("list_entitlements", "entitlements", "admin", Entitlement)
_list_op("list_devices", "devices", "admin", Device)
_get_op("get_product", "products/{pk}", "admin", Product)
_get_op("get_account", "accounts/{pk}", "admin", User)


@op("redeem_license_key", "POST", "me/redeem", "session", (("license_key", "str", True),))
def redeem_license_key(request, data, ctx):
    entitlement, created = services.redeem(request.user, data["license_key"])
    ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return entitlement, 201 if created else 200


@op("list_my_entitlements", "GET", "me/entitlements", "session")
def list_my_entitlements(request, data, ctx):
    return request.user.entitlements.order_by("pk"), 200


@op("get_my_entitlement", "GET", "me/entitlements/{pk}", "session")
def get_my_entitlement(request, data, ctx, pk):
    return _mine(Entitlement, pk, request.user), 200


@op("list_my_devices", "GET", "me/entitlements/{pk}/devices", "session")
def list_my_devices(request, data, ctx, pk):
    return _mine(Entitlement, pk, request.user).devices.order_by("pk"), 200


@op(
    "bind_my_device",
    "POST",
    "me/entitlements/{pk}/devices",
    "session",
    (("device_fingerprint", "str", True), ("display_name", "str?", False)),
)
def bind_my_device(request, data, ctx, pk):
    entitlement = _mine(Entitlement, pk, request.user)
    device, created = services.bind(entitlement, data["device_fingerprint"], data.get("display_name"))
    ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk)
    return device, 201 if created else 200


@op("unbind_my_device", "POST", "me/devices/{pk}/unbind", "session")
def unbind_my_device(request, data, ctx, pk):
    device = services.unbind(_mine(Device, pk, request.user))
    ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return device, 200


@op("set_my_device_display_name", "PATCH", "me/devices/{pk}", "session", (("display_name", "str?", True),))
def set_my_device_display_name(request, data, ctx, pk):
    device = _mine(Device, pk, request.user)
    device.display_name = data["display_name"]
    device.save(update_fields=("display_name",))
    ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return device, 200


@op(
    "activate_device",
    "POST",
    "activate",
    "anonymous",
    (("license_key", "str", True), ("device_fingerprint", "str", True), ("display_name", "str?", False)),
)
def activate_device(request, data, ctx):
    ctx["actor"] = "application"
    _, entitlement = services.resolve_redeemed_key(data["license_key"])
    device, created = services.bind(entitlement, data["device_fingerprint"], data.get("display_name"))
    ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk)
    return device, 201 if created else 200


@op(
    "validate_device",
    "POST",
    "validate",
    "anonymous",
    (("license_key", "str", True), ("device_fingerprint", "str", True)),
)
def validate_device(request, data, ctx):
    ctx["actor"] = "application"
    device = services.validate(data["license_key"], data["device_fingerprint"])
    ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return device, 200


_BY_PATH = {}
for _entry in OPERATIONS:
    _BY_PATH.setdefault(_entry[2], {})[_entry[1]] = _entry
urlpatterns = [
    path(f"api/{p.replace('{', '<int:').replace('}', '>')}", dispatch, {"op_path": p}) for p in _BY_PATH
]

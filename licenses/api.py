"""Explicit Django views. Request/response fields live in schemas; HTTP policy in api_http."""

from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from . import schemas, services
from .api_http import HTTP_STATUS as HTTP_STATUS
from .api_http import api_view
from .models import Device, Entitlement, LicenseKey, Product
from .services import Failure


@api_view(("POST",), access="anonymous")
def register(request):
    data = schemas.Credentials.from_request(request)
    user = services.register_account(data.username, data.password, request=request)
    request.audit_context.update(actor="customer", account_id=user.pk)
    return JsonResponse({"account": schemas.Account.model_validate(user).model_dump(mode="json")}, status=201)


register.openapi = {"POST": {"operationId": "register", "body": schemas.Credentials}}


@api_view(("POST",), access="anonymous")
def login_op(request):
    data = schemas.Credentials.from_request(request)
    user = services.authenticate_account(request, data.username, data.password)
    login(request, user)
    request.audit_context.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
    return JsonResponse({"account": schemas.Account.model_validate(user).model_dump(mode="json")}, status=200)


login_op.openapi = {"POST": {"operationId": "login", "body": schemas.Credentials}}


@api_view(("POST",), access="session")
def logout_op(request):
    schemas.EmptyBody.from_request(request)
    logout(request)
    return JsonResponse({"ok": True}, status=200)


logout_op.openapi = {"POST": {"operationId": "logout", "body": schemas.EmptyBody}}


@api_view(("GET", "POST"), access="admin")
def products(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "products": [
                    schemas.Product.model_validate(item).model_dump(mode="json")
                    for item in Product.objects.order_by("pk")
                ]
            },
            status=200,
        )

    data = schemas.CreateProduct.from_request(request)
    if Product.objects.filter(code__iexact=data.code).exists():
        raise Failure("conflict", "A product with this code already exists.")
    product = Product.objects.create(code=data.code, name=data.name)
    request.audit_context["product_id"] = product.pk
    return JsonResponse(
        {"product": schemas.Product.model_validate(product).model_dump(mode="json")}, status=201
    )


products.openapi = {
    "GET": {"operationId": "list_products"},
    "POST": {"operationId": "create_product", "body": schemas.CreateProduct},
}


@api_view(("GET", "PATCH"), access="admin")
def product_detail(request, pk):
    if request.method == "GET":
        product = get_object_or_404(Product, pk=pk)
        return JsonResponse(
            {"product": schemas.Product.model_validate(product).model_dump(mode="json")}, status=200
        )

    data = schemas.UpdateProduct.from_request(request)
    product = get_object_or_404(Product, pk=pk)
    if "name" in data.model_fields_set:
        product.name = data.name
        product.save(update_fields=("name",))
    request.audit_context["product_id"] = product.pk
    return JsonResponse(
        {"product": schemas.Product.model_validate(product).model_dump(mode="json")}, status=200
    )


product_detail.openapi = {
    "GET": {"operationId": "get_product"},
    "PATCH": {"operationId": "update_product", "body": schemas.UpdateProduct},
}


@api_view(("GET", "POST"), access="admin")
def license_keys(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "license_keys": [
                    schemas.LicenseKey.model_validate(item).model_dump(mode="json")
                    for item in LicenseKey.objects.order_by("pk")
                ]
            },
            status=200,
        )

    data = schemas.IssueKey.from_request(request)
    product = get_object_or_404(Product, pk=data.product_id)
    key, plaintext = services.issue_key(product, data.max_devices, data.expires_at)
    request.audit_context["product_id"] = product.pk
    response = JsonResponse(
        {"key": schemas.LicenseKey.model_validate(key).model_dump(mode="json"), "license_key": plaintext},
        status=201,
    )
    response["Cache-Control"] = "no-store, private"
    return response


license_keys.openapi = {
    "GET": {"operationId": "list_license_keys"},
    "POST": {"operationId": "issue_license_key", "body": schemas.IssueKey},
}


@api_view(("POST",), access="admin")
def revoke_license_key(request, pk):
    schemas.EmptyBody.from_request(request)
    key = get_object_or_404(LicenseKey, pk=pk)
    key = services.revoke_key(key)
    request.audit_context["product_id"] = key.product_id
    return JsonResponse({"key": schemas.LicenseKey.model_validate(key).model_dump(mode="json")}, status=200)


revoke_license_key.openapi = {"POST": {"operationId": "revoke_license_key", "body": schemas.EmptyBody}}


@api_view(("POST",), access="admin")
def set_entitlement_status(request, pk):
    data = schemas.SetEntitlementStatus.from_request(request)
    entitlement = get_object_or_404(Entitlement, pk=pk)
    entitlement.status = data.status
    entitlement.save(update_fields=("status",))
    request.audit_context.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return JsonResponse(
        {"entitlement": schemas.Entitlement.model_validate(entitlement).model_dump(mode="json")}, status=200
    )


set_entitlement_status.openapi = {
    "POST": {"operationId": "set_entitlement_status", "body": schemas.SetEntitlementStatus}
}


@api_view(("POST",), access="admin")
def unbind_device(request, pk):
    schemas.EmptyBody.from_request(request)
    device = get_object_or_404(Device, pk=pk)
    device = services.unbind(device)
    request.audit_context.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return JsonResponse({"device": schemas.Device.model_validate(device).model_dump(mode="json")}, status=200)


unbind_device.openapi = {"POST": {"operationId": "unbind_device", "body": schemas.EmptyBody}}


@api_view(("GET",), access="admin")
def list_accounts(request):
    return JsonResponse(
        {
            "accounts": [
                schemas.Account.model_validate(item).model_dump(mode="json")
                for item in User.objects.order_by("pk")
            ]
        },
        status=200,
    )


list_accounts.openapi = {"GET": {"operationId": "list_accounts"}}


@api_view(("GET",), access="admin")
def list_entitlements(request):
    return JsonResponse(
        {
            "entitlements": [
                schemas.Entitlement.model_validate(item).model_dump(mode="json")
                for item in Entitlement.objects.order_by("pk")
            ]
        },
        status=200,
    )


list_entitlements.openapi = {"GET": {"operationId": "list_entitlements"}}


@api_view(("GET",), access="admin")
def list_devices(request):
    return JsonResponse(
        {
            "devices": [
                schemas.Device.model_validate(item).model_dump(mode="json")
                for item in Device.objects.order_by("pk")
            ]
        },
        status=200,
    )


list_devices.openapi = {"GET": {"operationId": "list_devices"}}


@api_view(("GET",), access="admin")
def get_account(request, pk):
    account = get_object_or_404(User, pk=pk)
    return JsonResponse(
        {"account": schemas.Account.model_validate(account).model_dump(mode="json")}, status=200
    )


get_account.openapi = {"GET": {"operationId": "get_account"}}


@api_view(("POST",), access="session")
def redeem_license_key(request):
    data = schemas.RedeemKey.from_request(request)
    entitlement, created = services.redeem(request.user, data.license_key)
    request.audit_context.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
    return JsonResponse(
        {"entitlement": schemas.Entitlement.model_validate(entitlement).model_dump(mode="json")},
        status=201 if created else 200,
    )


redeem_license_key.openapi = {"POST": {"operationId": "redeem_license_key", "body": schemas.RedeemKey}}


@api_view(("GET",), access="session")
def list_my_entitlements(request):
    return JsonResponse(
        {
            "entitlements": [
                schemas.Entitlement.model_validate(e).model_dump(mode="json")
                for e in request.user.entitlements.order_by("pk")
            ]
        },
        status=200,
    )


list_my_entitlements.openapi = {"GET": {"operationId": "list_my_entitlements"}}


@api_view(("GET",), access="session")
def get_my_entitlement(request, pk):
    entitlement = get_object_or_404(Entitlement, pk=pk, account=request.user)
    return JsonResponse(
        {"entitlement": schemas.Entitlement.model_validate(entitlement).model_dump(mode="json")}, status=200
    )


get_my_entitlement.openapi = {"GET": {"operationId": "get_my_entitlement"}}


@api_view(("GET", "POST"), access="session")
def my_devices(request, pk):
    if request.method == "GET":
        entitlement = get_object_or_404(Entitlement, pk=pk, account=request.user)
        return JsonResponse(
            {
                "devices": [
                    schemas.Device.model_validate(d).model_dump(mode="json")
                    for d in entitlement.devices.order_by("pk")
                ]
            },
            status=200,
        )

    data = schemas.BindDevice.from_request(request)
    entitlement = get_object_or_404(Entitlement, pk=pk, account=request.user)
    device, created = services.bind(entitlement, data.device_fingerprint, data.display_name)
    request.audit_context.update(
        product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk
    )
    return JsonResponse(
        {"device": schemas.Device.model_validate(device).model_dump(mode="json")},
        status=201 if created else 200,
    )


my_devices.openapi = {
    "GET": {"operationId": "list_my_devices"},
    "POST": {"operationId": "bind_my_device", "body": schemas.BindDevice},
}


@api_view(("POST",), access="session")
def unbind_my_device(request, pk):
    schemas.EmptyBody.from_request(request)
    device = get_object_or_404(Device, pk=pk, entitlement__account=request.user)
    device = services.unbind(device)
    request.audit_context.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return JsonResponse({"device": schemas.Device.model_validate(device).model_dump(mode="json")}, status=200)


unbind_my_device.openapi = {"POST": {"operationId": "unbind_my_device", "body": schemas.EmptyBody}}


@api_view(("PATCH",), access="session")
def set_my_device_display_name(request, pk):
    data = schemas.RenameDevice.from_request(request)
    device = get_object_or_404(Device, pk=pk, entitlement__account=request.user)
    services.rename_device(device, data.display_name)
    request.audit_context.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return JsonResponse({"device": schemas.Device.model_validate(device).model_dump(mode="json")}, status=200)


set_my_device_display_name.openapi = {
    "PATCH": {"operationId": "set_my_device_display_name", "body": schemas.RenameDevice}
}


@api_view(("POST",), access="application")
def activate_device(request):
    data = schemas.ActivateDevice.from_request(request)
    key, entitlement = services.resolve_redeemed_key(data.license_key)
    device, created = services.bind(
        entitlement, data.device_fingerprint, data.display_name, source_key_id=key.pk
    )
    request.audit_context.update(
        product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk
    )
    return JsonResponse(
        {"device": schemas.Device.model_validate(device).model_dump(mode="json")},
        status=201 if created else 200,
    )


activate_device.openapi = {"POST": {"operationId": "activate_device", "body": schemas.ActivateDevice}}


@api_view(("POST",), access="application")
def validate_device(request):
    data = schemas.ValidateDevice.from_request(request)
    device = services.validate(data.license_key, data.device_fingerprint)
    request.audit_context.update(entitlement_id=device.entitlement_id, device_id=device.pk)
    return JsonResponse(
        {"valid": True, "device": schemas.Device.model_validate(device).model_dump(mode="json")}, status=200
    )


validate_device.openapi = {"POST": {"operationId": "validate_device", "body": schemas.ValidateDevice}}

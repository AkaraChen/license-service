"""Response schemas derived from Django models. Handlers return ORM rows;
``openapi_gen.adapt`` wraps them. OpenAPI uses the same models."""

from typing import Literal

from django.contrib.auth.models import User

from openapi_gen.adapt import envelope
from openapi_gen.orm import entity

from .models import Device, Entitlement, LicenseKey, Product

ErrorBody = envelope("ErrorBody", error=str, message=str)

Account = entity(
    "Account",
    User,
    account_id="pk",
    username=True,
    is_admin="is_staff",
    email=str | None,
    created_at="date_joined",
)
Product = entity("Product", Product, product_id="pk", code=True, name=True, created_at=True)
LicenseKey = entity(
    "LicenseKey",
    LicenseKey,
    key_id="pk",
    product_id=True,
    key_prefix=True,
    max_devices=True,
    expires_at=True,
    status=True,
    redeemed_by_account_id="redeemed_by_id",
    created_at=True,
)
Entitlement = entity(
    "Entitlement",
    Entitlement,
    entitlement_id="pk",
    account_id=True,
    product_id=True,
    max_devices=True,
    expires_at=True,
    status=True,
    source_key_id=True,
    created_at=True,
)
Device = entity(
    "Device",
    Device,
    device_id="pk",
    entitlement_id=True,
    device_fingerprint=True,
    display_name=True,
    bound_at=True,
    status=True,
)

AccountResponse = envelope("AccountResponse", account=Account)
ProductResponse = envelope("ProductResponse", product=Product)
LicenseKeyResponse = envelope("LicenseKeyResponse", key=LicenseKey)
EntitlementResponse = envelope("EntitlementResponse", entitlement=Entitlement)
DeviceResponse = envelope("DeviceResponse", device=Device)
AccountList = envelope("AccountList", accounts=list[Account])
ProductList = envelope("ProductList", products=list[Product])
LicenseKeyList = envelope("LicenseKeyList", license_keys=list[LicenseKey])
EntitlementList = envelope("EntitlementList", entitlements=list[Entitlement])
DeviceList = envelope("DeviceList", devices=list[Device])
IssuedLicenseKey = envelope("IssuedLicenseKey", key=LicenseKey, license_key=str)
Ok = envelope("Ok", ok=(Literal[True], True))
ValidateResponse = envelope("ValidateResponse", valid=(Literal[True], True), device=Device)

RESPONSES = {
    "register": {201: AccountResponse},
    "login": {200: AccountResponse},
    "logout": {200: Ok},
    "create_product": {201: ProductResponse},
    "update_product": {200: ProductResponse},
    "issue_license_key": {201: IssuedLicenseKey},
    "revoke_license_key": {200: LicenseKeyResponse},
    "set_entitlement_status": {200: EntitlementResponse},
    "unbind_device": {200: DeviceResponse},
    "list_products": {200: ProductList},
    "list_license_keys": {200: LicenseKeyList},
    "list_accounts": {200: AccountList},
    "list_entitlements": {200: EntitlementList},
    "list_devices": {200: DeviceList},
    "get_product": {200: ProductResponse},
    "get_account": {200: AccountResponse},
    "redeem_license_key": {200: EntitlementResponse, 201: EntitlementResponse},
    "list_my_entitlements": {200: EntitlementList},
    "get_my_entitlement": {200: EntitlementResponse},
    "list_my_devices": {200: DeviceList},
    "bind_my_device": {200: DeviceResponse, 201: DeviceResponse},
    "unbind_my_device": {200: DeviceResponse},
    "set_my_device_display_name": {200: DeviceResponse},
    "activate_device": {200: DeviceResponse, 201: DeviceResponse},
    "validate_device": {200: ValidateResponse},
}

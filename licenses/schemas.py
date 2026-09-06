"""Pydantic response models. Handlers return these; OpenAPI is derived from them."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(Schema):
    error: str
    message: str


class Account(Schema):
    account_id: int
    username: str
    is_admin: bool
    email: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, user):
        return cls(
            account_id=user.pk,
            username=user.username,
            is_admin=user.is_staff,
            email=user.email or None,
            created_at=user.date_joined,
        )


class Product(Schema):
    product_id: int
    code: str
    name: str
    created_at: datetime

    @classmethod
    def from_row(cls, product):
        return cls(product_id=product.pk, code=product.code, name=product.name, created_at=product.created_at)


class LicenseKey(Schema):
    key_id: int
    product_id: int
    key_prefix: str
    max_devices: int
    expires_at: datetime | None
    status: Literal["issued", "redeemed", "revoked"]
    redeemed_by_account_id: int | None
    created_at: datetime

    @classmethod
    def from_row(cls, key):
        return cls(
            key_id=key.pk,
            product_id=key.product_id,
            key_prefix=key.key_prefix,
            max_devices=key.max_devices,
            expires_at=key.expires_at,
            status=key.status,
            redeemed_by_account_id=key.redeemed_by_id,
            created_at=key.created_at,
        )


class Entitlement(Schema):
    entitlement_id: int
    account_id: int
    product_id: int
    max_devices: int
    expires_at: datetime | None
    status: Literal["active", "suspended", "revoked"]
    source_key_id: int
    created_at: datetime

    @classmethod
    def from_row(cls, entitlement):
        return cls(
            entitlement_id=entitlement.pk,
            account_id=entitlement.account_id,
            product_id=entitlement.product_id,
            max_devices=entitlement.max_devices,
            expires_at=entitlement.expires_at,
            status=entitlement.status,
            source_key_id=entitlement.source_key_id,
            created_at=entitlement.created_at,
        )


class Device(Schema):
    device_id: int
    entitlement_id: int
    device_fingerprint: str
    display_name: str | None
    bound_at: datetime
    status: Literal["bound", "unbound"]

    @classmethod
    def from_row(cls, device):
        return cls(
            device_id=device.pk,
            entitlement_id=device.entitlement_id,
            device_fingerprint=device.device_fingerprint,
            display_name=device.display_name,
            bound_at=device.bound_at,
            status=device.status,
        )


class AccountResponse(Schema):
    account: Account

    @classmethod
    def from_row(cls, user):
        return cls(account=Account.from_row(user))


class ProductResponse(Schema):
    product: Product

    @classmethod
    def from_row(cls, product):
        return cls(product=Product.from_row(product))


class LicenseKeyResponse(Schema):
    key: LicenseKey

    @classmethod
    def from_row(cls, key):
        return cls(key=LicenseKey.from_row(key))


class EntitlementResponse(Schema):
    entitlement: Entitlement

    @classmethod
    def from_row(cls, entitlement):
        return cls(entitlement=Entitlement.from_row(entitlement))


class DeviceResponse(Schema):
    device: Device

    @classmethod
    def from_row(cls, device):
        return cls(device=Device.from_row(device))


class AccountList(Schema):
    accounts: list[Account]

    @classmethod
    def from_rows(cls, rows):
        return cls(accounts=[Account.from_row(row) for row in rows])


class ProductList(Schema):
    products: list[Product]

    @classmethod
    def from_rows(cls, rows):
        return cls(products=[Product.from_row(row) for row in rows])


class LicenseKeyList(Schema):
    license_keys: list[LicenseKey]

    @classmethod
    def from_rows(cls, rows):
        return cls(license_keys=[LicenseKey.from_row(row) for row in rows])


class EntitlementList(Schema):
    entitlements: list[Entitlement]

    @classmethod
    def from_rows(cls, rows):
        return cls(entitlements=[Entitlement.from_row(row) for row in rows])


class DeviceList(Schema):
    devices: list[Device]

    @classmethod
    def from_rows(cls, rows):
        return cls(devices=[Device.from_row(row) for row in rows])


class IssuedLicenseKey(Schema):
    key: LicenseKey
    license_key: str

    @classmethod
    def from_issue(cls, key, plaintext):
        return cls(key=LicenseKey.from_row(key), license_key=plaintext)


class Ok(Schema):
    ok: Literal[True] = True


class ValidateResponse(Schema):
    valid: Literal[True] = True
    device: Device

    @classmethod
    def from_row(cls, device):
        return cls(device=Device.from_row(device))


# Success status -> model for each Section 11 operation. Handlers return these
# models; OpenAPI is generated from the same table.
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

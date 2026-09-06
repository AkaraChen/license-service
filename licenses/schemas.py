"""Pydantic schemas for request bodies and response payloads.

Uses ApiBaseModel from apispec-pydantic-plugin so schemas automatically register
with APISpec for OpenAPI generation.
"""

from datetime import datetime
from typing import List, Optional

from apispec_pydantic_plugin.models import ApiBaseModel
from pydantic import ConfigDict, StrictInt, StrictStr


class StrictRequestModel(ApiBaseModel):
    """Base model for requests: forbids unknown fields (SPEC 5.2)."""

    model_config = ConfigDict(extra="forbid")


# --- Error Schemas ---


class Error(ApiBaseModel):
    error: str
    message: str


ErrorResponse = Error


# --- Domain Object Schemas ---


class AccountSchema(ApiBaseModel):
    account_id: int
    username: str
    is_admin: bool
    email: Optional[str] = None
    created_at: Optional[str] = None


class ProductSchema(ApiBaseModel):
    product_id: int
    code: str
    name: str
    created_at: Optional[str] = None


class LicenseKeySchema(ApiBaseModel):
    key_id: int
    product_id: int
    key_prefix: str
    max_devices: int
    expires_at: Optional[str] = None
    status: str
    redeemed_by_account_id: Optional[int] = None
    created_at: Optional[str] = None


class EntitlementSchema(ApiBaseModel):
    entitlement_id: int
    account_id: int
    product_id: int
    max_devices: int
    expires_at: Optional[str] = None
    status: str
    source_key_id: int
    created_at: Optional[str] = None


class DeviceSchema(ApiBaseModel):
    device_id: int
    entitlement_id: int
    device_fingerprint: str
    display_name: Optional[str] = None
    bound_at: Optional[str] = None
    status: str


# --- Request Schemas ---


class RegisterRequest(StrictRequestModel):
    username: StrictStr
    password: StrictStr


class LoginRequest(StrictRequestModel):
    username: StrictStr
    password: StrictStr


class CreateProductRequest(StrictRequestModel):
    code: StrictStr
    name: StrictStr


class UpdateProductRequest(StrictRequestModel):
    name: Optional[StrictStr] = None


class IssueLicenseKeyRequest(StrictRequestModel):
    product_id: StrictInt
    max_devices: StrictInt
    expires_at: Optional[datetime] = None


class SetEntitlementStatusRequest(StrictRequestModel):
    status: StrictStr


class RedeemKeyRequest(StrictRequestModel):
    license_key: StrictStr


class BindDeviceRequest(StrictRequestModel):
    device_fingerprint: StrictStr
    display_name: Optional[StrictStr] = None


class SetDeviceDisplayNameRequest(StrictRequestModel):
    display_name: Optional[StrictStr] = None


class ActivateDeviceRequest(StrictRequestModel):
    license_key: StrictStr
    device_fingerprint: StrictStr
    display_name: Optional[StrictStr] = None


class ValidateDeviceRequest(StrictRequestModel):
    license_key: StrictStr
    device_fingerprint: StrictStr


# --- Response Schemas ---


class OkResponse(ApiBaseModel):
    ok: bool = True


class AccountResponse(ApiBaseModel):
    account: AccountSchema


class ProductResponse(ApiBaseModel):
    product: ProductSchema


class ProductsListResponse(ApiBaseModel):
    products: List[ProductSchema]


class LicenseKeyResponse(ApiBaseModel):
    key: LicenseKeySchema


class IssueLicenseKeyResponse(ApiBaseModel):
    key: LicenseKeySchema
    license_key: str


class LicenseKeysListResponse(ApiBaseModel):
    license_keys: List[LicenseKeySchema]


class EntitlementResponse(ApiBaseModel):
    entitlement: EntitlementSchema


class EntitlementsListResponse(ApiBaseModel):
    entitlements: List[EntitlementSchema]


class DeviceResponse(ApiBaseModel):
    device: DeviceSchema


class DevicesListResponse(ApiBaseModel):
    devices: List[DeviceSchema]


class ValidateDeviceResponse(ApiBaseModel):
    valid: bool
    device: DeviceSchema


class AccountsListResponse(ApiBaseModel):
    accounts: List[AccountSchema]

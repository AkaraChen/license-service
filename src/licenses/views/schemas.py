"""Public input contracts and explicit response field allowlists."""

from datetime import datetime
from typing import Annotated, Literal

from django.core.validators import ProhibitNullCharactersValidator
from ninja import Schema
from pydantic import AfterValidator, BeforeValidator, ConfigDict, Field, TypeAdapter, field_validator

from ..models import Product as ProductModel

ProductCode = Annotated[str, AfterValidator(ProductModel._meta.get_field("code").formfield().clean)]
ProductName = Annotated[str, AfterValidator(ProductModel._meta.get_field("name").formfield().clean)]

Fingerprint = Annotated[str, BeforeValidator(str.strip), Field(min_length=1, max_length=128)]
_reject_null = ProhibitNullCharactersValidator()


class Empty(Schema):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def valid_text(cls, value):
        if isinstance(value, str):
            _reject_null(value)
        return value


class Credentials(Empty):
    username: str
    password: str


class ProductCreate(Empty):
    code: ProductCode
    name: ProductName


class ProductUpdate(Empty):
    name: ProductName = ""


class KeyIssue(Empty):
    product_id: int
    max_devices: int = Field(ge=1)
    expires_at: (
        Annotated[datetime, Field(strict=False), BeforeValidator(TypeAdapter(str).validate_python)] | None
    ) = None


class EntitlementStatus(Empty):
    status: Literal["active", "suspended", "revoked"]


class Redeem(Empty):
    license_key: str


class DeviceName(Empty):
    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None


class DeviceBind(Empty):
    device_fingerprint: Fingerprint
    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class Validate(Redeem):
    device_fingerprint: Fingerprint


class Activate(Validate):
    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class Product(Schema):
    product_id: int = Field(alias="pk")
    code: str
    name: str
    created_at: datetime


class Key(Schema):
    key_id: int = Field(alias="pk")
    product_id: int
    key_prefix: str
    max_devices: int
    expires_at: datetime | None
    status: str
    redeemed_by_account_id: int | None = Field(alias="redeemed_by_id")
    created_at: datetime


class Entitlement(Schema):
    entitlement_id: int = Field(alias="pk")
    account_id: int
    product_id: int
    max_devices: int
    expires_at: datetime | None
    status: str
    source_key_id: int
    created_at: datetime


class Device(Schema):
    device_id: int = Field(alias="pk")
    entitlement_id: int
    device_fingerprint: str
    display_name: str | None
    bound_at: datetime
    status: str


class Account(Schema):
    account_id: int = Field(alias="pk")
    username: str
    is_admin: bool = Field(alias="is_staff")
    email: str | None
    created_at: datetime = Field(alias="date_joined")

    @staticmethod
    def resolve_email(user):
        return user.email or None


class IssuedKey(Schema):
    key: Key
    license_key: str


class ValidatedDevice(Schema):
    valid: bool
    device: Device


class Error(Schema):
    error: str
    message: str


ERROR_RESPONSES = {code: Error for code in (400, 401, 403, 404, 409, 429, 503)}

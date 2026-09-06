"""API field contracts shared by Pydantic validation and OpenAPI."""

from datetime import datetime
from typing import Annotated, Literal, Self

from django.http import HttpRequest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_serializer,
    field_validator,
)

from .services import Failure, validate_text


class RequestBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    @classmethod
    def from_request(cls, request: HttpRequest) -> Self:
        try:
            return cls.model_validate_json(request.body or b"{}")
        except ValidationError as exc:
            # Never serialize Pydantic's input or context: they may contain passwords or keys.
            errors = exc.errors(include_input=False, include_context=False, include_url=False)
            first = errors[0]
            unknown = sorted(str(item["loc"][0]) for item in errors if item["type"] == "extra_forbidden")
            if unknown and all(name.isidentifier() for name in unknown):
                message = f"Unknown fields: {', '.join(unknown)}."
            elif first["type"] in {"json_invalid", "model_type"}:
                message = "Body must be a JSON object."
            elif first["loc"] and str(first["loc"][0]).isidentifier():
                field = first["loc"][0]
                message = (
                    f"Missing required field: {field}."
                    if first["type"] == "missing"
                    else f"Field {field} has an invalid value."
                )
            else:
                message = "The request body is invalid."
            raise Failure("validation_error", message) from None

    @field_validator("*")
    @classmethod
    def validate_strings(cls, value):
        # Preserve the service's Unicode/null-character boundary for every text field.
        if isinstance(value, str):
            validate_text(value)
        return value


class EmptyBody(RequestBody):
    pass


class Credentials(RequestBody):
    username: str
    password: str


class CreateProduct(RequestBody):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    name: str


class UpdateProduct(RequestBody):
    # model_fields_set distinguishes omission from an explicitly supplied empty name.
    name: str = ""


class IssueKey(RequestBody):
    product_id: int
    max_devices: int = Field(ge=1)
    expires_at: datetime | None = None


class SetEntitlementStatus(RequestBody):
    status: Literal["active", "suspended", "revoked"]


class RedeemKey(RequestBody):
    license_key: str


class BindDevice(RequestBody):
    device_fingerprint: str
    display_name: str | None = None


class RenameDevice(RequestBody):
    display_name: str | None


class ActivateDevice(RequestBody):
    license_key: str
    device_fingerprint: str
    display_name: str | None = None


class ValidateDevice(RequestBody):
    license_key: str
    device_fingerprint: str


class Resource(BaseModel):
    model_config = ConfigDict(from_attributes=True, hide_input_in_errors=True)

    @field_serializer("*", check_fields=False)
    def serialize_datetime(self, value):
        # Preserve the API's full precision and +00:00 spelling (rather than Z).
        return value.isoformat() if isinstance(value, datetime) else value


class Account(Resource):
    account_id: int = Field(validation_alias="pk")
    username: str
    is_admin: bool = Field(validation_alias="is_staff")
    email: str | None
    created_at: datetime = Field(validation_alias="date_joined")

    @field_validator("email")
    @classmethod
    def empty_email_is_null(cls, value):
        return value or None


class Product(Resource):
    product_id: int = Field(validation_alias="pk")
    code: str
    name: str
    created_at: datetime


class LicenseKey(Resource):
    key_id: int = Field(validation_alias="pk")
    product_id: int
    key_prefix: str
    max_devices: int
    expires_at: datetime | None
    status: str
    redeemed_by_account_id: int | None = Field(validation_alias="redeemed_by_id")
    created_at: datetime


class Entitlement(Resource):
    entitlement_id: int = Field(validation_alias="pk")
    account_id: int
    product_id: int
    max_devices: int
    expires_at: datetime | None
    status: str
    source_key_id: int
    created_at: datetime


class Device(Resource):
    device_id: int = Field(validation_alias="pk")
    entitlement_id: int
    device_fingerprint: str
    display_name: str | None
    bound_at: datetime
    status: str

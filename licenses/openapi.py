"""OpenAPI 3.1 document generated from OPERATIONS and Pydantic response models."""

from functools import cache

from django.http import JsonResponse

from openapi_gen import OpenAPIBuilder

from .api import HTTP_STATUS, OPERATIONS
from .schemas import ErrorBody


def _tags(name, auth):
    if name in {"activate_device", "validate_device"}:
        return ["Application"]
    if auth == "admin":
        return ["Admin"]
    return ["Customer"]


def _error_schema():
    schema = ErrorBody.model_json_schema(mode="serialization")
    schema.pop("$schema", None)
    schema.pop("$defs", None)
    schema["properties"]["error"] = {"type": "string", "enum": sorted(HTTP_STATUS)}
    schema["required"] = ["error", "message"]
    return schema


@cache
def build_openapi():
    builder = OpenAPIBuilder(
        title="License Service", version="3.0.0", description="Single-tenant license key service."
    )
    builder.add_tag("Admin", "Administrator session operations")
    builder.add_tag("Customer", "Customer session and registration")
    builder.add_tag("Application", "Licensed application calls (no Account session)")
    builder.cookie_auth("sessionCookie", "sessionid")
    builder.component_schema("Error", _error_schema())
    for name, method, op_path, auth, fields, _handler, responses in OPERATIONS:
        builder.add_operation(
            operation_id=name,
            method=method,
            path=f"/api/{op_path}",
            fields=fields,
            success=responses,
            security=[] if auth == "anonymous" else [{"sessionCookie": []}],
            errors=HTTP_STATUS,
            tags=_tags(name, auth),
            path_param_schema={"type": "integer"},
        )
    return builder.build()


def openapi_view(request):
    return JsonResponse(build_openapi())

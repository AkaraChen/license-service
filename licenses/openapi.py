"""OpenAPI document generated using APISpec and PydanticPlugin.

Automatically resolves schemas from Pydantic models for both requests and responses.
"""

from apispec import APISpec
from apispec_pydantic_plugin import PydanticPlugin
from django.http import JsonResponse

from .api import OPERATIONS
from .schemas import Error


def build_openapi() -> dict:
    spec = APISpec(
        title="License Service",
        version="3.0.0",
        openapi_version="3.1.0",
        info={"description": "Single-tenant license key service."},
        plugins=[PydanticPlugin()],
    )

    # Register Error schema under Error for standard error representation
    spec.components.schema("Error", model=Error)
    spec.components.security_scheme(
        "sessionCookie", {"type": "apiKey", "in": "cookie", "name": "sessionid"}
    )

    for op in OPERATIONS:
        path = f"/api/{op.op_path}"
        method = op.method.lower()

        success_code = "201" if (op.method == "POST" and "create" in op.name) or op.name in ("register", "issue_license_key") else "200"

        responses = {
            success_code: {
                "description": "success",
                "content": {
                    "application/json": {
                        "schema": op.resp_schema.__name__ if op.resp_schema else "Error"
                    }
                },
            },
            "default": {
                "description": "error",
                "content": {
                    "application/json": {
                        "schema": "Error"
                    }
                },
            },
        }

        operation_dict = {
            "operationId": op.name,
            "summary": op.name.replace("_", " "),
            "security": [] if op.auth == "anonymous" else [{"sessionCookie": []}],
            "responses": responses,
        }

        path_params = [seg[1:-1] for seg in op.op_path.split("/") if seg.startswith("{")]
        if path_params:
            operation_dict["parameters"] = [
                {"name": p, "in": "path", "required": True, "schema": {"type": "integer"}}
                for p in path_params
            ]

        if op.req_schema:
            operation_dict["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": op.req_schema.__name__
                    }
                },
            }

        spec.path(path=path, operations={method: operation_dict})

    return spec.to_dict()


def openapi_view(request):
    return JsonResponse(build_openapi())

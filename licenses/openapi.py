"""OpenAPI derived from explicit Django routes and Pydantic request models."""

from django.http import JsonResponse
from django.urls import URLPattern, get_resolver

from .api_http import HTTP_STATUS


def build_openapi():
    paths = {}
    for route in get_resolver().url_patterns:
        if not isinstance(route, URLPattern) or not hasattr(route.callback, "openapi"):
            continue
        view = route.callback
        url = "/" + str(route.pattern)
        for parameter in route.pattern.converters:
            url = url.replace(f"<int:{parameter}>", "{" + parameter + "}")
        operations = {}
        for method, metadata in view.openapi.items():
            name = metadata["operationId"]
            operation = {
                "operationId": name,
                "summary": name.replace("_", " "),
                "security": [] if view.access in {"anonymous", "application"} else [{"sessionCookie": []}],
                "responses": {
                    str(code): {
                        "description": error,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                    }
                    for error, code in HTTP_STATUS.items()
                },
            }
            operation["responses"]["200"] = {"description": "success"}
            if method == "POST":
                operation["responses"]["201"] = {"description": "created"}
            if route.pattern.converters:
                operation["parameters"] = [
                    {"name": parameter, "in": "path", "required": True, "schema": {"type": "integer"}}
                    for parameter in route.pattern.converters
                ]
            if body := metadata.get("body"):
                schema = body.model_json_schema()
                operation["requestBody"] = {
                    "required": bool(schema.get("required")),
                    "content": {"application/json": {"schema": schema}},
                }
            operations[method.lower()] = operation
        paths[url] = operations
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "License Service",
            "version": "3.0.0",
            "description": "Single-tenant license key service.",
        },
        "paths": paths,
        "components": {
            "schemas": {
                "Error": {
                    "type": "object",
                    "required": ["error", "message"],
                    "properties": {
                        "error": {"type": "string", "enum": sorted(HTTP_STATUS)},
                        "message": {"type": "string"},
                    },
                }
            },
            "securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie", "name": "sessionid"}},
        },
    }


def openapi_view(request):
    return JsonResponse(build_openapi())

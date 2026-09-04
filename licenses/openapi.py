"""OpenAPI document and human-readable API docs, both generated from the same
OPERATIONS registry that produces the running HTTP implementation (Section 12).
"""
from django.http import JsonResponse
from django.shortcuts import render

from .api import HTTP_STATUS, OPERATIONS

_KIND_SCHEMA = {"str": {"type": "string"}, "int": {"type": "integer"},
                "str?": {"type": ["string", "null"]}, "dt?": {"type": ["string", "null"], "format": "date-time"}}
_ERROR_SCHEMA = {"type": "object", "required": ["error", "message"],
                 "properties": {"error": {"type": "string", "enum": sorted(HTTP_STATUS)},
                                "message": {"type": "string"}}}
_AUTH_TEXT = {"anonymous": "none", "session": "session cookie", "admin": "admin session cookie"}

def build_openapi():
    paths = {}
    for name, method, op_path, auth, fields, _ in OPERATIONS:
        spec = {"operationId": name, "summary": name.replace("_", " "),
                "security": [] if auth == "anonymous" else [{"sessionCookie": []}],
                "responses": {str(code): {"description": cls, "content": {"application/json":
                              {"schema": {"$ref": "#/components/schemas/Error"}}}}
                              for cls, code in HTTP_STATUS.items()}}
        spec["responses"]["200" if method == "GET" else "200/201"] = {"description": "success"}
        params = [seg[1:-1] for seg in op_path.split("/") if seg.startswith("{")]
        if params:
            spec["parameters"] = [{"name": p, "in": "path", "required": True,
                                   "schema": {"type": "integer"}} for p in params]
        if fields:
            spec["requestBody"] = {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "additionalProperties": False,
                "required": [n for n, _, req in fields if req],
                "properties": {n: _KIND_SCHEMA[kind] for n, kind, _ in fields}}}}}
        paths.setdefault(f"/api/{op_path}", {})[method.lower()] = spec
    return {"openapi": "3.1.0",
            "info": {"title": "License Service", "version": "3.0.0",
                     "description": "Single-tenant license key service. See /docs for the profile."},
            "paths": paths,
            "components": {"schemas": {"Error": _ERROR_SCHEMA},
                           "securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie",
                                                                 "name": "sessionid"}}}}

def openapi_view(request):
    return JsonResponse(build_openapi())

def docs_view(request):
    """Human-readable API documentation (Section 5.1.6), rendered from the same
    registry so it cannot contradict the OpenAPI document."""
    rows = [{"name": name, "method": method, "path": f"/api/{op_path}", "auth": _AUTH_TEXT[auth],
             "fields": [(n, kind, req) for n, kind, req in fields]}
            for name, method, op_path, auth, fields, _ in OPERATIONS]
    return render(request, "licenses/docs.html", {"operations": rows, "errors": sorted(HTTP_STATUS.items())})

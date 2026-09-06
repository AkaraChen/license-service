"""Assemble a typed, spec-validated OpenAPI 3.1 document."""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from .errors import OpenAPIBuildError
from .fields import merge_error_statuses, normalize_method, path_param_names, request_body_schema, status_key
from .validate import validate_openapi

_JSON = "application/json"
_META_KEYS = ("$schema", "$id")


def pydantic_schemas(model: type[BaseModel]) -> dict[str, dict]:
    """Flatten a Pydantic model (and its nested $defs) into component schemas."""
    raw = model.model_json_schema(mode="serialization", ref_template="#/components/schemas/{model}")
    defs = raw.pop("$defs", {})
    for key in _META_KEYS:
        raw.pop(key, None)
    schemas = {model.__name__: raw}
    for name, sub in defs.items():
        cleaned = dict(sub)
        for key in _META_KEYS:
            cleaned.pop(key, None)
        schemas[name] = cleaned
    return schemas


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_content(schema: dict) -> dict:
    return {_JSON: {"schema": schema}}


class OpenAPIBuilder:
    """Collect operations and component schemas, then emit a validated document."""

    def __init__(self, title: str, version: str, description: str = "", openapi: str = "3.1.1"):
        if openapi not in {"3.1.0", "3.1.1"}:
            raise OpenAPIBuildError(f"Unsupported OpenAPI version {openapi!r}; use 3.1.0 or 3.1.1")
        self.title = title
        self.version = version
        self.description = description
        self.openapi = openapi
        self._schemas: dict[str, dict] = {}
        self._security_schemes: dict[str, dict] = {}
        self._paths: dict[str, dict] = {}
        self._operation_ids: set[str] = set()
        self._tags: dict[str, str] = {}

    def add_tag(self, name: str, description: str = "") -> None:
        self._tags.setdefault(name, description)

    def cookie_auth(self, scheme_name: str, cookie: str) -> None:
        self._security_schemes[scheme_name] = {"type": "apiKey", "in": "cookie", "name": cookie}

    def component_schema(self, name: str, schema: dict) -> None:
        existing = self._schemas.get(name)
        if existing is not None and existing != schema:
            raise OpenAPIBuildError(f"Component schema {name!r} already exists with a different definition")
        self._schemas[name] = schema

    def component_model(self, model: type[BaseModel]) -> None:
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise OpenAPIBuildError(f"component_model expected a Pydantic model, got {model!r}")
        for name, schema in pydantic_schemas(model).items():
            self.component_schema(name, schema)

    def add_operation(
        self,
        *,
        operation_id: str,
        method: str,
        path: str,
        fields: Sequence[tuple[str, str, bool]] = (),
        success: Mapping[int | str, type[BaseModel]],
        security: list | None = None,
        errors: Mapping[str, int] | None = None,
        tags: Sequence[str] = (),
        path_param_schema: dict | None = None,
        summary: str | None = None,
    ) -> None:
        if not operation_id:
            raise OpenAPIBuildError("operationId is required")
        if operation_id in self._operation_ids:
            raise OpenAPIBuildError(f"Duplicate operationId {operation_id!r}")
        method = normalize_method(method)
        params = path_param_names(path)
        if not success:
            raise OpenAPIBuildError(f"{operation_id} must declare at least one success response")

        spec: dict[str, Any] = {
            "operationId": operation_id,
            "summary": summary if summary is not None else operation_id.replace("_", " "),
            "responses": {},
        }
        if tags:
            spec["tags"] = list(tags)
            for tag in tags:
                self.add_tag(tag)
        if security is not None:
            spec["security"] = security
        if params:
            schema = dict(path_param_schema or {"type": "string"})
            spec["parameters"] = [
                {"name": name, "in": "path", "required": True, "schema": schema} for name in params
            ]
        if fields:
            spec["requestBody"] = {"required": True, "content": _json_content(request_body_schema(fields))}
        for status, model in success.items():
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise OpenAPIBuildError(f"{operation_id} success {status} must be a Pydantic model")
            self.component_model(model)
            spec["responses"][status_key(status)] = {
                "description": model.__name__,
                "content": _json_content(_ref(model.__name__)),
            }
        if errors:
            for code, description in merge_error_statuses(dict(errors)).items():
                spec["responses"][code] = {
                    "description": description,
                    "content": _json_content(_ref("Error")),
                }

        item = self._paths.setdefault(path, {})
        if method in item:
            raise OpenAPIBuildError(f"Duplicate operation {method.upper()} {path}")
        item[method] = spec
        self._operation_ids.add(operation_id)

    def build(self) -> dict:
        info = {"title": self.title, "version": self.version}
        if self.description:
            info["description"] = self.description
        components: dict[str, Any] = {}
        if self._schemas:
            components["schemas"] = self._schemas
        if self._security_schemes:
            components["securitySchemes"] = self._security_schemes
        document: dict[str, Any] = {"openapi": self.openapi, "info": info, "paths": self._paths}
        if components:
            document["components"] = components
        if self._tags:
            document["tags"] = [
                {"name": name, **({"description": desc} if desc else {})} for name, desc in self._tags.items()
            ]
        return validate_openapi(document)

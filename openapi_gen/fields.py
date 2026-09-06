"""Request-field kinds and OpenAPI 3.1 lexical constraints."""

import re
from typing import Literal

from .errors import OpenAPIBuildError

FieldKind = Literal["str", "int", "str?", "dt?"]

KIND_SCHEMAS: dict[str, dict] = {
    "str": {"type": "string"},
    "int": {"type": "integer"},
    "str?": {"type": ["string", "null"]},
    "dt?": {"type": ["string", "null"], "format": "date-time"},
}

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
# OAS 3.1 Responses Object: default, an HTTP code, or a 1XX-5XX range.
STATUS_RE = re.compile(r"^(default|[1-5](?:XX|[0-9]{2}))$")
PATH_PARAM_RE = re.compile(r"\{([^{}]+)\}")


def kind_schema(kind: str) -> dict:
    try:
        return dict(KIND_SCHEMAS[kind])
    except KeyError:
        raise OpenAPIBuildError(
            f"Unknown field kind {kind!r}; expected one of {sorted(KIND_SCHEMAS)}"
        ) from None


def status_key(status: int | str) -> str:
    key = str(status)
    if not STATUS_RE.fullmatch(key):
        raise OpenAPIBuildError(
            f"Invalid OpenAPI response status {key!r}; use an HTTP code, 1XX-5XX, or default"
        )
    return key


def normalize_method(method: str) -> str:
    lowered = method.lower()
    if lowered not in HTTP_METHODS:
        raise OpenAPIBuildError(f"Invalid HTTP method {method!r}")
    return lowered


def path_param_names(path: str) -> list[str]:
    if not path.startswith("/"):
        raise OpenAPIBuildError(f"Path must start with '/': {path!r}")
    if path.count("{") != path.count("}"):
        raise OpenAPIBuildError(f"Unbalanced path template: {path!r}")
    names = PATH_PARAM_RE.findall(path)
    if any(not name.strip() for name in names):
        raise OpenAPIBuildError(f"Empty path parameter in {path!r}")
    return names


def request_body_schema(fields: list[tuple[str, str, bool]] | tuple) -> dict:
    properties = {name: kind_schema(kind) for name, kind, _ in fields}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [name for name, _, required in fields if required],
        "properties": properties,
    }


def merge_error_statuses(error_classes: dict[str, int]) -> dict[str, str]:
    """Map each HTTP status to a description listing the error classes that use it."""
    grouped: dict[int, list[str]] = {}
    for cls, code in error_classes.items():
        grouped.setdefault(int(code), []).append(cls)
    return {status_key(code): ", ".join(sorted(names)) for code, names in grouped.items()}

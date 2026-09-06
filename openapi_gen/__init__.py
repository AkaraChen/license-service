"""Build OpenAPI 3.1 documents that validate against the official specification.

The builder accepts operations (path, method, request field tuples, Pydantic
response models). ``OpenAPIBuilder.build`` type-checks with ``openapi-pydantic``
and validates with ``openapi-spec-validator``, so invalid constructs such as
status ``200/201`` cannot be emitted.
"""

from .builder import OpenAPIBuilder
from .errors import OpenAPIBuildError
from .fields import FieldKind, kind_schema, status_key
from .validate import validate_openapi

__all__ = [
    "FieldKind",
    "OpenAPIBuildError",
    "OpenAPIBuilder",
    "kind_schema",
    "status_key",
    "validate_openapi",
]

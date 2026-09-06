from openapi_pydantic import OpenAPI
from openapi_spec_validator import validate
from pydantic import ValidationError

from .errors import OpenAPIBuildError


def dump_openapi(document: OpenAPI) -> dict:
    """Serialize with the aliases and omissions the OpenAPI 3.1 mapping requires."""
    return document.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)


def validate_openapi(document: dict) -> dict:
    """Type-check with openapi-pydantic, then validate against the official OAS 3.1 schema."""
    try:
        typed = OpenAPI.model_validate(document)
    except ValidationError as exc:
        raise OpenAPIBuildError(f"Document failed OpenAPI 3.1 type check: {exc}") from exc
    dumped = dump_openapi(typed)
    try:
        validate(dumped)
    except Exception as exc:
        raise OpenAPIBuildError(f"Document failed official OpenAPI 3.1 validation: {exc}") from exc
    return dumped

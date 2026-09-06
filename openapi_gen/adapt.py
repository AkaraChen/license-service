"""Coerce handler return values into a Pydantic response model."""

from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, create_model, field_validator


class Schema(BaseModel):
    """Response model: ORM-friendly, unknown fields forbidden, blank strings → null."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any, info):
        if value != "":
            return value
        annotation = cls.model_fields[info.field_name].annotation
        return None if _allows_none(annotation) else value


def _allows_none(annotation) -> bool:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return type(None) in get_args(annotation)
    return annotation is type(None)


def envelope(name: str, **fields):
    """Build a wrapper model. Values are a type, or ``(type, default)``."""
    defs = {}
    for key, spec in fields.items():
        defs[key] = spec if isinstance(spec, tuple) else (spec, ...)
    return create_model(name, __base__=Schema, **defs)


def adapt(model: type[BaseModel], payload: Any) -> BaseModel:
    """Turn a handler return value into ``model``.

    * already a ``model`` instance → unchanged
    * ``None`` → ``model()`` (all-default envelopes such as ``Ok``)
    * ``dict`` → ``model.model_validate(dict)`` (nested ORM values allowed)
    * otherwise wrap in the single required field (object, queryset, or list)
    """
    if isinstance(payload, model):
        return payload
    if payload is None:
        return model()
    if isinstance(payload, dict):
        return model.model_validate(payload)
    required = [name for name, field in model.model_fields.items() if field.is_required()]
    if len(required) == 1:
        return model.model_validate({required[0]: payload})
    raise TypeError(f"Cannot adapt {type(payload).__name__} to {model.__name__}; return a dict or ORM object")


def dump_model(model: type[BaseModel], payload: Any) -> dict:
    return adapt(model, payload).model_dump(mode="json")

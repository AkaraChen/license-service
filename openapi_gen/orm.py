"""Derive Pydantic field types from a Django model."""

from datetime import datetime
from typing import Any, Literal

from django.db import models
from pydantic import AliasChoices, Field, create_model

from .adapt import Schema


def entity(schema_name: str, model: type[models.Model], /, **fields):
    """Pydantic schema from a Django model. Types and enums come from the ORM.

    Each keyword is a public API field:
    - ``True`` — same-named Django attribute
    - ``"attr"`` — Django attribute / ``pk``
    - a type — same-named attribute with this annotation
    - ``("attr", type)`` — both
    """
    defs: dict[str, Any] = {}
    for api_name, spec in fields.items():
        attr, annotation = _resolve(model, api_name, spec)
        if attr == api_name:
            defs[api_name] = (annotation, ...)
        else:
            defs[api_name] = (annotation, Field(validation_alias=AliasChoices(api_name, attr)))
    return create_model(schema_name, __base__=Schema, **defs)


def _resolve(model: type[models.Model], api_name: str, spec):
    if spec is True:
        return api_name, annotation_for(model, api_name)
    if isinstance(spec, str):
        return spec, annotation_for(model, spec)
    if isinstance(spec, tuple):
        attr, annotation = spec
        return attr, annotation
    return api_name, spec


def annotation_for(model: type[models.Model], attr: str):
    if attr == "pk":
        return int
    field = model._meta.get_field(attr)
    if field.choices:
        values = tuple(choice[0] for choice in field.choices)
        typ: Any = Literal[*values]
    elif isinstance(field, models.BooleanField):
        typ = bool
    elif isinstance(field, models.DateTimeField):
        typ = datetime
    elif isinstance(field, (models.IntegerField, models.AutoField, models.ForeignKey)):
        typ = int
    elif isinstance(field, (models.CharField, models.TextField)):
        typ = str
    else:
        typ = str
    return typ | None if field.null else typ

"""openapi_gen rejects illegal OpenAPI and emits documents the official schema accepts."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field

from openapi_gen import OpenAPIBuilder, OpenAPIBuildError, Schema, adapt, status_key, validate_openapi


class Ping(BaseModel):
    pong: bool


def _minimal(**overrides):
    builder = OpenAPIBuilder(title="T", version="1.0.0")
    kwargs = {"operation_id": "ping", "method": "GET", "path": "/ping", "success": {200: Ping}}
    kwargs.update(overrides)
    builder.add_operation(**kwargs)
    return builder


def test_status_key_rejects_handwritten_200_201():
    with pytest.raises(OpenAPIBuildError, match="200/201"):
        status_key("200/201")


def test_builder_rejects_invalid_status_on_success():
    with pytest.raises(OpenAPIBuildError, match="200/201"):
        _minimal(success={"200/201": Ping})


def test_builder_rejects_unknown_field_kind():
    with pytest.raises(OpenAPIBuildError, match="Unknown field kind"):
        _minimal(method="POST", fields=(("name", "float", True),))


def test_builder_rejects_unbalanced_path():
    with pytest.raises(OpenAPIBuildError, match="Unbalanced"):
        _minimal(path="/items/{id")


def test_builder_rejects_duplicate_operation_id():
    builder = _minimal()
    with pytest.raises(OpenAPIBuildError, match="Duplicate operationId"):
        builder.add_operation(operation_id="ping", method="POST", path="/ping2", success={200: Ping})


def test_build_passes_official_openapi_31_schema():
    document = _minimal(
        method="POST",
        path="/items/{id}",
        fields=(("name", "str", True), ("note", "str?", False)),
        path_param_schema={"type": "integer"},
    ).build()
    validate_openapi(document)
    assert document["openapi"] in {"3.1.0", "3.1.1"}
    assert "200/201" not in document["paths"]["/items/{id}"]["post"]["responses"]
    body = document["paths"]["/items/{id}"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["additionalProperties"] is False
    assert set(body["properties"]) == {"name", "note"}
    assert document["paths"]["/items/{id}"]["post"]["parameters"][0]["required"] is True
    assert "Ping" in document["components"]["schemas"]


class _Row(Schema):
    row_id: int = Field(validation_alias="pk")
    name: str


class _RowOut(Schema):
    item: _Row
    ok: bool = True


def test_adapt_wraps_orm_like_object_from_model_attributes():
    row = SimpleNamespace(pk=7, name="demo")
    dumped = adapt(_RowOut, row).model_dump()
    assert dumped == {"item": {"row_id": 7, "name": "demo"}, "ok": True}


def test_adapt_wraps_list_in_the_required_field():
    class _List(Schema):
        items: list[_Row]

    rows = [SimpleNamespace(pk=1, name="a"), SimpleNamespace(pk=2, name="b")]
    dumped = adapt(_List, rows).model_dump()
    assert dumped == {"items": [{"row_id": 1, "name": "a"}, {"row_id": 2, "name": "b"}]}


def test_adapt_accepts_dict_for_multi_field_models():
    class _Issued(Schema):
        item: _Row
        token: str

    dumped = adapt(_Issued, {"item": SimpleNamespace(pk=1, name="k"), "token": "lic_x"}).model_dump()
    assert dumped == {"item": {"row_id": 1, "name": "k"}, "token": "lic_x"}

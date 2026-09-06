"""SPEC 17.7: observability and OpenAPI (Sections 12 and 13)."""

import json
import logging
import re

from openapi_spec_validator import validate

from licenses.api import OPERATIONS
from licenses.openapi import build_openapi

from .conftest import ALICE_PW

_OAS_STATUS = re.compile(r"^(default|[1-5](?:XX|[0-9]{2}))$")

EXPECTED_OPERATIONS = {
    "create_product",
    "update_product",
    "list_products",
    "get_product",
    "issue_license_key",
    "revoke_license_key",
    "list_license_keys",
    "list_accounts",
    "get_account",
    "list_entitlements",
    "set_entitlement_status",
    "list_devices",
    "unbind_device",
    "register",
    "login",
    "logout",
    "redeem_license_key",
    "list_my_entitlements",
    "get_my_entitlement",
    "list_my_devices",
    "bind_my_device",
    "unbind_my_device",
    "set_my_device_display_name",
    "activate_device",
    "validate_device",
}


def test_openapi_served_and_lists_every_operation(api):
    response = api.client.get("/openapi.json")  # served by the same process
    assert response.status_code == 200
    document = json.loads(response.content)
    served = {
        spec["operationId"]
        for path in document["paths"].values()
        for key, spec in path.items()
        if key in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    }
    assert served == EXPECTED_OPERATIONS
    assert served == {name for name, *_ in OPERATIONS}  # generated from the registry
    from licenses.schemas import RESPONSES

    assert set(RESPONSES) == served


def test_openapi_is_valid_openapi_31_and_uses_pydantic_responses(api):
    document = json.loads(api.client.get("/openapi.json").content)
    assert document == build_openapi()
    validate(document)  # official OpenAPI 3.1 schema
    for path_item in document["paths"].values():
        for key, spec in path_item.items():
            if key not in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}:
                continue
            for status in spec["responses"]:
                assert _OAS_STATUS.fullmatch(status), status
            success = [spec["responses"][code] for code in spec["responses"] if code.startswith("2")]
            assert success
            for response in success:
                assert "$ref" in response["content"]["application/json"]["schema"]
    assert "200/201" not in json.dumps(document)
    components = document["components"]["schemas"]
    for name in ("Account", "Product", "LicenseKey", "Entitlement", "Device", "Error", "ValidateResponse"):
        assert name in components


def test_openapi_describes_error_envelope_and_write_fields(api):
    document = json.loads(api.client.get("/openapi.json").content)
    error = document["components"]["schemas"]["Error"]
    assert error["required"] == ["error", "message"]
    # Section 12: a generated client can call these without undocumented fields.
    expected_fields = {
        "/api/auth/register": {"username", "password"},
        "/api/auth/login": {"username", "password"},
        "/api/me/redeem": {"license_key"},
        "/api/activate": {"license_key", "device_fingerprint", "display_name"},
        "/api/validate": {"license_key", "device_fingerprint"},
    }
    for path, fields in expected_fields.items():
        spec = next(spec for key, spec in document["paths"][path].items() if key in {"get", "post", "patch"})
        schema = spec["requestBody"]["content"]["application/json"]["schema"]
        assert set(schema["properties"]) == fields
        assert schema["additionalProperties"] is False
    validate_op = document["paths"]["/api/validate"]["post"]
    assert validate_op["security"] == []  # no session cookie for application calls


def test_mutating_calls_log_actor_and_outcome(api, customer_api, redeemed, caplog):
    _, plaintext = redeemed
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        customer_api.post("me/redeem", {"license_key": plaintext})  # idempotent re-redeem
        api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "ghost"})
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "op=redeem_license_key" in m and "actor=customer" in m and "outcome=success" in m for m in messages
    )
    assert any(
        "op=activate_device" in m and "actor=application" in m and "outcome=success" in m for m in messages
    )
    assert any("op=validate_device" in m and "outcome=unknown_device" in m for m in messages)
    assert any("rid=" in m for m in messages)


def test_logs_never_contain_secrets_or_raw_fingerprints(
    api, admin_api, customer_api, product, redeemed, caplog
):
    entitlement, plaintext = redeemed
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        admin_api.post("license-keys", {"product_id": product.pk, "max_devices": 1})
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "secret-fingerprint-1"}
        )
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "secret-fingerprint-1"})
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert plaintext not in blob
    assert ALICE_PW not in blob
    assert "secret-fingerprint-1" not in blob
    assert "key_hash" not in blob

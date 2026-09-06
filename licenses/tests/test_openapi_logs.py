"""SPEC 17.7: observability and OpenAPI (Sections 12 and 13)."""

import json
import logging

from licenses.api import OPERATIONS

from .conftest import ALICE_PW

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
    served = {spec["operationId"] for path in document["paths"].values() for spec in path.values()}
    assert served == EXPECTED_OPERATIONS
    assert served == {name for name, *_ in OPERATIONS}  # generated, not handwritten


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
        spec = next(iter(document["paths"][path].values()))
        schema = spec["requestBody"]["content"]["application/json"]["schema"]
        assert set(schema["properties"]) == fields
        assert schema["additionalProperties"] is False
    validate = document["paths"]["/api/validate"]["post"]
    assert validate["security"] == []  # no session cookie for application calls


def test_mutating_calls_log_actor_and_outcome(api, customer_api, redeemed, caplog):
    _, plaintext = redeemed
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        customer_api.post("me/redeem", {"license_key": plaintext})  # idempotent re-redeem
        api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "ghost"})
    messages = [json.loads(r.getMessage()) for r in caplog.records if r.name == "licenses.api"]
    assert any(
        m["op"] == "redeem_license_key" and m["actor"] == "customer" and m["outcome"] == "success"
        for m in messages
    )
    assert any(
        m["op"] == "activate_device" and m["actor"] == "application" and m["outcome"] == "success"
        for m in messages
    )
    assert any(m["op"] == "validate_device" and m["outcome"] == "unknown_device" for m in messages)
    assert any("rid" in m for m in messages)


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

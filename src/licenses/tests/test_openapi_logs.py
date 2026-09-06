"""SPEC 17.7: observability and OpenAPI (Sections 12 and 13)."""

import json
import logging

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


def test_mutating_calls_log_events(api, customer_api, redeemed, caplog):
    _, plaintext = redeemed
    with caplog.at_level(logging.INFO):
        customer_api.post("me/redeem", {"license_key": plaintext})
        api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "ghost"})
    events = [
        json.loads(r.getMessage())["event"]
        for r in caplog.records
        if r.name.startswith("licenses.") and r.getMessage().startswith("{")
    ]
    assert "redeem" in events
    assert "activate" in events
    assert "api_error" in events


def test_logs_never_contain_secrets_or_raw_fingerprints(
    api, admin_api, customer_api, product, redeemed, caplog
):
    entitlement, plaintext = redeemed
    with caplog.at_level(logging.INFO):
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

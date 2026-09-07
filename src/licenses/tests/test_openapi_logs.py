"""SPEC 17.7: observability and OpenAPI (Sections 12 and 13)."""

import io
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
    events = [r.getMessage() for r in caplog.records if r.name.startswith("licenses.")]
    assert "redeem" in events
    assert "activate" in events
    assert "api_error" in events


def test_request_id_copied_from_header_only(api, caplog, monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(logging.getLogger("licenses").handlers[0], "stream", output)
    with caplog.at_level(logging.INFO):
        api.client.generic(
            "POST",
            "/api/auth/login",
            data=json.dumps({"username": "missing", "password": "secret"}),
            content_type="application/json",
            headers={"X-Request-ID": "client-rid-1", "X-CSRFToken": api.client.cookies["csrftoken"].value},
        )
        api.post("auth/login", {"username": "missing", "password": "secret"})
    records = [r for r in caplog.records if r.name.startswith("licenses.") and r.getMessage() == "api_error"]
    assert any(getattr(r, "request_id", None) == "client-rid-1" for r in records)
    assert any(not getattr(r, "request_id", None) for r in records)
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    lines = [line for line in lines if line["message"] == "api_error"]
    assert [line["request_id"] for line in lines] == ["client-rid-1", None]
    assert all(line["outcome"] == "unauthenticated" for line in lines)


def test_logs_never_contain_secrets_or_raw_fingerprints(
    api, admin_api, customer_api, product, redeemed, caplog, monkeypatch
):
    output = io.StringIO()
    monkeypatch.setattr(logging.getLogger("licenses").handlers[0], "stream", output)
    entitlement, plaintext = redeemed
    with caplog.at_level(logging.INFO):
        admin_api.post("license-keys", {"product_id": product.pk, "max_devices": 1})
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "secret-fingerprint-1"}
        )
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "secret-fingerprint-1"})
    blob = output.getvalue()
    assert plaintext not in blob
    assert ALICE_PW not in blob
    assert "secret-fingerprint-1" not in blob
    assert "key_hash" not in blob

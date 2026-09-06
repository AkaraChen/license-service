"""SPEC 17.2: parsing and API contract; 5.2 parsing rules; 5.3 envelope/status."""

import json

from django.contrib.auth.models import User

from licenses.models import Device
from licenses.views.http import HTTP_STATUS

from .conftest import error_class


def test_unknown_json_field_rejected_without_mutation(api):
    response = api.post("auth/register", {"username": "mallory", "password": "x" * 8, "is_admin": True})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"
    assert not User.objects.filter(username="mallory").exists()


def test_max_devices_below_one(admin_api, product):
    response = admin_api.post("license-keys", {"product_id": product.pk, "max_devices": 0})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"


def test_empty_fingerprint_rejected(customer_api, redeemed):
    entitlement, _ = redeemed
    response = customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "   "})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"
    assert Device.objects.count() == 0


def test_oversized_fingerprint_rejected(customer_api, redeemed):
    entitlement, _ = redeemed
    response = customer_api.post(
        f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "x" * 129}
    )
    assert response.status_code == 400
    assert error_class(response) == "validation_error"


def test_non_json_content_type_rejected(api):
    response = api.call(
        "POST", "auth/register", "username=alice&password=x", content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 400
    assert error_class(response) == "validation_error"


def test_error_envelope_shape_and_status_mapping(api, admin_api, product):
    response = api.post("auth/login", {"username": "ghost", "password": "nope"})
    body = json.loads(response.content)
    assert set(body) == {"error", "message"}
    assert body["error"] in HTTP_STATUS
    assert isinstance(body["message"], str) and body["message"]
    assert response.status_code == HTTP_STATUS[body["error"]] == 401

    response = admin_api.get("products/9999")
    assert response.status_code == 404
    assert error_class(response) == "not_found"


def test_activate_and_validate_need_no_session(api, redeemed):
    _, plaintext = redeemed
    bound = api.post("activate", {"license_key": plaintext, "device_fingerprint": "machine-1"})
    assert bound.status_code == 201  # fresh client: no session cookie at all
    ok = api.post("validate", {"license_key": plaintext, "device_fingerprint": "machine-1"})
    assert ok.status_code == 200
    assert api.json(ok)["valid"] is True


def test_session_cookie_required_for_customer_and_admin_ops(api):
    for method, path in [
        ("GET", "products"),
        ("GET", "license-keys"),
        ("GET", "accounts"),
        ("GET", "entitlements"),
        ("GET", "devices"),
        ("POST", "me/redeem"),
        ("GET", "me/entitlements"),
        ("POST", "auth/logout"),
    ]:
        response = api.call(method, path, {} if method != "GET" else "__skip__")
        assert response.status_code == 401, (method, path)
        assert error_class(response) == "unauthenticated"


def test_empty_list_operations_return_empty_collections(admin_api, customer_api):
    for path in ("products", "license-keys", "accounts", "entitlements", "devices"):
        body = admin_api.json(admin_api.get(path))
        assert isinstance(next(iter(body.values())), list)
    assert admin_api.json(admin_api.get("products"))["products"] == []
    assert customer_api.json(customer_api.get("me/entitlements"))["entitlements"] == []

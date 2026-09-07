"""SPEC 17.2: parsing and API contract; 5.2 parsing rules; 5.3 envelope/status."""

import json

import pytest
from django.contrib.auth.models import User

from licenses.models import Device

from .conftest import error_class


@pytest.mark.parametrize(
    "fields",
    [
        {"is_admin": True},
        {"is_staff": True},
        {"username": ""},
        {"username": "x" * 151},
        {"username": "bad/name"},
        {"password": ""},
    ],
)
def test_invalid_registration_rejected_without_mutation(api, fields):
    response = api.post("auth/register", {"username": "mallory", "password": "x" * 8, **fields})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"
    assert not User.objects.exists()


def test_max_devices_below_one(admin_api, product):
    response = admin_api.post("license-keys", {"product_id": product.pk, "max_devices": 0})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"


@pytest.mark.parametrize("fingerprint", ["   ", "x" * 129])
def test_invalid_fingerprint_rejected(customer_api, redeemed, fingerprint):
    entitlement, _ = redeemed
    response = customer_api.post(
        f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": fingerprint}
    )
    assert response.status_code == 400
    assert error_class(response) == "validation_error"
    assert Device.objects.count() == 0


def test_empty_display_name_rejected_at_http_boundary(api, customer_api, redeemed):
    entitlement, key = redeemed
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1", "display_name": ""}
        ).status_code
        == 400
    )
    assert (
        api.post("activate", {"license_key": key, "device_fingerprint": "m1", "display_name": ""}).status_code
        == 400
    )
    assert Device.objects.count() == 0
    device = customer_api.json(
        customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"})
    )["device"]
    assert customer_api.patch(f"me/devices/{device['device_id']}", {"display_name": ""}).status_code == 400
    assert (
        customer_api.client.post(
            f"/ui/devices/{device['device_id']}/rename",
            {"display_name": ""},
            HTTP_X_CSRFTOKEN=customer_api.client.cookies["csrftoken"].value,
        ).status_code
        == 400
    )


def test_error_envelope_shape_and_status_mapping(api, admin_api, product):
    response = api.post("auth/login", {"username": "ghost", "password": "nope"})
    body = json.loads(response.content)
    assert set(body) == {"error", "message"}
    assert body["error"] == "unauthenticated"
    assert isinstance(body["message"], str) and body["message"]
    assert response.status_code == 401

    response = admin_api.get("products/9999")
    assert response.status_code == 404
    assert error_class(response) == "not_found"


def test_activate_and_validate_need_no_session(api, redeemed):
    api.client.cookies.clear()
    _, plaintext = redeemed
    for endpoint, status in (("activate", 201), ("validate", 200)):
        response = api.client.post(
            f"/api/{endpoint}",
            {"license_key": plaintext, "device_fingerprint": "machine-1"},
            content_type="application/json",
        )
        assert response.status_code == status
    assert response.json()["valid"] is True


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


@pytest.mark.parametrize("fields", [{"code": " "}, {"code": "x" * 65}, {"name": "x" * 201}, {"name": ""}])
def test_product_model_fields_validated_at_api_boundary(admin_api, product, fields):
    assert admin_api.post("products", {"code": "new", "name": "New", **fields}).status_code == 400
    if "name" in fields:
        assert admin_api.patch(f"products/{product.pk}", fields).status_code == 400
    product.refresh_from_db()
    assert product.name == "Demo App"

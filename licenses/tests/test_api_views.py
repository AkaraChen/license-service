"""HTTP contract checks for the explicit function views and their documentation."""

import json
import logging
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import patch

import pytest
from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError
from django.test import override_settings
from django.urls import path

from licenses import api as views
from licenses.models import Device, Entitlement, LicenseKey, Product
from licenses.openapi import build_openapi

# Independent of view metadata: URLs, supported methods, and authentication are public contracts.
ENDPOINTS = {
    "auth/register": ({"POST"}, "anonymous"),
    "auth/login": ({"POST"}, "anonymous"),
    "auth/logout": ({"POST"}, "session"),
    "products": ({"GET", "POST"}, "admin"),
    "products/{pk}": ({"GET", "PATCH"}, "admin"),
    "license-keys": ({"GET", "POST"}, "admin"),
    "license-keys/{pk}/revoke": ({"POST"}, "admin"),
    "accounts": ({"GET"}, "admin"),
    "accounts/{pk}": ({"GET"}, "admin"),
    "entitlements": ({"GET"}, "admin"),
    "entitlements/{pk}/status": ({"POST"}, "admin"),
    "devices": ({"GET"}, "admin"),
    "devices/{pk}/unbind": ({"POST"}, "admin"),
    "me/redeem": ({"POST"}, "session"),
    "me/entitlements": ({"GET"}, "session"),
    "me/entitlements/{pk}": ({"GET"}, "session"),
    "me/entitlements/{pk}/devices": ({"GET", "POST"}, "session"),
    "me/devices/{pk}/unbind": ({"POST"}, "session"),
    "me/devices/{pk}": ({"PATCH"}, "session"),
    "activate": ({"POST"}, "anonymous"),
    "validate": ({"POST"}, "anonymous"),
}


def test_all_routes_reject_unsupported_methods_as_json(api):
    for route, (methods, _) in ENDPOINTS.items():
        for method in {"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"} - methods:
            response = api.call(method, route.replace("{pk}", "1"), {})
            assert response.status_code == 405, (route, method)
            assert response.json() == {"error": "validation_error", "message": "Method not allowed."}
        # Django removes the body for HEAD, but it must still reject the method.
        assert api.call("HEAD", route.replace("{pk}", "1")).status_code == 405


def test_documented_authentication_matches_every_http_operation(api, customer_api):
    document = api.client.get("/openapi.json").json()
    assert set(document["paths"]) == {f"/api/{route}" for route in ENDPOINTS}
    for route, (methods, auth) in ENDPOINTS.items():
        specs = document["paths"][f"/api/{route}"]
        assert set(specs) == {method.lower() for method in methods}
        for method in methods:
            spec = specs[method.lower()]
            assert spec["security"] == ([] if auth == "anonymous" else [{"sessionCookie": []}])
            response = api.call(method, route.replace("{pk}", "999999"), {})
            assert response.status_code == (400 if auth == "anonymous" else 401), (route, method)
            if auth == "admin":
                forbidden = customer_api.call(method, route.replace("{pk}", "999999"), {})
                assert forbidden.status_code == 403, (route, method)
                assert forbidden.json()["error"] == "forbidden"


def test_shared_urls_support_read_and_write_branches(admin_api, customer_api):
    response = admin_api.post("products", {"code": "branches", "name": "Before"})
    assert response.status_code == 201
    product = response.json()["product"]
    pk = product["product_id"]
    assert admin_api.get("products").json()["products"] == [product]
    assert admin_api.patch(f"products/{pk}", {"name": "After"}).status_code == 200
    assert admin_api.get(f"products/{pk}").json()["product"]["name"] == "After"
    issued = admin_api.post("license-keys", {"product_id": pk, "max_devices": 1})
    assert issued.status_code == 201
    assert issued["Cache-Control"] == "no-store, private"
    assert admin_api.get("license-keys").json()["license_keys"] == [issued.json()["key"]]
    redeemed = customer_api.post("me/redeem", {"license_key": issued.json()["license_key"]})
    assert redeemed.status_code == 201
    target = f"me/entitlements/{redeemed.json()['entitlement']['entitlement_id']}/devices"
    assert customer_api.get(target).json() == {"devices": []}
    bound = customer_api.post(target, {"device_fingerprint": "branches"})
    assert bound.status_code == 201
    assert customer_api.get(target).json()["devices"] == [bound.json()["device"]]


def test_serialization_preserves_timestamp_precision_and_nulls(admin_api, customer_api, redeemed):
    entitlement, _ = redeemed
    device = Device.objects.create(entitlement=entitlement, device_fingerprint="timestamps")
    timestamp = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC)
    Product.objects.filter(pk=entitlement.product_id).update(created_at=timestamp)
    LicenseKey.objects.filter(pk=entitlement.source_key_id).update(created_at=timestamp, expires_at=None)
    Entitlement.objects.filter(pk=entitlement.pk).update(created_at=timestamp, expires_at=None)
    Device.objects.filter(pk=device.pk).update(bound_at=timestamp, display_name=None)
    product = admin_api.get(f"products/{entitlement.product_id}").json()["product"]
    key = admin_api.get("license-keys").json()["license_keys"][0]
    owned = customer_api.get(f"me/entitlements/{entitlement.pk}").json()["entitlement"]
    bound = customer_api.get(f"me/entitlements/{entitlement.pk}/devices").json()["devices"][0]
    assert (
        product["created_at"]
        == key["created_at"]
        == owned["created_at"]
        == bound["bound_at"]
        == timestamp.isoformat()
    )
    assert key["expires_at"] is owned["expires_at"] is bound["display_name"] is None


@pytest.mark.parametrize(
    "exception,status,error",
    [
        (OperationalError("private database detail"), 503, "store_unavailable"),
        (IntegrityError("private constraint detail"), 409, "conflict"),
        (DataError("private data detail"), 400, "validation_error"),
        (RequestDataTooBig("private request detail"), 400, "validation_error"),
        (UnicodeError("private unicode detail"), 400, "validation_error"),
    ],
)
def test_shared_error_mapping_and_failure_audit(api, caplog, exception, status, error):
    with patch("licenses.api.services.authenticate_account", side_effect=exception):
        with caplog.at_level(logging.INFO, logger="licenses.api"):
            response = api.client.post(
                "/api/auth/login",
                {"username": "example", "password": "example"},
                content_type="application/json",
                HTTP_X_REQUEST_ID="inline-test",
            )
    assert response.status_code == status
    assert response.json()["error"] == error
    assert "private" not in response.content.decode()
    records = [json.loads(record.getMessage()) for record in caplog.records if record.name == "licenses.api"]
    assert records == [{"op": "login", "actor": "anonymous", "rid": "inline-test", "outcome": error}]


def test_list_query_failure_does_not_log_success(admin_api, caplog):
    with patch("licenses.api.Product.objects.order_by", side_effect=OperationalError("offline")):
        with caplog.at_level(logging.INFO, logger="licenses.api"):
            response = admin_api.get("products")
    assert response.status_code == 503
    records = [json.loads(record.getMessage()) for record in caplog.records if record.name == "licenses.api"]
    assert len(records) == 1
    assert records[0]["op"] == "list_products"
    assert records[0]["outcome"] == "store_unavailable"


def test_openapi_uses_the_active_urlconf():
    urlconf = ModuleType("test_api_urlconf")
    urlconf.urlpatterns = [path("custom/accounts/<int:pk>", views.get_account)]
    with override_settings(ROOT_URLCONF=urlconf):
        document = build_openapi()
    assert set(document["paths"]) == {"/custom/accounts/{pk}"}
    operation = document["paths"]["/custom/accounts/{pk}"]["get"]
    assert operation["operationId"] == "get_account"
    assert operation["parameters"] == [
        {"name": "pk", "in": "path", "required": True, "schema": {"type": "integer"}}
    ]


def test_patch_distinguishes_omitted_empty_and_null_names(admin_api, product):
    original = product.name
    target = f"products/{product.pk}"
    assert admin_api.patch(target, {}).json()["product"]["name"] == original
    rejected = admin_api.patch(target, {"name": None})
    assert rejected.status_code == 400
    product.refresh_from_db()
    assert product.name == original
    assert admin_api.patch(target, {"name": ""}).json()["product"]["name"] == ""


@pytest.mark.parametrize(
    "body",
    [
        '{"username":"example","password":{"secret":"never-echo-this-value"}}',
        '{"username":"example","password":"never-echo-this-value",',
        '["never-echo-this-value"]',
    ],
)
def test_invalid_credentials_never_leak_into_responses_or_logs(api, caplog, body):
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        response = api.call("POST", "auth/login", body)
    assert response.status_code == 400
    assert set(response.json()) == {"error", "message"}
    assert "never-echo-this-value" not in response.content.decode()
    assert "never-echo-this-value" not in caplog.text

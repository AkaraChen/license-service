"""SPEC 17.4: adapter / authorization. Invariants 4 and 6."""

import pytest

from licenses.models import Device, Product

from .conftest import error_class

ADMIN_WRITES = [
    ("POST", "products", {"code": "x", "name": "X"}),
    ("POST", "license-keys", {"product_id": 1, "max_devices": 1}),
    ("POST", "license-keys/1/revoke", {}),
    ("POST", "entitlements/1/status", {"status": "suspended"}),
    ("POST", "devices/1/unbind", {}),
    ("GET", "accounts", "__skip__"),
    ("GET", "entitlements", "__skip__"),
    ("GET", "devices", "__skip__"),
]


@pytest.mark.parametrize("method,path,body", ADMIN_WRITES)
def test_customer_cannot_call_admin_operations(customer_api, method, path, body):
    response = customer_api.call(method, path, body)
    assert response.status_code == 403
    assert error_class(response) == "forbidden"


def test_register_always_yields_non_admin(api):
    response = api.post("auth/register", {"username": "mallory", "password": "pw-12345"})
    assert response.status_code == 201
    assert api.json(response)["account"]["is_admin"] is False


def test_register_cannot_escalate_via_unknown_field(api):
    response = api.post("auth/register", {"username": "mallory", "password": "pw-12345", "is_staff": True})
    assert response.status_code == 400


def test_duplicate_username_conflict_case_insensitive(api):
    assert api.post("auth/register", {"username": "Alice", "password": "pw-12345"}).status_code == 201
    response = api.post("auth/register", {"username": "alice", "password": "pw-12345"})
    assert response.status_code == 409
    assert error_class(response) == "conflict"


@pytest.mark.parametrize("path", ["/api/auth/login", "/ui/login", "/admin/login/"])
def test_login_is_case_sensitive(client, admin, path):
    credentials = {"username": "RoOt", "password": "admin-pw-123"}
    if path.startswith("/api/"):
        response = client.post(path, credentials, content_type="application/json")
        assert response.status_code == 401
    else:
        assert client.post(path, credentials).status_code == 200
    assert client.get("/admin/").status_code == 302


def test_duplicate_product_code_conflict(admin_api):
    assert admin_api.post("products", {"code": "demo", "name": "One"}).status_code == 201
    response = admin_api.post("products", {"code": "Demo", "name": "Two"})
    assert response.status_code == 409
    assert error_class(response) == "conflict"
    assert Product.objects.count() == 1


def test_customer_cannot_read_foreign_entitlement(customer_api, other_customer, redeemed):
    entitlement, _ = redeemed  # owned by alice; bob's client is built below
    from .conftest import BOB_PW, Api

    bob = Api()
    bob.login("bob", BOB_PW)
    assert bob.get(f"me/entitlements/{entitlement.pk}").status_code == 404
    assert bob.get(f"me/entitlements/{entitlement.pk}/devices").status_code == 404


def test_customer_cannot_unbind_or_rename_foreign_device(customer_api, other_customer, redeemed):
    entitlement, _ = redeemed
    device = Device.objects.create(entitlement=entitlement, device_fingerprint="alice-machine")
    from .conftest import BOB_PW, Api

    bob = Api()
    bob.login("bob", BOB_PW)
    assert bob.post(f"me/devices/{device.pk}/unbind").status_code == 404
    assert bob.patch(f"me/devices/{device.pk}", {"display_name": "hijacked"}).status_code == 404
    device.refresh_from_db()
    assert device.status == "bound" and device.display_name is None


def test_foreign_rows_do_not_leak_existence(customer_api, other_customer, redeemed):
    entitlement, _ = redeemed
    from .conftest import BOB_PW, Api

    bob = Api()
    bob.login("bob", BOB_PW)
    foreign = bob.get(f"me/entitlements/{entitlement.pk}")
    missing = bob.get("me/entitlements/999999")
    assert foreign.status_code == missing.status_code == 404
    assert bob.json(foreign) == bob.json(missing)

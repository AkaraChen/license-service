"""Executable regressions mapped to the September security scan."""

import json
import re
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db import DataError, IntegrityError, transaction
from django.test import Client, override_settings

from licenses import accounts, services
from licenses.models import Device, Entitlement, LicenseKey

from .conftest import ALICE_PW


@pytest.fixture(autouse=True)
def fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def post(client, path, body, **headers):
    return client.post(path, json.dumps(body), content_type="application/json", **headers)


def test_device_names_are_bounded_in_api_and_store(db, customer_api, redeemed):
    entitlement, key = redeemed
    assert (
        post(
            Client(),
            "/api/activate",
            {"license_key": key, "device_fingerprint": "m1", "display_name": "x" * 201},
        ).status_code
        == 400
    )
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices",
            {"device_fingerprint": "m1", "display_name": "x" * 201},
        ).status_code
        == 400
    )
    assert not Device.objects.exists()
    device, _ = services.bind(entitlement, "m1", "unchanged")
    assert customer_api.patch(f"me/devices/{device.pk}", {"display_name": "x" * 201}).status_code == 400
    device.refresh_from_db()
    assert device.display_name == "unchanged"
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        Device.objects.filter(pk=device.pk).update(display_name="x" * 201)


def test_device_history_stays_bounded_and_keeps_bound_devices(db, redeemed, monkeypatch):
    monkeypatch.setattr(services, "DEVICE_HISTORY_LIMIT", 3)
    entitlement, _ = redeemed
    live, _ = services.bind(entitlement, "live")
    for i in range(10):
        device, _ = services.bind(entitlement, f"machine-{i}")
        services.unbind(device)
    assert entitlement.devices.count() == 3
    assert Device.objects.get(pk=live.pk).status == "bound"
    assert services.bind(entitlement, "live")[1] is False


@pytest.mark.parametrize("adapter", ["api", "html", "admin"])
def test_inactive_accounts_never_get_a_session(db, customer, adapter):
    customer.is_active = False
    customer.save(update_fields=("is_active",))
    client = Client()
    if adapter == "api":
        response = post(client, "/api/auth/login", {"username": "alice", "password": ALICE_PW})
        assert response.status_code == 401
    else:
        path = "/ui/login" if adapter == "html" else "/admin/login/"
        assert client.post(path, {"username": "alice", "password": ALICE_PW}).status_code == 200
    assert "_auth_user_id" not in client.session
    customer.is_active = True
    customer.save(update_fields=("is_active",))
    assert client.get("/api/me/entitlements").status_code == 401


def test_activation_changes_invalidate_existing_sessions(db, admin, customer_api, customer):
    old_cookie = customer_api.client.cookies["sessionid"].value
    staff = Client()
    staff.force_login(admin)
    assert (
        staff.post(
            f"/admin/auth/user/{customer.pk}/change/",
            {"username": customer.username, "email": "", "_save": "Save"},
        ).status_code
        == 302
    )
    customer.refresh_from_db()
    assert customer.is_active is False
    assert not Session.objects.filter(session_key=old_cookie).exists()
    assert customer_api.get("me/entitlements").status_code == 401
    accounts.set_account_active(customer, True)
    assert customer_api.get("me/entitlements").status_code == 401


def test_sibling_origin_cannot_send_json_session_mutations(customer_api, redeemed):
    entitlement, _ = redeemed
    device, _ = services.bind(entitlement, "machine")
    path = f"/api/me/devices/{device.pk}/unbind"
    response = post(customer_api.client, path, {}, HTTP_ORIGIN="http://evil.testserver")
    assert response.status_code == 403
    device.refresh_from_db()
    assert device.status == "bound"
    assert post(customer_api.client, path, {}, HTTP_ORIGIN="http://testserver").status_code == 200


def test_batch_and_single_issue_do_not_persist_plaintext(db, admin_api, product):
    for path, data in [
        ("/admin/licenses/licensekey/issue_batch/", {"product": product.pk, "max_devices": 1, "count": 3}),
        ("/admin/licenses/licensekey/add/", {"product": product.pk, "max_devices": 1}),
    ]:
        response = admin_api.client.post(path, data)
        assert response.status_code == 200  # no redirect or session-backed handoff
        assert "no-store" in response["Cache-Control"]
        keys = re.findall(r"<code>(lic_[a-z0-9]{32})</code>", response.content.decode())
        assert len(keys) == data.get("count", 1)
        durable = json.dumps([session.get_decoded() for session in Session.objects.all()])
        for key in keys:
            assert key not in durable
            assert key not in str(response.cookies)
            assert key not in admin_api.client.get(path).content.decode()


@pytest.mark.parametrize("status", ["suspended", "revoked"])
def test_bind_rechecks_status_after_resolution(db, redeemed, status):
    stale_entitlement, _ = redeemed
    Entitlement.objects.filter(pk=stale_entitlement.pk).update(status=status)
    with pytest.raises(services.Failure) as rejected:
        services.bind(stale_entitlement, "machine")
    assert rejected.value.code == f"entitlement_{status}"
    assert not Device.objects.exists()


def test_activation_rechecks_key_after_resolution(db, redeemed):
    entitlement, key = redeemed
    original = services.resolve_redeemed_key

    def revoke_after_resolution(plaintext):
        result = original(plaintext)
        LicenseKey.objects.filter(pk=entitlement.source_key_id).update(status="revoked")
        return result

    with patch.object(services, "resolve_redeemed_key", side_effect=revoke_after_resolution):
        response = post(Client(), "/api/activate", {"license_key": key, "device_fingerprint": "machine"})
    assert response.status_code == 409
    assert response.json()["error"] == "key_revoked"
    assert not Device.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        '{"username":"\\ud800","password":"pw"}',
        "[" * 1100 + "0" + "]" * 1100,
        '{"username":"x","password":' + '"x"' * 9000 + "}",
    ],
)
def test_malformed_unicode_and_nested_json_are_sanitized(db, body):
    with override_settings(DEBUG=False):
        response = Client().post("/api/auth/register", body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert b"Traceback" not in response.content
    assert not User.objects.exists()


def test_account_capacity_rejects_new_registrations(db, customer, monkeypatch):
    monkeypatch.setattr(accounts, "MAX_ACCOUNTS", 1)
    response = post(Client(), "/api/auth/register", {"username": "new", "password": "pw"})
    assert response.status_code == 429
    assert User.objects.count() == 1


def test_database_rejects_case_variant_identity_outside_registration(db, customer):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(username="ALICE")

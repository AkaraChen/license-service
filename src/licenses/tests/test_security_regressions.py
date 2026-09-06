"""Executable regressions mapped to the September security scan."""

import json
import logging
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


def test_activation_changes_invalidate_existing_sessions(db, customer_api, customer):
    old_cookie = customer_api.client.cookies["sessionid"].value
    customer.is_active = False
    customer.save(update_fields=("is_active",))
    customer.is_active = True
    customer.save(update_fields=("is_active",))
    assert not Session.objects.filter(session_key=old_cookie).exists()
    assert customer_api.get("me/entitlements").status_code == 401


@pytest.mark.parametrize(
    "content_type", ["application/x-www-form-urlencoded", "text/plain", "multipart/form-data"]
)
def test_empty_form_mutations_cannot_use_victim_session(db, admin_api, redeemed, content_type):
    entitlement, _ = redeemed
    device, _ = services.bind(entitlement, "machine")
    paths = [
        "/api/auth/logout",
        f"/api/license-keys/{entitlement.source_key_id}/revoke",
        f"/api/devices/{device.pk}/unbind",
    ]
    for path in paths:
        response = admin_api.client.generic("POST", path, b"", content_type=content_type)
        assert response.status_code == 400
    device.refresh_from_db()
    assert device.status == "bound"
    assert LicenseKey.objects.get(pk=entitlement.source_key_id).status == "redeemed"
    assert admin_api.get("accounts").status_code == 200


def test_sibling_origin_cannot_send_json_session_mutations(customer_api, redeemed):
    entitlement, _ = redeemed
    device, _ = services.bind(entitlement, "machine")
    path = f"/api/me/devices/{device.pk}/unbind"
    response = post(customer_api.client, path, {}, HTTP_ORIGIN="http://evil.testserver")
    assert response.status_code == 403
    response = customer_api.client.generic("POST", path, b"", content_type="text/plain")
    assert response.status_code == 400
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
    assert rejected.value.error == f"entitlement_{status}"
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


@pytest.mark.parametrize("rid", ["ok\noutcome=success", "id actor=admin", "x" * 1000, "a,b", "\x00"])
def test_request_ids_cannot_forge_audit_records(db, caplog, rid):
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        post(
            Client(), "/api/auth/login", {"username": "missing", "password": "secret"}, HTTP_X_REQUEST_ID=rid
        )
    records = [json.loads(record.getMessage()) for record in caplog.records if record.name == "licenses.api"]
    assert len(records) == 1
    assert records[0]["actor"] == "anonymous"
    assert records[0]["outcome"] == "unauthenticated"
    assert re.fullmatch(r"[a-f0-9]{32}", records[0]["rid"])
    assert "secret" not in caplog.text


def test_html_and_admin_mutations_emit_audit_resources(db, customer_api, admin_api, redeemed, caplog):
    entitlement, key = redeemed
    device, _ = services.bind(entitlement, "hidden-fingerprint")
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        assert customer_api.client.post("/ui/redeem", {"license_key": key}).status_code == 302
        assert (
            customer_api.client.post(
                f"/ui/devices/{device.pk}/rename", {"display_name": "Laptop"}
            ).status_code
            == 302
        )
        assert (
            admin_api.client.post(
                f"/admin/licenses/entitlement/{entitlement.pk}/change/",
                {"status": "suspended", "_save": "Save"},
            ).status_code
            == 302
        )
        assert customer_api.client.post("/ui/redeem", {"license_key": "not-a-key"}).status_code == 400
    records = [json.loads(record.getMessage()) for record in caplog.records if record.name == "licenses.api"]
    assert any(
        r["actor"] == "customer" and r.get("entitlement_id") == entitlement.pk and r["outcome"] == "success"
        for r in records
    )
    assert any(
        r["actor"] == "admin" and r.get("object_id") == entitlement.pk and r["outcome"] == "success"
        for r in records
    )
    assert any(r["outcome"] == "unknown_key" for r in records)
    assert key not in caplog.text and "hidden-fingerprint" not in caplog.text


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


def test_audit_sink_failure_does_not_fail_committed_mutation(db):
    with patch("licenses.audit.log.info", side_effect=OSError("sink unavailable")):
        response = post(Client(), "/api/auth/register", {"username": "new", "password": "pw"})
    assert response.status_code == 201
    assert User.objects.filter(username="new").exists()


def test_admin_login_audit_records_authenticated_actor(db, admin, caplog):
    with caplog.at_level(logging.INFO, logger="licenses.api"):
        response = Client().post(
            "/admin/login/", {"username": "root", "password": "admin-pw-123", "next": "/admin/"}
        )
    assert response.status_code == 302
    records = [json.loads(r.getMessage()) for r in caplog.records if r.name == "licenses.api"]
    assert records[-1]["actor"] == "admin"
    assert records[-1]["account_id"] == admin.pk
    assert records[-1]["outcome"] == "success"

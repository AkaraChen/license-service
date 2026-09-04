"""SPEC 17.5: redeem, bind, validate state machines (Sections 7.4-7.7)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from licenses import services
from licenses.models import Device, Entitlement, LicenseKey

from .conftest import BOB_PW, Api, error_class

# --- redeem (7.4) ------------------------------------------------------------


def test_first_redeem_creates_entitlement_and_marks_key(customer_api, customer, issued_key):
    key, plaintext = issued_key
    response = customer_api.post("me/redeem", {"license_key": plaintext})
    assert response.status_code == 201
    body = customer_api.json(response)["entitlement"]
    assert body["account_id"] == customer.pk and body["product_id"] == key.product_id
    assert body["max_devices"] == key.max_devices and body["status"] == "active"
    key.refresh_from_db()
    assert key.status == "redeemed" and key.redeemed_by_id == customer.pk
    assert Entitlement.objects.count() == 1


def test_redeem_same_key_same_account_is_idempotent(customer_api, redeemed):
    entitlement, plaintext = redeemed
    response = customer_api.post("me/redeem", {"license_key": plaintext})
    assert response.status_code == 200
    assert customer_api.json(response)["entitlement"]["entitlement_id"] == entitlement.pk
    assert Entitlement.objects.count() == 1


def test_redeem_key_redeemed_by_other_account(customer, other_customer, redeemed):
    _, plaintext = redeemed
    bob = Api()
    bob.login("bob", BOB_PW)
    response = bob.post("me/redeem", {"license_key": plaintext})
    assert response.status_code == 409
    assert error_class(response) == "key_already_redeemed"
    assert Entitlement.objects.count() == 1


def test_second_issued_key_same_product_is_already_entitled(customer_api, customer, product, redeemed):
    _, _ = redeemed
    second_key, second_plaintext = services.issue_key(product, max_devices=5)
    response = customer_api.post("me/redeem", {"license_key": second_plaintext})
    assert response.status_code == 409
    assert error_class(response) == "already_entitled"
    second_key.refresh_from_db()
    assert second_key.status == "issued" and second_key.redeemed_by_id is None


def test_redeem_revoked_unused_key(customer_api, issued_key):
    key, plaintext = issued_key
    services.revoke_key(key)
    response = customer_api.post("me/redeem", {"license_key": plaintext})
    assert response.status_code == 409
    assert error_class(response) == "key_revoked"
    assert Entitlement.objects.count() == 0


def test_redeem_unknown_key(customer_api):
    response = customer_api.post("me/redeem", {"license_key": "lic_doesnotexist"})
    assert response.status_code == 404
    assert error_class(response) == "unknown_key"


# --- bind (7.5) --------------------------------------------------------------


def test_bind_occupies_one_seat_and_is_idempotent(customer_api, redeemed):
    entitlement, _ = redeemed
    first = customer_api.post(
        f"me/entitlements/{entitlement.pk}/devices",
        {"device_fingerprint": "machine-1", "display_name": "Laptop"},
    )
    assert first.status_code == 201
    again = customer_api.post(
        f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "machine-1"}
    )
    assert again.status_code == 200
    assert customer_api.json(again)["device"]["device_id"] == customer_api.json(first)["device"]["device_id"]
    assert Device.objects.filter(status="bound").count() == 1


def test_bind_trims_fingerprint_and_matches_case_sensitively(customer_api, redeemed):
    entitlement, _ = redeemed
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "  machine-1  "}
        ).status_code
        == 201
    )
    device = Device.objects.get()
    assert device.device_fingerprint == "machine-1"
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "machine-1"}
        ).status_code
        == 200
    )
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "MACHINE-1"}
        ).status_code
        == 201
    )


def test_seat_exhausted_at_max_devices(customer_api, redeemed):
    entitlement, _ = redeemed  # max_devices=2
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"}
        ).status_code
        == 201
    )
    assert (
        customer_api.post(
            f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m2"}
        ).status_code
        == 201
    )
    response = customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m3"})
    assert response.status_code == 409
    assert error_class(response) == "seat_exhausted"
    assert Device.objects.filter(status="bound").count() == 2


def test_unbind_frees_seat_and_rebind_creates_new_device(customer_api, redeemed):
    entitlement, _ = redeemed
    first = customer_api.json(
        customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"})
    )["device"]
    customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m2"})
    assert customer_api.post(f"me/devices/{first['device_id']}/unbind").status_code == 200
    rebound = customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"})
    assert rebound.status_code == 201
    assert customer_api.json(rebound)["device"]["device_id"] != first["device_id"]
    assert Device.objects.filter(status="bound").count() == 2


def test_unbind_is_idempotent(customer_api, redeemed):
    entitlement, _ = redeemed
    device = customer_api.json(
        customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"})
    )["device"]
    assert customer_api.post(f"me/devices/{device['device_id']}/unbind").status_code == 200
    second = customer_api.post(f"me/devices/{device['device_id']}/unbind")
    assert second.status_code == 200
    assert customer_api.json(second)["device"]["status"] == "unbound"


def test_set_display_name(customer_api, redeemed):
    entitlement, _ = redeemed
    device = customer_api.json(
        customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m1"})
    )["device"]
    response = customer_api.patch(f"me/devices/{device['device_id']}", {"display_name": "Workstation"})
    assert customer_api.json(response)["device"]["display_name"] == "Workstation"
    response = customer_api.patch(f"me/devices/{device['device_id']}", {"display_name": None})
    assert customer_api.json(response)["device"]["display_name"] is None


# --- validate (7.7) ----------------------------------------------------------


def test_validate_happy_path(api, redeemed):
    _, plaintext = redeemed
    api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
    response = api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"})
    assert response.status_code == 200
    assert api.json(response)["valid"] is True


def test_validate_creates_no_rows(api, redeemed):
    _, plaintext = redeemed
    counts = [Device.objects.count(), Entitlement.objects.count(), LicenseKey.objects.count()]
    api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"})
    api.post("validate", {"license_key": "lic_nope", "device_fingerprint": "m1"})
    assert counts == [Device.objects.count(), Entitlement.objects.count(), LicenseKey.objects.count()]


def test_validate_unknown_and_issued_key(api, issued_key):
    _, plaintext = issued_key  # still "issued"
    assert (
        error_class(api.post("validate", {"license_key": "lic_nope", "device_fingerprint": "m1"}))
        == "unknown_key"
    )
    assert (
        error_class(api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"}))
        == "unknown_key"
    )


def test_validate_revoked_key(api, redeemed):
    _, plaintext = redeemed
    api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
    services.revoke_key(LicenseKey.objects.get())
    response = api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"})
    assert response.status_code == 409
    assert error_class(response) == "key_revoked"


def test_validate_unknown_device(api, redeemed):
    _, plaintext = redeemed
    response = api.post("validate", {"license_key": plaintext, "device_fingerprint": "ghost"})
    assert response.status_code == 404
    assert error_class(response) == "unknown_device"


@pytest.mark.parametrize(
    "status,error", [("suspended", "entitlement_suspended"), ("revoked", "entitlement_revoked")]
)
def test_suspended_and_revoked_block_bind_and_validate(api, customer_api, redeemed, status, error):
    entitlement, plaintext = redeemed
    api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
    entitlement.status = status
    entitlement.save(update_fields=("status",))
    for response in (
        api.post("activate", {"license_key": plaintext, "device_fingerprint": "m2"}),
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"}),
        customer_api.post(f"me/entitlements/{entitlement.pk}/devices", {"device_fingerprint": "m2"}),
    ):
        assert response.status_code == 409
        assert error_class(response) == error
    assert Device.objects.filter(status="bound").count() == 1


def test_expired_entitlement_blocks_bind_and_validate(api, customer_api, customer, product):
    _, plaintext = services.issue_key(
        product, max_devices=2, expires_at=timezone.now() + timedelta(minutes=5)
    )
    services.redeem(customer, plaintext)
    assert api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"}).status_code == 201
    Entitlement.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    for response in (
        api.post("activate", {"license_key": plaintext, "device_fingerprint": "m2"}),
        api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"}),
    ):
        assert response.status_code == 409
        assert error_class(response) == "entitlement_expired"


def test_admin_unbind_device(admin_api, api, redeemed):
    _, plaintext = redeemed
    device = api.json(api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"}))["device"]
    response = admin_api.post(f"devices/{device['device_id']}/unbind")
    assert response.status_code == 200
    assert Device.objects.get().status == "unbound"


def test_admin_set_entitlement_status_roundtrip(admin_api, api, redeemed):
    entitlement, plaintext = redeemed
    response = admin_api.post(f"entitlements/{entitlement.pk}/status", {"status": "suspended"})
    assert admin_api.json(response)["entitlement"]["status"] == "suspended"
    assert (
        error_class(api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"}))
        == "entitlement_suspended"
    )
    admin_api.post(f"entitlements/{entitlement.pk}/status", {"status": "active"})
    api.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})
    assert api.post("validate", {"license_key": plaintext, "device_fingerprint": "m1"}).status_code == 200


def test_admin_revoke_redeemed_key_leaves_entitlement_status(admin_api, redeemed):
    entitlement, _ = redeemed
    admin_api.post(f"license-keys/{entitlement.source_key_id}/revoke")
    entitlement.refresh_from_db()
    assert entitlement.status == "active"  # Section 7.1: key revoke does not cascade

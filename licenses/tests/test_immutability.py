"""SPEC 17.6: Entitlement immutability (Invariant 7) and seat safety under
concurrent binds (Invariant 3)."""

import threading

import pytest
from django.db import close_old_connections

from licenses import services
from licenses.models import Device

from .conftest import error_class


def test_set_entitlement_status_rejects_immutable_fields(admin_api, redeemed):
    entitlement, _ = redeemed
    for field, value in (("max_devices", 99), ("expires_at", None)):
        response = admin_api.post(f"entitlements/{entitlement.pk}/status", {"status": "active", field: value})
        assert response.status_code == 400
        assert error_class(response) == "validation_error"


def test_no_operation_mutates_max_devices_or_expires_at(admin_api, customer_api, redeemed):
    entitlement, _ = redeemed
    before = entitlement.max_devices, entitlement.expires_at
    assert admin_api.call("PATCH", f"entitlements/{entitlement.pk}", {"max_devices": 99}).status_code in (
        400,
        404,
        405,
    )
    assert customer_api.patch(f"me/entitlements/{entitlement.pk}", {"max_devices": 99}).status_code in (
        400,
        404,
        405,
    )
    entitlement.refresh_from_db()
    assert (entitlement.max_devices, entitlement.expires_at) == before


def test_source_key_cannot_change(admin_api, redeemed, product):
    entitlement, _ = redeemed
    other_key, _ = services.issue_key(product, max_devices=1)
    response = admin_api.post(
        f"entitlements/{entitlement.pk}/status", {"status": "active", "source_key_id": other_key.pk}
    )
    assert response.status_code == 400
    entitlement.refresh_from_db()
    assert entitlement.source_key_id != other_key.pk


@pytest.mark.django_db(transaction=True)
def test_concurrent_binds_never_exceed_max_devices(customer, product):
    _, plaintext = services.issue_key(product, max_devices=3)
    entitlement, _ = services.redeem(customer, plaintext)
    results = []
    barrier = threading.Barrier(8)

    def racer(i):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            _, created = services.bind(entitlement, f"machine-{i}")
            results.append(created)
        except services.Failure as exc:
            results.append(exc.error)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=racer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert results.count(True) == 3
    assert results.count("seat_exhausted") == 5
    assert Device.objects.filter(entitlement=entitlement, status="bound").count() == 3

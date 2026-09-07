"""SPEC 17.6: Entitlement immutability (Invariant 7) and seat safety under
concurrent binds (Invariant 3)."""

import threading

import pytest
from django.db import close_old_connections

from licenses import services
from licenses.models import Device

from .conftest import error_class


@pytest.mark.parametrize("field,value", [("max_devices", 99), ("expires_at", None), ("source_key_id", 99999)])
def test_set_entitlement_status_rejects_immutable_fields(admin_api, redeemed, field, value):
    entitlement, _ = redeemed
    before = entitlement.max_devices, entitlement.expires_at, entitlement.source_key_id
    response = admin_api.post(f"entitlements/{entitlement.pk}/status", {"status": "active", field: value})
    assert response.status_code == 400
    assert error_class(response) == "validation_error"
    entitlement.refresh_from_db()
    assert (entitlement.max_devices, entitlement.expires_at, entitlement.source_key_id) == before


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
            results.append(exc.code)
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

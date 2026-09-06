"""Concurrent identity creation and commit-order authorization regressions."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections, connection, transaction
from django.test import Client

from licenses import services
from licenses.models import Device, Entitlement, LicenseKey


@pytest.mark.django_db(transaction=True)
def test_case_variant_registration_race_has_one_winner(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    admission_barrier = threading.Barrier(2)

    def register(username):
        close_old_connections()
        try:
            admission_barrier.wait(timeout=5)
            return (
                Client()
                .post(
                    "/api/auth/register",
                    {"username": username, "password": "pw"},
                    content_type="application/json",
                )
                .status_code
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(register, ["Alice", "alice"]))
    assert sorted(statuses) == [201, 409]
    assert User.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("target", ["entitlement", "key"])
def test_bind_waits_for_revocation_commit(redeemed, target):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock ordering integration")
    entitlement, _ = redeemed
    locked = threading.Event()
    attempted = threading.Event()
    model = Entitlement if target == "entitlement" else LicenseKey
    pk = entitlement.pk if target == "entitlement" else entitlement.source_key_id

    def revoke():
        close_old_connections()
        try:
            with transaction.atomic():
                model.objects.select_for_update().get(pk=pk)
                model.objects.filter(pk=pk).update(status="revoked")
                locked.set()
                assert attempted.wait(timeout=5)
        finally:
            close_old_connections()

    def bind():
        close_old_connections()
        try:
            assert locked.wait(timeout=5)
            attempted.set()
            try:
                services.bind(entitlement, "racing-machine", source_key_id=entitlement.source_key_id)
            except services.Failure as exc:
                return exc.code
            return "unexpected success"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        revoked = pool.submit(revoke)
        bound = pool.submit(bind)
        revoked.result(timeout=10)
        assert bound.result(timeout=10) == f"{target}_revoked"
    assert not Device.objects.exists()

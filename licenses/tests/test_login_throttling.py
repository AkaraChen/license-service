"""Persistent abuse controls for every password-login adapter."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.test import Client
from django.utils import timezone

from licenses import auth as auth_backend
from licenses.auth import LOGIN_FAILURE_LIMIT
from licenses.models import LoginThrottle

from .conftest import ALICE_PW


def _api_login(client, username, password, source="192.0.2.10", **headers):
    return client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
        REMOTE_ADDR=source,
        **headers,
    )


@pytest.mark.parametrize("adapter", ("api", "html"))
def test_login_adapters_lock_repeated_failures_and_recover_after_expiry(db, customer, adapter):
    client = Client()
    for _ in range(LOGIN_FAILURE_LIMIT):
        if adapter == "api":
            response = _api_login(client, " Alice ", "wrong")
            assert response.status_code == 401
            assert response.json()["error"] == "unauthenticated"
        else:
            response = client.post(
                "/ui/login", {"username": " Alice ", "password": "wrong"}, REMOTE_ADDR="192.0.2.10"
            )
            assert response.status_code == 200
            assert b"Invalid username or password" in response.content

    if adapter == "api":
        blocked = _api_login(client, "alice", ALICE_PW)
        assert blocked.status_code == 401
        assert blocked.json()["error"] == "unauthenticated"
    else:
        blocked = client.post(
            "/ui/login", {"username": "alice", "password": ALICE_PW}, REMOTE_ADDR="192.0.2.10"
        )
        assert blocked.status_code == 200
        assert "_auth_user_id" not in client.session

    LoginThrottle.objects.update(
        window_started_at=timezone.now() - timedelta(hours=1),
        locked_until=timezone.now() - timedelta(seconds=1),
    )
    if adapter == "api":
        assert _api_login(client, "alice", ALICE_PW).status_code == 200
    else:
        assert (
            client.post(
                "/ui/login", {"username": "alice", "password": ALICE_PW}, REMOTE_ADDR="192.0.2.10"
            ).status_code
            == 302
        )


def test_distributed_sources_share_the_account_limit(db, customer):
    for attempt in range(LOGIN_FAILURE_LIMIT):
        response = _api_login(Client(), "ALICE", "wrong", source=f"192.0.2.{attempt + 1}")
        assert response.status_code == 401

    blocked = _api_login(Client(), "alice", ALICE_PW, source="198.51.100.10")
    assert blocked.status_code == 401
    assert LoginThrottle.objects.get(scope="account").locked_until > timezone.now()


def test_one_source_cannot_spray_accounts_or_spoof_forwarded_address(db, customer):
    client = Client()
    for attempt in range(LOGIN_FAILURE_LIMIT):
        response = _api_login(
            client,
            f"missing-{attempt}",
            "wrong",
            source="192.0.2.10",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt + 1}",
        )
        assert response.status_code == 401

    blocked = _api_login(client, "alice", ALICE_PW, source="192.0.2.10")
    assert blocked.status_code == 401
    assert LoginThrottle.objects.filter(scope="source").count() == 1


def test_admin_login_uses_the_same_account_throttle(db, admin):
    for attempt in range(LOGIN_FAILURE_LIMIT):
        response = Client().post(
            "/admin/login/",
            {"username": "root", "password": "wrong", "next": "/admin/"},
            REMOTE_ADDR=f"192.0.2.{attempt + 1}",
        )
        assert response.status_code == 200

    client = Client()
    blocked = client.post(
        "/admin/login/",
        {"username": "root", "password": "admin-pw-123", "next": "/admin/"},
        REMOTE_ADDR="198.51.100.10",
    )
    assert blocked.status_code == 200
    assert "_auth_user_id" not in client.session


def test_sessions_from_the_previous_backend_remain_valid(db, customer):
    client = Client()
    session = client.session
    session[SESSION_KEY] = str(customer.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = customer.get_session_auth_hash()
    session.save()

    assert client.get("/api/me/entitlements").status_code == 200


def test_account_lock_uses_dummy_hash_without_checking_the_account_password(db, customer):
    for attempt in range(LOGIN_FAILURE_LIMIT):
        assert _api_login(Client(), "alice", "wrong", source=f"192.0.2.{attempt + 1}").status_code == 401

    with (
        patch.object(User, "check_password", side_effect=AssertionError("account hash was checked")),
        patch("django.contrib.auth.base_user.make_password", return_value="!dummy") as dummy_hash,
    ):
        assert _api_login(Client(), "alice", ALICE_PW, source="198.51.100.10").status_code == 401
    dummy_hash.assert_called_once_with(ALICE_PW)


def test_stale_throttle_rows_are_pruned(db, customer):
    stale = LoginThrottle.objects.create(scope="source", key_digest="0" * 64)
    LoginThrottle.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(hours=1))

    assert _api_login(Client(), "alice", ALICE_PW, source="192.0.2.10").status_code == 200
    assert not LoginThrottle.objects.filter(pk=stale.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_sqlite_failures_are_retried_and_counted(customer, monkeypatch):
    if connection.vendor != "sqlite":
        pytest.skip("SQLite lock-retry regression test")

    barrier = threading.Barrier(2)
    synchronized_threads = set()
    guard = threading.Lock()
    original_normalize = auth_backend._normalize_state

    assert _api_login(Client(), "alice", ALICE_PW, source="192.0.2.10").status_code == 200
    assert _api_login(Client(), "alice", ALICE_PW, source="198.51.100.10").status_code == 200
    monkeypatch.setattr(auth_backend, "_prune_stale", lambda now: None)

    def synchronize_once(state, now):
        result = original_normalize(state, now)
        should_wait = False
        if state.scope == "account":
            thread_id = threading.get_ident()
            with guard:
                if thread_id not in synchronized_threads:
                    synchronized_threads.add(thread_id)
                    should_wait = True
        if should_wait:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(auth_backend, "_normalize_state", synchronize_once)

    def fail_login(source):
        close_old_connections()
        try:
            return _api_login(Client(), "alice", "wrong", source=source).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(fail_login, ("192.0.2.10", "198.51.100.10")))

    assert statuses == [401, 401]
    assert LoginThrottle.objects.get(scope="account").failure_count == 2

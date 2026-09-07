import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from licenses import accounts, services
from licenses.models import Product

ADMIN_PW = "admin-pw-123"
ALICE_PW = "alice-pw-123"
BOB_PW = "bob-pw-123"


class Api:
    """Thin JSON client over Django's test Client."""

    def __init__(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/ui/login")

    def call(self, method, path, body="__skip__", content_type="application/json"):
        kwargs = {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}
        if body != "__skip__":
            kwargs.update(data=body if isinstance(body, str) else json.dumps(body), content_type=content_type)
        return self.client.generic(method, f"/api/{path}", **kwargs)

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, {} if body is None else body)

    def patch(self, path, body=None):
        return self.call("PATCH", path, {} if body is None else body)

    def login(self, username, password):
        return self.post("auth/login", {"username": username, "password": password})

    def json(self, response):
        return json.loads(response.content)


@pytest.fixture
def api(db):
    return Api()


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(username="root", password=ADMIN_PW)


@pytest.fixture
def admin_api(admin):
    client = Api()
    assert client.login("root", ADMIN_PW).status_code == 200
    return client


@pytest.fixture
def customer(db):
    return accounts.register_account("alice", ALICE_PW)


@pytest.fixture
def other_customer(db):
    return accounts.register_account("bob", BOB_PW)


@pytest.fixture
def customer_api(customer):
    client = Api()
    assert client.login("alice", ALICE_PW).status_code == 200
    return client


@pytest.fixture
def product(db):
    return Product.objects.create(code="demo", name="Demo App")


@pytest.fixture
def issued_key(product):
    key, plaintext = services.issue_key(product, max_devices=2)
    return key, plaintext


@pytest.fixture
def redeemed(customer, issued_key):
    _, plaintext = issued_key
    entitlement, created = services.redeem(customer, plaintext)
    assert created
    return entitlement, plaintext


def error_class(response):
    return json.loads(response.content)["error"]


@pytest.fixture(autouse=True)
def isolated_security_cache():
    from django.core.cache import caches

    # delete_pattern applies this test process's random KEY_PREFIX; never FLUSHDB.
    caches["default"].delete_pattern("*")
    yield
    caches["default"].delete_pattern("*")

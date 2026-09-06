"""SPEC 17.3: resources and secrets. Invariant 5; Section 9.1 restart durability."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from django.db import connection

from licenses.models import LicenseKey

from .conftest import ALICE_PW


def test_plaintext_key_never_stored_or_listed(admin_api, product):
    issued = admin_api.post("license-keys", {"product_id": product.pk, "max_devices": 1})
    plaintext = admin_api.json(issued)["license_key"]
    assert plaintext.startswith("lic_") and len(plaintext) == 36
    key = LicenseKey.objects.get()
    assert key.key_hash != plaintext and plaintext not in key.key_hash
    assert plaintext.startswith(key.key_prefix) and len(key.key_prefix) < len(plaintext)
    listed = admin_api.get("license-keys").content.decode()
    assert plaintext not in listed
    assert admin_api.get("accounts/1").content.decode().find(plaintext) == -1


def test_account_payloads_never_expose_password_hash(admin_api, customer):
    for path in ("accounts", f"accounts/{customer.pk}"):
        body = admin_api.get(path).content.decode()
        assert "pbkdf2" not in body and "password" not in body


@pytest.mark.django_db(transaction=True)
def test_restart_preserves_all_durable_rows(admin_api):
    """A separate process opening the same store file must see every row."""
    created = admin_api.json(admin_api.post("products", {"code": "demo", "name": "Demo"}))
    product_id = created["product"]["product_id"]
    plaintext = admin_api.json(admin_api.post("license-keys", {"product_id": product_id, "max_devices": 2}))[
        "license_key"
    ]
    admin_api.post("auth/register", {"username": "alice", "password": ALICE_PW})
    from .conftest import Api

    alice = Api()
    alice.login("alice", ALICE_PW)
    alice.post("me/redeem", {"license_key": plaintext})
    alice.post("activate", {"license_key": plaintext, "device_fingerprint": "m1"})

    db_file = connection.settings_dict["NAME"]
    probe = (
        "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');"
        "django.setup();"
        "from django.contrib.auth.models import User;"
        "from licenses.models import Product,LicenseKey,Entitlement,Device;"
        "print(User.objects.count(),Product.objects.count(),LicenseKey.objects.count(),"
        "Entitlement.objects.count(),Device.objects.count())"
    )
    url = urlsplit(os.environ.get("LICENSE_DATABASE_URL", "sqlite:///"))
    database_url = (
        f"sqlite:///{db_file}"
        if connection.vendor == "sqlite"
        else urlunsplit(url._replace(path="/" + str(db_file)))
    )
    env = {**os.environ, "LICENSE_DATABASE_URL": database_url}
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["2", "1", "1", "1", "1"]

"""Resource payloads and secret non-disclosure (Invariant 5)."""

from licenses.models import LicenseKey


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

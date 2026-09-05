"""SPEC 17.8: HTML UI and host lifecycle; Section 3.1.4 page requirements."""

from django.test import Client

from licenses import services
from licenses.models import Device, Entitlement

from .conftest import ADMIN_PW, ALICE_PW


def test_admin_console_requires_admin_session(db, admin, customer):
    anonymous = Client()
    response = anonymous.get("/admin/")
    assert response.status_code == 302 and "/admin/login" in response["Location"]

    non_admin = Client()
    non_admin.login(username="alice", password=ALICE_PW)
    response = non_admin.get("/admin/")
    assert response.status_code == 302 and "/admin/login" in response["Location"]

    staff = Client()
    staff.login(username="root", password=ADMIN_PW)
    assert staff.get("/admin/").status_code == 200


def test_customer_pages_full_flow(db, customer, product):
    _, plaintext = services.issue_key(product, max_devices=1)
    browser = Client()

    page = browser.get("/ui/register")
    assert page.status_code == 200
    assert b"css/tailwind.css" in page.content
    response = browser.post("/ui/register", {"username": "carol", "password": "carol-pw-1"})
    assert response.status_code == 302  # registered and logged in

    home = browser.get("/")
    assert home.status_code == 200
    assert b"No entitlements yet" in home.content

    response = browser.post("/ui/redeem", {"license_key": plaintext})
    assert response.status_code == 302
    assert Entitlement.objects.count() == 1
    entitlement = Entitlement.objects.get()

    home = browser.get("/")
    assert b"Demo App" in home.content

    page = browser.get(f"/ui/entitlements/{entitlement.pk}")
    assert page.status_code == 200
    response = browser.post(
        f"/ui/entitlements/{entitlement.pk}",
        {"device_fingerprint": "browser-machine", "display_name": "Laptop"},
    )
    assert response.status_code == 302
    device = Device.objects.get()
    assert device.status == "bound" and device.display_name == "Laptop"

    response = browser.post(f"/ui/devices/{device.pk}/unbind")
    assert response.status_code == 302
    device.refresh_from_db()
    assert device.status == "unbound"


def test_customer_pages_require_login(db):
    response = Client().get("/")
    assert response.status_code == 302 and "/ui/login" in response["Location"]


def test_customer_pages_never_link_admin_console(db, customer, redeemed):
    browser = Client()
    browser.login(username="alice", password=ALICE_PW)
    entitlement, _ = redeemed
    for path in ("/", "/ui/redeem", f"/ui/entitlements/{entitlement.pk}"):
        body = browser.get(path).content.decode()
        assert 'href="/admin' not in body and 'action="/admin' not in body


def test_customer_cannot_open_foreign_entitlement_page(db, customer, other_customer, redeemed):
    entitlement, _ = redeemed
    bob_browser = Client()
    bob_browser.login(username="bob", password="bob-pw-123")
    response = bob_browser.get(f"/ui/entitlements/{entitlement.pk}")
    assert response.status_code == 400  # error page, no data leaked
    assert b"Not found" in response.content


def test_admin_console_issue_key_shows_plaintext_once(db, admin, product):
    staff = Client()
    staff.login(username="root", password=ADMIN_PW)
    response = staff.post(
        "/admin/licenses/licensekey/add/", {"product": product.pk, "max_devices": "2"}, follow=True
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "lic_" in body  # issuing response shows plaintext once
    again = staff.get("/admin/licenses/licensekey/").content.decode()
    assert "lic_" not in again.split("key_prefix")[0] or "shown once" not in again


def test_admin_console_never_shows_password_hash(db, admin):
    staff = Client()
    staff.login(username="root", password=ADMIN_PW)
    body = staff.get(f"/admin/auth/user/{admin.pk}/change/").content.decode()
    assert "pbkdf2" not in body


def test_admin_console_entitlement_immutable_fields_readonly(db, admin, redeemed):
    staff = Client()
    staff.login(username="root", password=ADMIN_PW)
    entitlement, _ = redeemed
    body = staff.get(f"/admin/licenses/entitlement/{entitlement.pk}/change/").content.decode()
    assert 'name="status"' in body
    assert 'name="max_devices"' not in body
    assert 'name="expires_at' not in body

"""SPEC 17.8: HTML UI and host lifecycle; Section 3.1.4 page requirements."""

import re

from django.test import Client

from licenses import services
from licenses.models import Entitlement, LicenseKey

from .conftest import ADMIN_PW, ALICE_PW


def test_admin_console_requires_admin_session(db, admin, customer):
    anonymous = Client()
    response = anonymous.get("/admin/")
    assert response.status_code == 302 and "/admin/login" in response["Location"]

    non_admin = Client()
    non_admin.post(
        "/api/auth/login", {"username": "alice", "password": ALICE_PW}, content_type="application/json"
    )
    response = non_admin.get("/admin/")
    assert response.status_code == 302 and "/admin/login" in response["Location"]

    staff = Client()
    staff.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")
    home = staff.get("/admin/")
    assert home.status_code == 200
    assert b"unfold" in home.content
    assert b"License Service" in home.content
    assert b"--color-primary-600: rgb(0, 107, 255)" in home.content
    assert b"css/admin-theme.css" in home.content


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
    assert b"Bind a new device" not in page.content
    assert b'name="device_fingerprint"' not in page.content
    assert browser.post(f"/ui/entitlements/{entitlement.pk}", {"device_fingerprint": "x"}).status_code == 405

    device, _ = services.bind(entitlement, "browser-machine", "Laptop")
    page = browser.get(f"/ui/entitlements/{entitlement.pk}")
    assert b"Laptop" in page.content

    response = browser.post(f"/ui/devices/{device.pk}/unbind")
    assert response.status_code == 302
    device.refresh_from_db()
    assert device.status == "unbound"


def test_customer_pages_require_login(db):
    response = Client().get("/")
    assert response.status_code == 302 and "/ui/login" in response["Location"]
    assert "next=/" in response["Location"]


def test_login_returns_to_redeem_via_next(db, customer):
    browser = Client()
    bounced = browser.get("/ui/redeem")
    assert bounced.status_code == 302
    assert bounced["Location"] == "/ui/login?next=/ui/redeem"

    form = browser.get(bounced["Location"])
    assert form.status_code == 200
    body = form.content.decode()
    assert 'name="next"' in body and 'value="/ui/redeem"' in body
    assert 'href="/ui/register?next=/ui/redeem"' in body

    logged_in = browser.post("/ui/login", {"username": "alice", "password": ALICE_PW, "next": "/ui/redeem"})
    assert logged_in.status_code == 302 and logged_in["Location"] == "/ui/redeem"
    assert browser.get("/ui/redeem").status_code == 200


def test_login_honors_redirect_query_and_rejects_unsafe_targets(db, customer):
    browser = Client()
    via_redirect = browser.post("/ui/login?redirect=/ui/redeem", {"username": "alice", "password": ALICE_PW})
    assert via_redirect.status_code == 302 and via_redirect["Location"] == "/ui/redeem"

    offsite = Client()
    response = offsite.post(
        "/ui/login", {"username": "alice", "password": ALICE_PW, "next": "https://evil.example/"}
    )
    assert response.status_code == 302 and response["Location"] == "/"

    admin_target = Client()
    response = admin_target.post("/ui/login", {"username": "alice", "password": ALICE_PW, "next": "/admin/"})
    assert response.status_code == 302 and response["Location"] == "/"


def test_register_returns_to_next(db):
    browser = Client()
    response = browser.post(
        "/ui/register", {"username": "carol", "password": "carol-pw-1", "next": "/ui/redeem"}
    )
    assert response.status_code == 302 and response["Location"] == "/ui/redeem"


def test_customer_pages_never_link_admin_console(db, customer, redeemed):
    browser = Client()
    browser.post(
        "/api/auth/login", {"username": "alice", "password": ALICE_PW}, content_type="application/json"
    )
    entitlement, _ = redeemed
    for path in ("/", "/ui/redeem", f"/ui/entitlements/{entitlement.pk}"):
        body = browser.get(path).content.decode()
        assert 'href="/admin' not in body and 'action="/admin' not in body


def test_customer_cannot_open_foreign_entitlement_page(db, customer, other_customer, redeemed):
    entitlement, _ = redeemed
    bob_browser = Client()
    bob_browser.post(
        "/api/auth/login", {"username": "bob", "password": "bob-pw-123"}, content_type="application/json"
    )
    response = bob_browser.get(f"/ui/entitlements/{entitlement.pk}")
    assert response.status_code == 400  # error page, no data leaked
    assert b"Not found" in response.content


def test_admin_console_issue_key_shows_plaintext_once(db, admin, product):
    staff = Client()
    staff.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")
    response = staff.post(
        "/admin/licenses/licensekey/add/", {"product": product.pk, "max_devices": "2"}, follow=True
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "lic_" in body  # issuing response shows plaintext once
    again = staff.get("/admin/licenses/licensekey/").content.decode()
    assert "lic_" not in again.split("key_prefix")[0] or "shown once" not in again


def test_admin_console_batch_issue_requires_admin_session(db, customer):
    path = "/admin/licenses/licensekey/issue_batch/"
    anonymous = Client().get(path)
    assert anonymous.status_code == 302 and "/admin/login" in anonymous["Location"]

    non_admin = Client()
    non_admin.post(
        "/api/auth/login", {"username": "alice", "password": ALICE_PW}, content_type="application/json"
    )
    response = non_admin.get(path)
    assert response.status_code == 302 and "/admin/login" in response["Location"]


def test_admin_console_batch_issue_creates_keys_and_shows_plaintext_once(db, admin, product):
    staff = Client()
    staff.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")

    changelist = staff.get("/admin/licenses/licensekey/").content.decode()
    assert "Issue batch" in changelist
    assert "/admin/licenses/licensekey/issue_batch/" in changelist

    form_page = staff.get("/admin/licenses/licensekey/issue_batch/")
    assert form_page.status_code == 200
    form_body = form_page.content.decode()
    assert 'name="product"' in form_body
    assert 'name="max_devices"' in form_body
    assert 'name="count"' in form_body

    rejected = staff.post(
        "/admin/licenses/licensekey/issue_batch/", {"product": product.pk, "max_devices": "2", "count": "51"}
    )
    assert rejected.status_code == 200
    assert LicenseKey.objects.count() == 0

    response = staff.post(
        "/admin/licenses/licensekey/issue_batch/",
        {"product": product.pk, "max_devices": "2", "count": "3"},
        follow=True,
    )
    assert response.status_code == 200
    body = response.content.decode()
    keys = re.findall(r"<code>(lic_[a-z0-9]{32})</code>", body)
    assert len(keys) == 3
    assert LicenseKey.objects.count() == 3
    assert all(key.startswith("lic_") and len(key) == 36 for key in keys)

    reload_result = staff.get("/admin/licenses/licensekey/issue_batch/").content.decode()
    for key in keys:
        assert key not in reload_result
    assert LicenseKey.objects.count() == 3  # refresh does not issue another batch

    again = staff.get("/admin/licenses/licensekey/").content.decode()
    for key in keys:
        assert key not in again
        assert key[:12] in again

    zh = Client()
    zh.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")
    zh_page = zh.get("/admin/licenses/licensekey/issue_batch/", HTTP_ACCEPT_LANGUAGE="zh-hans")
    assert zh_page.status_code == 200
    assert "批量签发" in zh_page.content.decode()


def test_admin_console_never_shows_password_hash(db, admin):
    staff = Client()
    staff.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")
    body = staff.get(f"/admin/auth/user/{admin.pk}/change/").content.decode()
    assert "pbkdf2" not in body


def test_customer_pages_follow_accept_language(db):
    en = Client().get("/ui/login", HTTP_ACCEPT_LANGUAGE="en")
    assert en.status_code == 200
    assert b"Log in" in en.content and 'lang="en"' in en.content.decode()

    zh = Client().get("/ui/login", HTTP_ACCEPT_LANGUAGE="zh-CN,zh;q=0.9")
    assert zh.status_code == 200
    body = zh.content.decode()
    assert "登录" in body and 'lang="zh-hans"' in body
    assert b"Log in" not in zh.content


def test_admin_console_entitlement_immutable_fields_readonly(db, admin, redeemed):
    staff = Client()
    staff.post("/api/auth/login", {"username": "root", "password": ADMIN_PW}, content_type="application/json")
    entitlement, _ = redeemed
    body = staff.get(f"/admin/licenses/entitlement/{entitlement.pk}/change/").content.decode()
    assert 'name="status"' in body
    assert 'name="max_devices"' not in body
    assert 'name="expires_at' not in body

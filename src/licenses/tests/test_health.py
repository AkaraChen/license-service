from unittest.mock import patch

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(SECURE_SSL_REDIRECT=True)
def test_health_works_over_http_and_is_not_cached():
    client = Client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-store" in response.headers["Cache-Control"]
    assert client.head("/healthz").status_code == 200
    assert client.get("/ui/login").status_code == 301
    assert client.get("/healthz/extra").status_code == 301
    assert client.get("/healthz", HTTP_HOST="untrusted.invalid").status_code == 400
    assert client.post("/healthz").status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("dependency", ["connection.cursor", "cache.set", "cache.get"])
def test_health_dependency_failures_return_generic_503(dependency):
    with patch(f"licenses.views.health.{dependency}", side_effect=RuntimeError("private-details")):
        response = Client().get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "private-details" not in response.content.decode()
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.django_db
def test_health_detects_cache_roundtrip_failure():
    with patch("licenses.views.health.cache.get", return_value=None):
        assert Client().get("/healthz").status_code == 503


@pytest.mark.django_db
def test_kamal_internal_probe_does_not_relax_business_host_validation():
    from django.conf import settings

    middleware = ["licenses.views.health.HealthcheckMiddleware", *settings.MIDDLEWARE]
    with override_settings(MIDDLEWARE=middleware, SECURE_SSL_REDIRECT=True):
        client = Client()
        assert client.get("/healthz", HTTP_HOST="a1b2c3d4e5f6:8000").status_code == 200
        assert client.get("/ui/login", HTTP_HOST="a1b2c3d4e5f6:8000").status_code == 400
        assert client.get("/ui/login").status_code == 301
        assert client.post("/healthz").status_code == 405
        with patch("licenses.views.health.cache.set", side_effect=RuntimeError("private")):
            response = client.get("/healthz", HTTP_HOST="a1b2c3d4e5f6:8000")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}

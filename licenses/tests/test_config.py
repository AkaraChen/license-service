"""SPEC 17.8 host lifecycle: config_invalid and unreachable store prevent listen
(Sections 6.1, 6.4, 8). Exercised via subprocesses against real startup."""

import os
import subprocess
import sys
from pathlib import Path

BASE = str(Path(__file__).resolve().parents[2])


def run_manage(*args, **env_overrides):
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "LICENSE_STORE_ENGINE": "sqlite3",
        "LICENSE_STORE_NAME": str(Path(BASE) / "license_store.sqlite3"),
        **env_overrides,
    }
    env.pop("LICENSE_SESSION_SECRET", None) if "LICENSE_SESSION_SECRET" not in env_overrides else None
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        capture_output=True,
        text=True,
        cwd=BASE,
        env=env,
        timeout=60,
        check=False,
    )


def test_unknown_store_engine_is_config_invalid():
    out = run_manage("check", LICENSE_STORE_ENGINE="bogus-engine")
    assert out.returncode != 0
    assert "config_invalid" in (out.stderr + out.stdout)


def test_production_without_session_secret_is_config_invalid():
    out = run_manage("check", LICENSE_DEBUG="0")
    assert out.returncode != 0
    assert "config_invalid" in (out.stderr + out.stdout)
    assert "licenses.E001" in (out.stderr + out.stdout)


def test_production_with_session_secret_passes_check():
    out = run_manage(
        "check", LICENSE_DEBUG="0", LICENSE_SESSION_SECRET="x" * 50, LICENSE_ALLOWED_HOSTS="example.com"
    )
    assert out.returncode == 0, out.stderr + out.stdout


def test_unreachable_store_prevents_startup():
    """PostgreSQL engine with no server (and possibly no driver) must fail startup."""
    out = run_manage(
        "migrate",
        "--run-syncdb",
        LICENSE_STORE_ENGINE="postgresql",
        LICENSE_STORE_PORT="1",
        LICENSE_STORE_HOST="127.0.0.1",
    )
    assert out.returncode != 0


def test_sqlite_store_opens_and_migrates(tmp_path):
    db_file = tmp_path / "store.sqlite3"
    out = run_manage("migrate", LICENSE_STORE_NAME=str(db_file))
    assert out.returncode == 0, out.stderr
    assert db_file.exists()


def test_default_wsgi_profile_requires_secret_and_debug_is_loopback_only():
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings"}
    env.pop("LICENSE_DEBUG", None)
    env.pop("LICENSE_SESSION_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", "import config.wsgi"],
        cwd=BASE,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "LICENSE_SESSION_SECRET is required" in result.stderr
    result = run_manage("check", LICENSE_DEBUG="1", LICENSE_LISTEN_HOST="0.0.0.0")
    assert result.returncode != 0
    assert "debug mode requires a loopback listener" in result.stderr


def test_production_http_redirect_and_cookie_flags(tmp_path):
    env = {
        "LICENSE_DEBUG": "0",
        "LICENSE_SESSION_SECRET": "test-only-production-secret-" * 3,
        "LICENSE_ALLOWED_HOSTS": "127.0.0.1,testserver",
        "LICENSE_TRUST_PROXY": "1",
        "LICENSE_STORE_ENGINE": "sqlite3",
        "LICENSE_STORE_NAME": str(tmp_path / "production.sqlite3"),
    }
    assert run_manage("migrate", **env).returncode == 0
    # Real WSGI HTTP requests: direct plaintext redirects before any account write;
    # the explicitly trusted local edge header selects the HTTPS cookie profile.
    probe = r"""
import json, threading, urllib.request, urllib.error
from wsgiref.simple_server import make_server
from config.wsgi import application
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
server = make_server("127.0.0.1", 0, application)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = "http://127.0.0.1:" + str(server.server_port)
try:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(base + "/ui/login")
        raise AssertionError("plaintext reached app")
    except urllib.error.HTTPError as exc:
        assert exc.code == 301 and exc.headers["Location"].startswith("https://")
    from django.contrib.auth.models import User
    User.objects.create_user("test-customer", password="test-password")
    request = urllib.request.Request(base + "/api/auth/login", data=json.dumps({"username":"test-customer","password":"test-password"}).encode(), headers={"Content-Type":"application/json", "X-Forwarded-Proto":"https"})
    with opener.open(request) as response:
        assert response.status == 200
        cookies = response.headers.get_all("Set-Cookie")
        assert any(c.startswith("sessionid=") and "Secure" in c and "HttpOnly" in c for c in cookies)
        assert any(c.startswith("csrftoken=") and "Secure" in c for c in cookies)
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    request = urllib.request.Request(base + "/api/auth/register", data=b'{"username":"\\ud800","password":"pw"}', headers={"Content-Type":"application/json", "X-Forwarded-Proto":"https"})
    try:
        opener.open(request)
        raise AssertionError("invalid Unicode accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400 and json.load(exc)["error"] == "validation_error"
finally:
    server.shutdown()
    server.server_close()
    thread.join()
"""
    result = run_manage("shell", "-c", probe, **env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_security_migration_refuses_duplicate_identities_and_retires_sessions(tmp_path):
    env = {"LICENSE_DEBUG": "1", "LICENSE_STORE_NAME": str(tmp_path / "upgrade.sqlite3")}
    assert run_manage("migrate", **env).returncode == 0
    assert run_manage("migrate", "licenses", "0002", **env).returncode == 0
    seed = """
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
User.objects.create(username='Alice')
User.objects.create(username='alice')
session = SessionStore()
session['_issued_license_keys_once'] = ['legacy-plaintext']
session.save()
"""
    assert run_manage("shell", "-c", seed, **env).returncode == 0
    rejected = run_manage("migrate", **env)
    assert rejected.returncode != 0
    assert "Resolve case-insensitive duplicate usernames" in rejected.stderr
    repair = """
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
assert User.objects.count() == 2
assert Session.objects.count() == 1
User.objects.get(username='alice').delete()
"""
    assert run_manage("shell", "-c", repair, **env).returncode == 0
    assert run_manage("migrate", **env).returncode == 0
    verify = """
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
assert User.objects.count() == 1
assert not Session.objects.exists()
"""
    result = run_manage("shell", "-c", verify, **env)
    assert result.returncode == 0, result.stderr

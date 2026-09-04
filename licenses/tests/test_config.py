"""SPEC 17.8 host lifecycle: config_invalid and unreachable store prevent listen
(Sections 6.1, 6.4, 8). Exercised via subprocesses against real startup."""
import os
import subprocess
import sys

BASE = "/workspace"


def run_manage(*args, **env_overrides):
    env = {**os.environ, **env_overrides}
    env.pop("LICENSE_SESSION_SECRET", None) if "LICENSE_SESSION_SECRET" not in env_overrides else None
    return subprocess.run([sys.executable, "manage.py", *args], capture_output=True,
                          text=True, cwd=BASE, env=env, timeout=60)


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
    out = run_manage("check", LICENSE_DEBUG="0",
                     LICENSE_SESSION_SECRET="x" * 50, LICENSE_ALLOWED_HOSTS="example.com")
    assert out.returncode == 0, out.stderr + out.stdout


def test_unreachable_store_prevents_startup():
    """PostgreSQL engine with no server (and possibly no driver) must fail startup."""
    out = run_manage("migrate", "--run-syncdb", LICENSE_STORE_ENGINE="postgresql",
                     LICENSE_STORE_PORT="1", LICENSE_STORE_HOST="127.0.0.1")
    assert out.returncode != 0


def test_sqlite_store_opens_and_migrates(tmp_path):
    db_file = tmp_path / "store.sqlite3"
    out = run_manage("migrate", LICENSE_STORE_NAME=str(db_file))
    assert out.returncode == 0, out.stderr
    assert db_file.exists()

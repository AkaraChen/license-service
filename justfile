# License Service
#
#   just serve        start locally with Tailwind watcher (default 127.0.0.1:8000)
#   just css          rebuild production CSS
#   just messages     compile gettext catalogs
#   just superuser    bootstrap the only Admin account
#   just test         run the pytest suite

host := env("LICENSE_LISTEN_HOST", "127.0.0.1")
port := env("LICENSE_LISTEN_PORT", "8000")

# List recipes
default:
    @just --list

# Create .venv and sync locked dependencies
setup:
    uv sync

# Apply store migrations
migrate:
    uv run python manage.py migrate

# Bootstrap the only Admin (createsuperuser is the only way)
superuser:
    uv run python manage.py createsuperuser

# Run Django preflight checks
check:
    uv run python manage.py check

# Compile gettext catalogs (ignore site-packages)
messages:
    uv run python manage.py compilemessages --ignore .venv

# Production CSS build (standalone Tailwind CLI, no Node)
css:
    uv run python manage.py tailwind build

# Migrate and start the service with a Tailwind watcher
serve:
    LICENSE_DEBUG=1 uv run python manage.py migrate
    LICENSE_DEBUG=1 uv run python manage.py tailwind runserver {{ host }}:{{ port }}

alias run := serve
alias start := serve

# Pass through a Django management command: just manage shell
manage *args:
    uv run python manage.py {{ args }}

# Run the pytest suite
test *args:
    LICENSE_DEBUG=1 uv run pytest {{ args }}

# Format with ruff
fmt:
    uv run ruff format .

# Lint (format check + ruff)
lint:
    uv run ruff format --check .
    uv run ruff check .

#!/bin/sh
set -eu
if [ "${1:-}" = "gunicorn" ]; then
    python manage.py check
    python manage.py migrate --noinput
fi
exec "$@"

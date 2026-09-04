from django.apps import AppConfig
from django.core.checks import Error, register


class LicensesConfig(AppConfig):
    name = "licenses"


@register("config")
def config_check(app_configs, **kwargs):
    """Preflight (Section 6.4): config_invalid or an unreachable store refuses
    startup before listen. Runs with `manage.py check` and every runserver."""
    from django.conf import settings

    if not settings.DEBUG and settings.SECRET_KEY == settings.DEV_SECRET_KEY:
        return [
            Error(
                "config_invalid: LICENSE_SESSION_SECRET must be set when "
                "LICENSE_DEBUG=0 (no hardcoded production default).",
                id="licenses.E001",
            )
        ]
    try:
        from django.db import connections

        connections["default"].ensure_connection()
    except Exception as exc:  # noqa: BLE001 - preflight must catch any driver/connection error
        return [
            Error(f"store_unavailable: cannot open the License Store at startup: {exc}", id="licenses.E002")
        ]
    return []

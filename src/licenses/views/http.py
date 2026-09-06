"""Ninja API instance and session authenticators."""

from ninja import NinjaAPI
from ninja.security import SessionAuth


class LicenseAPI(NinjaAPI):
    # Public Ninja hook: keep the SPEC operation names without repeating 25 IDs.
    def get_openapi_operation_id(self, operation):
        return operation.view_func.__name__


api = LicenseAPI(title="License Service", version="3.0.0", openapi_url="/openapi.json", docs_url="/docs")

customer_session = SessionAuth(csrf=False)
admin_session = SessionAuth(csrf=False)

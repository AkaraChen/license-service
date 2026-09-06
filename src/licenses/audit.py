"""Request audit and the existing JSON browser policy for all HTTP adapters."""

import json
import logging
import re
import uuid

from django.http import JsonResponse

log = logging.getLogger("licenses.api")


def request_id(request):
    supplied = request.headers.get("X-Request-ID", "")
    return supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else uuid.uuid4().hex


def emit(operation, context):
    # JSON values cannot inject a new log line or counterfeit sibling fields.
    try:
        log.info(json.dumps({"op": operation, **context}, ensure_ascii=True, separators=(",", ":")))
    except Exception:  # noqa: BLE001 - sink failures must not change a committed mutation
        pass


def resources(request, **fields):
    if hasattr(request, "audit_context"):
        request.audit_context.update(fields)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        request.audit_context = {"rid": request_id(request), "actor": "anonymous"}
        if user.is_authenticated:
            request.audit_context.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        is_api = request.path.startswith("/api/")
        if request.path in {"/api/activate", "/api/validate"}:
            request.audit_context["actor"] = "application"
        response = self.get_response(request)
        if request.path.startswith("/api/") and response.status_code == 405:
            return JsonResponse(
                {"error": "validation_error", "message": "Method not allowed."},
                status=405,
                headers={"Allow": response.get("Allow", "")},
            )
        if request.method not in {"POST", "PATCH", "DELETE"}:
            return response
        match = request.resolver_match
        if match is None:
            return response
        context = request.audit_context
        if context["actor"] == "anonymous" and request.user.is_authenticated:
            context.update(actor="admin" if request.user.is_staff else "customer", account_id=request.user.pk)
        if (
            response.status_code == 302
            and context["actor"] == "anonymous"
            and "login" in response.get("Location", "")
        ):
            context.setdefault("outcome", "unauthenticated")
        template_context = getattr(response, "context_data", None) or {}
        form = template_context.get("form") or template_context.get("adminform")
        if hasattr(form, "form"):
            form = form.form
        invalid = bool(form is not None and getattr(form, "errors", None))
        context.setdefault(
            "outcome",
            "validation_error"
            if invalid
            else ("success" if response.status_code < 400 else f"http_{response.status_code}"),
        )
        context["status"] = response.status_code
        for field in ("device_id", "entitlement_id"):
            if field in match.kwargs:
                context[field] = match.kwargs[field]
        object_id = match.kwargs.get("object_id", "")
        if str(object_id).isdigit():
            context["object_id"] = int(object_id)
        if is_api:
            context.update(method=request.method, path=request.path)
        emit(match.url_name if is_api else match.view_name, context)
        return response

    def process_view(self, request, view, args, kwargs):
        # SPEC's JSON clients use same-origin checks instead of CSRF tokens.
        if not request.path.startswith("/api/") or request.method not in {"POST", "PATCH"}:
            return None
        origin = request.headers.get("Origin")
        if request.path not in {"/api/activate", "/api/validate"} and origin is not None:
            if origin != f"{request.scheme}://{request.get_host()}":
                resources(request, outcome="forbidden")
                return JsonResponse(
                    {"error": "forbidden", "message": "Cross-origin writes are not allowed."}, status=403
                )
        if request.content_type != "application/json":
            resources(request, outcome="validation_error")
            return JsonResponse(
                {"error": "validation_error", "message": "Write bodies must be application/json."}, status=400
            )
        return None

"""Customer HTML pages (SPEC 3.1.4): register, login, logout, redeem,
entitlement list, device list/unbind/rename. Bind happens in the licensed
application (JSON API), not on these pages. Form posts invoke the same
accounts.py/services.py mutations as the JSON operations (5.1.1). The Admin console is
Django Admin at /admin/ and is never linked or exposed here.
"""

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from . import accounts, audit, services
from .models import Device, Entitlement
from .services import Failure


def _safe_next(request):
    """Return-to URL after login/register. Honors `next` (Django login_required)
    and `redirect`. Rejects off-site and /admin targets."""
    for key in ("next", "redirect"):
        candidate = request.POST.get(key) or request.GET.get(key)
        if not candidate:
            continue
        path = candidate.split("?", 1)[0]
        if path.startswith("/admin") or path in {"/ui/login", "/ui/register"}:
            continue
        if url_has_allowed_host_and_scheme(
            url=candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return candidate
    return None


def _fail(view):
    """On Failure, render the error page with the message (no partial mutation)."""

    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except (Failure, Http404) as exc:
            error = exc.message if isinstance(exc, Failure) else _("Not found.")
            audit.resources(request, outcome=exc.error if isinstance(exc, Failure) else "not_found")
            return render(request, "licenses/error.html", {"error": error}, status=400)

    return wrapped


def register_page(request):
    nxt = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(nxt or "ui_home")
    if request.method == "POST":
        try:
            user = accounts.register_account(
                request.POST.get("username"), request.POST.get("password"), request=request
            )
        except Failure as exc:
            audit.resources(request, outcome=exc.error)
            return render(request, "licenses/register.html", {"error": exc.message, "next": nxt})
        audit.resources(request, actor="admin" if user.is_staff else "customer", account_id=user.pk)
        login(request, user, backend="licenses.accounts.CaseInsensitiveBackend")
        return redirect(nxt or "ui_home")
    return render(request, "licenses/register.html", {"next": nxt})


class CustomerLoginView(LoginView):
    template_name = "licenses/login.html"
    next_page = "ui_home"
    redirect_authenticated_user = True

    def get_redirect_url(self):
        return _safe_next(self.request) or ""

    def form_invalid(self, form):
        audit.resources(self.request, outcome="unauthenticated")
        return super().form_invalid(form)


@login_required(login_url="ui_login")
def home(request):
    return render(request, "licenses/home.html", {"entitlements": request.user.entitlements.order_by("pk")})


@login_required(login_url="ui_login")
@_fail
def redeem_page(request):
    if request.method == "POST":
        entitlement, _ = services.redeem(request.user, request.POST.get("license_key", ""))
        audit.resources(request, entitlement_id=entitlement.pk, product_id=entitlement.product_id)
        return redirect("ui_home")
    return render(request, "licenses/redeem.html")


@login_required(login_url="ui_login")
@require_GET
@_fail
def entitlement_page(request, entitlement_id):
    entitlement = get_object_or_404(Entitlement, pk=entitlement_id, account=request.user)
    bound = entitlement.devices.filter(status="bound").count()
    return render(
        request,
        "licenses/entitlement.html",
        {
            "entitlement": entitlement,
            "devices": entitlement.devices.order_by("pk"),
            "seats_used": bound,
            "seats_available": max(0, entitlement.max_devices - bound),
        },
    )


@login_required(login_url="ui_login")
@require_POST
@_fail
def unbind_page(request, device_id):
    device = get_object_or_404(Device, pk=device_id, entitlement__account=request.user)
    services.unbind(device)
    audit.resources(request, entitlement_id=device.entitlement_id, product_id=device.entitlement.product_id)
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)


@login_required(login_url="ui_login")
@require_POST
@_fail
def rename_page(request, device_id):
    device = get_object_or_404(Device, pk=device_id, entitlement__account=request.user)
    services.rename_device(device, request.POST.get("display_name"))
    audit.resources(request, entitlement_id=device.entitlement_id, product_id=device.entitlement.product_id)
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)

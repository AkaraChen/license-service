"""Customer HTML pages (SPEC 3.1.4): register, login, logout, redeem,
entitlement list, device list/bind/unbind/rename. Form posts invoke the same
services.py mutations as the JSON operations (5.1.1). The Admin console is
Django Admin at /admin/ and is never linked or exposed here.
"""

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import services
from .models import Device, Entitlement
from .services import Failure


def _fail(view):
    """On Failure, render the error page with the message (no partial mutation)."""

    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Failure as exc:
            return render(request, "licenses/error.html", {"error": exc.message}, status=400)

    return wrapped


def register_page(request):
    if request.method == "POST":
        try:
            user = services.register_account(request.POST.get("username"), request.POST.get("password"))
        except Failure as exc:
            return render(request, "licenses/register.html", {"error": exc.message})
        login(request, user)
        return redirect("ui_home")
    return render(request, "licenses/register.html")


def login_page(request):
    if request.method == "POST":
        try:
            user = services.authenticate_account(
                request, request.POST.get("username"), request.POST.get("password")
            )
        except Failure as exc:
            return render(request, "licenses/login.html", {"error": exc.message})
        login(request, user)
        return redirect("ui_home")
    return render(request, "licenses/login.html")


@require_POST
def logout_page(request):
    logout(request)
    return redirect("ui_login")


@login_required(login_url="ui_login")
def home(request):
    return render(request, "licenses/home.html", {"entitlements": request.user.entitlements.order_by("pk")})


@login_required(login_url="ui_login")
@_fail
def redeem_page(request):
    if request.method == "POST":
        services.redeem(request.user, request.POST.get("license_key", ""))
        return redirect("ui_home")
    return render(request, "licenses/redeem.html")


def _own(model, pk, user):
    """Invariant 6 for the pages: foreign rows render the error page."""
    obj = model.objects.filter(pk=pk).first()
    if (
        obj is None
        or (hasattr(obj, "account_id") and obj.account_id != user.pk)
        or (hasattr(obj, "entitlement") and obj.entitlement.account_id != user.pk)
    ):
        raise Failure("not_found", _("Not found."))
    return obj


@login_required(login_url="ui_login")
@_fail
def entitlement_page(request, entitlement_id):
    entitlement = _own(Entitlement, entitlement_id, request.user)
    if request.method == "POST":
        services.bind(
            entitlement, request.POST.get("device_fingerprint", ""), request.POST.get("display_name") or None
        )
        return redirect("ui_entitlement", entitlement_id=entitlement.pk)
    bound = entitlement.devices.filter(status="bound").count()
    return render(
        request,
        "licenses/entitlement.html",
        {
            "entitlement": entitlement,
            "devices": entitlement.devices.order_by("pk"),
            "seats_used": bound,
            "seats_free": entitlement.max_devices - bound,
        },
    )


@login_required(login_url="ui_login")
@require_POST
@_fail
def unbind_page(request, device_id):
    device = _own(Device, device_id, request.user)
    services.unbind(device)
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)


@login_required(login_url="ui_login")
@require_POST
@_fail
def rename_page(request, device_id):
    device = _own(Device, device_id, request.user)
    device.display_name = request.POST.get("display_name") or None
    device.save(update_fields=("display_name",))
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)

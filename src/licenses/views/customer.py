"""Customer HTML pages (SPEC 3.1.4): register, login, logout, redeem,
entitlement list, device list/unbind/rename. Bind happens in the licensed
application (JSON API), not on these pages. Form posts invoke the same
accounts.py/services.py mutations as the JSON operations (5.1.1). The Admin console is
Django Admin at /admin/ and is never linked or exposed here.
"""

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET, require_POST

from .. import accounts, audit, services
from ..models import Device, Entitlement
from ..services import Failure
from .forms import DeviceNameForm, RedeemForm, RegistrationForm


def _entitlement_response(request, entitlement, *, error=None, rename_forms=None, status=200):
    forms = rename_forms or {}
    rows = [
        (d, forms.get(d.pk) or DeviceNameForm(initial={"display_name": d.display_name}))
        for d in entitlement.devices.order_by("pk")
    ]
    return render(
        request,
        "licenses/entitlement.html",
        {"entitlement": entitlement, "devices": rows, "error": error},
        status=status,
    )


def register_page(request):
    if request.user.is_authenticated:
        return redirect("ui_home")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            user = accounts.register_account(**form.cleaned_data, request=request)
        except Failure as exc:
            audit.resources(request, outcome=exc.error)
            form.add_error(None, exc.message)
        else:
            audit.resources(request, actor="customer", account_id=user.pk)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("ui_home")
    return TemplateResponse(
        request,
        "licenses/register.html",
        {"form": form},
        status=400 if form.errors else 200,
    )


class CustomerLoginView(LoginView):
    template_name = "licenses/login.html"
    next_page = "ui_home"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        audit.resources(self.request, outcome="unauthenticated")
        return super().form_invalid(form)


@login_required(login_url="ui_login")
def home(request):
    return render(request, "licenses/home.html", {"entitlements": request.user.entitlements.order_by("pk")})


@login_required(login_url="ui_login")
def redeem_page(request):
    form = RedeemForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            entitlement, _ = services.redeem(request.user, form.cleaned_data["license_key"])
        except Failure as exc:
            audit.resources(request, outcome=exc.error)
            form.add_error(None, exc.message)
        else:
            audit.resources(request, entitlement_id=entitlement.pk, product_id=entitlement.product_id)
            return redirect("ui_home")
    return TemplateResponse(
        request, "licenses/redeem.html", {"form": form}, status=400 if form.errors else 200
    )


@login_required(login_url="ui_login")
@require_GET
def entitlement_page(request, entitlement_id):
    entitlement = get_object_or_404(Entitlement, pk=entitlement_id, account=request.user)
    return _entitlement_response(request, entitlement)


@login_required(login_url="ui_login")
@require_POST
def unbind_page(request, device_id):
    device = get_object_or_404(Device, pk=device_id, entitlement__account=request.user)
    try:
        services.unbind(device)
    except Failure as exc:
        audit.resources(request, outcome=exc.error)
        return _entitlement_response(request, device.entitlement, error=exc.message, status=400)
    audit.resources(request, entitlement_id=device.entitlement_id, product_id=device.entitlement.product_id)
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)


@login_required(login_url="ui_login")
@require_POST
def rename_page(request, device_id):
    device = get_object_or_404(Device, pk=device_id, entitlement__account=request.user)
    form = DeviceNameForm(request.POST)
    if not form.is_valid():
        audit.resources(request, outcome="validation_error")
        return _entitlement_response(
            request, device.entitlement, rename_forms={device.pk: form}, status=400
        )
    try:
        services.rename_device(device, **form.cleaned_data)
    except Failure as exc:
        audit.resources(request, outcome=exc.error)
        form.add_error(None, exc.message)
        return _entitlement_response(
            request, device.entitlement, rename_forms={device.pk: form}, status=400
        )
    audit.resources(request, entitlement_id=device.entitlement_id, product_id=device.entitlement.product_id)
    return redirect("ui_entitlement", entitlement_id=device.entitlement_id)

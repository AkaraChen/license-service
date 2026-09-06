"""Shared registration rules, enforced by django-ratelimit in Redis."""

from django.conf import settings
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from . import audit


@ratelimit(
    group="registration.global",
    key=lambda g, r: "all",
    rate=lambda g, r: f"{settings.LICENSE_REGISTRATION_GLOBAL_LIMIT}/h",
)
@ratelimit(
    group="registration.source", key="ip", rate=lambda g, r: f"{settings.LICENSE_REGISTRATION_SOURCE_LIMIT}/h"
)
def admit_registration(request):
    pass


def ratelimited(request, exception):
    audit.resources(request, outcome="rate_limited")
    return render(
        request,
        "licenses/error.html",
        {"error": "Registration limit reached. Please try again later."},
        status=429,
    )

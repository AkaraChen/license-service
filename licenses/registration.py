"""Shared registration rules, enforced by django-ratelimit in Redis."""

from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from . import audit


@ratelimit(group="registration.global", key=lambda g, r: "all", rate="100/h")
@ratelimit(group="registration.source", key="ip", rate="5/h")
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

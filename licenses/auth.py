"""Account-name normalization; login throttling belongs to django-axes."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Value
from django.db.models.functions import Lower


def canonical_username(request, credentials):
    username = ((credentials or {}).get("username") or "").strip()
    account = (
        get_user_model()
        .objects.alias(canonical=Lower("username"))
        .filter(canonical=Lower(Value(username)))
        .first()
    )
    return account.username if account is not None else username


class CaseInsensitiveBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        return super().authenticate(
            request, username=canonical_username(request, {"username": username}), password=password, **kwargs
        )


def lockout_response(request, response, credentials=None):
    # Keep the adapters' generic invalid-credentials response, including Admin.
    return response

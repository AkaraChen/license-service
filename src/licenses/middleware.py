from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure(request, reason=""):
    from .services.errors import Forbidden

    if not request.path.startswith("/api/"):
        return django_csrf_failure(request, reason=reason)
    return JsonResponse(Forbidden("CSRF verification failed.").envelope(), status=403)

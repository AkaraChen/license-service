from django.http import JsonResponse


class JsonWritePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and response.status_code == 405:
            return JsonResponse(
                {"error": "validation_error", "message": "Method not allowed."},
                status=405,
                headers={"Allow": response.get("Allow", "")},
            )
        return response

    def process_view(self, request, view, args, kwargs):
        if not request.path.startswith("/api/") or request.method not in {"POST", "PATCH"}:
            return None
        from .services import Failure
        from .views.http import api_error

        origin = request.headers.get("Origin")
        if request.path not in {"/api/activate", "/api/validate"} and origin is not None:
            if origin != f"{request.scheme}://{request.get_host()}":
                return api_error(request, Failure("forbidden", "Cross-origin writes are not allowed."))
        if request.content_type != "application/json":
            return api_error(request, Failure("validation_error", "Write bodies must be application/json."))
        return None

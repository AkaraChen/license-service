"""JSON machine API: explicit Django views with inline validation and responses.

The adjacent openapi attributes describe views for documentation only.
"""

import json

from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.core.exceptions import RequestDataTooBig
from django.db import DataError, IntegrityError, OperationalError
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from . import audit, services
from .models import Device, Entitlement, LicenseKey, Product
from .services import Failure

HTTP_STATUS = {
    "validation_error": 400,
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "unknown_key": 404,
    "unknown_device": 404,
    "conflict": 409,
    "already_entitled": 409,
    "key_already_redeemed": 409,
    "key_revoked": 409,
    "seat_exhausted": 409,
    "entitlement_suspended": 409,
    "entitlement_revoked": 409,
    "entitlement_expired": 409,
    "store_unavailable": 503,
    "rate_limited": 429,
}


@csrf_exempt
def register(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "register"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"password", "username"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "username" not in data:
            raise Failure("validation_error", "Missing required field: username.")
        if type(data["username"]) is not str:
            raise Failure("validation_error", "Field username has an invalid value.")
        if "password" not in data:
            raise Failure("validation_error", "Missing required field: password.")
        if type(data["password"]) is not str:
            raise Failure("validation_error", "Field password has an invalid value.")
        user = services.register_account(data["username"], data["password"], request=request)
        ctx.update(actor="customer", account_id=user.pk)
        response = JsonResponse(
            {
                "account": {
                    "account_id": user.pk,
                    "username": user.username,
                    "is_admin": user.is_staff,
                    "email": user.email or None,
                    "created_at": user.date_joined.isoformat(),
                }
            },
            status=201,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


register.openapi = {
    "POST": {
        "operationId": "register",
        "auth": "anonymous",
        "fields": (("username", "str", True), ("password", "str", True)),
    }
}


@csrf_exempt
def login_op(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "login"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"password", "username"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "username" not in data:
            raise Failure("validation_error", "Missing required field: username.")
        if type(data["username"]) is not str:
            raise Failure("validation_error", "Field username has an invalid value.")
        if "password" not in data:
            raise Failure("validation_error", "Missing required field: password.")
        if type(data["password"]) is not str:
            raise Failure("validation_error", "Field password has an invalid value.")
        user = services.authenticate_account(request, data["username"], data["password"])
        login(request, user)
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        response = JsonResponse(
            {
                "account": {
                    "account_id": user.pk,
                    "username": user.username,
                    "is_admin": user.is_staff,
                    "email": user.email or None,
                    "created_at": user.date_joined.isoformat(),
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


login_op.openapi = {
    "POST": {
        "operationId": "login",
        "auth": "anonymous",
        "fields": (("username", "str", True), ("password", "str", True)),
    }
}


@csrf_exempt
def logout_op(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "logout"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(data)
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        logout(request)
        response = JsonResponse({"ok": True}, status=200)
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


logout_op.openapi = {"POST": {"operationId": "logout", "auth": "session", "fields": ()}}


@csrf_exempt
def products(request):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_products" if request.method == "GET" else "create_product"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.method in ("POST", "PATCH"):
            origin = request.headers.get("Origin")
            if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
                raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.method == "GET":
            response = JsonResponse(
                {
                    "products": [
                        {
                            "product_id": item.pk,
                            "code": item.code,
                            "name": item.name,
                            "created_at": item.created_at.isoformat(),
                        }
                        for item in Product.objects.order_by("pk")
                    ]
                },
                status=200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
        else:
            if request.content_type != "application/json":
                raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
            if not request.body:
                data = {}
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, RecursionError):
                    raise Failure("validation_error", "Body must be a JSON object.")
            if not isinstance(data, dict):
                raise Failure("validation_error", "Body must be a JSON object.")
            for field, value in data.items():
                services.validate_text(field)
                if isinstance(value, str):
                    services.validate_text(value)
                elif isinstance(value, (list, dict)):
                    raise Failure("validation_error", "Nested values are not supported.")
            unknown = sorted(set(data) - {"code", "name"})
            if unknown:
                raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
            if "code" not in data:
                raise Failure("validation_error", "Missing required field: code.")
            if type(data["code"]) is not str:
                raise Failure("validation_error", "Field code has an invalid value.")
            if "name" not in data:
                raise Failure("validation_error", "Missing required field: name.")
            if type(data["name"]) is not str:
                raise Failure("validation_error", "Field name has an invalid value.")
            code = data["code"].strip()
            if not code:
                raise Failure("validation_error", "code must not be empty.")
            if Product.objects.filter(code__iexact=code).exists():
                raise Failure("conflict", "A product with this code already exists.")
            product = Product.objects.create(code=code, name=data["name"])
            ctx["product_id"] = product.pk
            response = JsonResponse(
                {
                    "product": {
                        "product_id": product.pk,
                        "code": product.code,
                        "name": product.name,
                        "created_at": product.created_at.isoformat(),
                    }
                },
                status=201,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


products.openapi = {
    "GET": {"operationId": "list_products", "auth": "admin", "fields": ()},
    "POST": {
        "operationId": "create_product",
        "auth": "admin",
        "fields": (("code", "str", True), ("name", "str", True)),
    },
}


@csrf_exempt
def product_detail(request, pk):
    if request.method not in ("GET", "PATCH"):
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "get_product" if request.method == "GET" else "update_product"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.method in ("POST", "PATCH"):
            origin = request.headers.get("Origin")
            if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
                raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.method == "GET":
            product = Product.objects.filter(pk=pk).first()
            if product is None:
                raise Failure("not_found", "Unknown product id.")
            response = JsonResponse(
                {
                    "product": {
                        "product_id": product.pk,
                        "code": product.code,
                        "name": product.name,
                        "created_at": product.created_at.isoformat(),
                    }
                },
                status=200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
        else:
            if request.content_type != "application/json":
                raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
            if not request.body:
                data = {}
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, RecursionError):
                    raise Failure("validation_error", "Body must be a JSON object.")
            if not isinstance(data, dict):
                raise Failure("validation_error", "Body must be a JSON object.")
            for field, value in data.items():
                services.validate_text(field)
                if isinstance(value, str):
                    services.validate_text(value)
                elif isinstance(value, (list, dict)):
                    raise Failure("validation_error", "Nested values are not supported.")
            unknown = sorted(set(data) - {"name"})
            if unknown:
                raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
            if "name" in data:
                if type(data["name"]) is not str:
                    raise Failure("validation_error", "Field name has an invalid value.")
            product = Product.objects.filter(pk=pk).first()
            if product is None:
                raise Failure("not_found", "Unknown product id.")
            if "name" in data:
                product.name = data["name"]
                product.save(update_fields=("name",))
            ctx["product_id"] = product.pk
            response = JsonResponse(
                {
                    "product": {
                        "product_id": product.pk,
                        "code": product.code,
                        "name": product.name,
                        "created_at": product.created_at.isoformat(),
                    }
                },
                status=200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


product_detail.openapi = {
    "GET": {"operationId": "get_product", "auth": "admin", "fields": ()},
    "PATCH": {"operationId": "update_product", "auth": "admin", "fields": (("name", "str", False),)},
}


@csrf_exempt
def license_keys(request):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_license_keys" if request.method == "GET" else "issue_license_key"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.method in ("POST", "PATCH"):
            origin = request.headers.get("Origin")
            if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
                raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.method == "GET":
            response = JsonResponse(
                {
                    "license_keys": [
                        {
                            "key_id": item.pk,
                            "product_id": item.product_id,
                            "key_prefix": item.key_prefix,
                            "max_devices": item.max_devices,
                            "expires_at": item.expires_at.isoformat()
                            if item.expires_at is not None
                            else None,
                            "status": item.status,
                            "redeemed_by_account_id": item.redeemed_by_id,
                            "created_at": item.created_at.isoformat(),
                        }
                        for item in LicenseKey.objects.order_by("pk")
                    ]
                },
                status=200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
        else:
            if request.content_type != "application/json":
                raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
            if not request.body:
                data = {}
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, RecursionError):
                    raise Failure("validation_error", "Body must be a JSON object.")
            if not isinstance(data, dict):
                raise Failure("validation_error", "Body must be a JSON object.")
            for field, value in data.items():
                services.validate_text(field)
                if isinstance(value, str):
                    services.validate_text(value)
                elif isinstance(value, (list, dict)):
                    raise Failure("validation_error", "Nested values are not supported.")
            unknown = sorted(set(data) - {"max_devices", "product_id", "expires_at"})
            if unknown:
                raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
            if "product_id" not in data:
                raise Failure("validation_error", "Missing required field: product_id.")
            if type(data["product_id"]) is not int:
                raise Failure("validation_error", "Field product_id has an invalid value.")
            if "max_devices" not in data:
                raise Failure("validation_error", "Missing required field: max_devices.")
            if type(data["max_devices"]) is not int:
                raise Failure("validation_error", "Field max_devices has an invalid value.")
            if "expires_at" in data:
                if not (data["expires_at"] is None or type(data["expires_at"]) is str):
                    raise Failure("validation_error", "Field expires_at has an invalid value.")
                try:
                    parsed = parse_datetime(data["expires_at"]) if data["expires_at"] is not None else None
                except (ValueError, OverflowError):
                    parsed = None
                if data["expires_at"] is not None and parsed is None:
                    raise Failure("validation_error", "Field expires_at has an invalid value.")
                data["expires_at"] = parsed
            product = Product.objects.filter(pk=data["product_id"]).first()
            if product is None:
                raise Failure("not_found", "Unknown product id.")
            key, plaintext = services.issue_key(product, data["max_devices"], data.get("expires_at"))
            ctx["product_id"] = product.pk
            response = JsonResponse(
                {
                    "key": {
                        "key_id": key.pk,
                        "product_id": key.product_id,
                        "key_prefix": key.key_prefix,
                        "max_devices": key.max_devices,
                        "expires_at": key.expires_at.isoformat() if key.expires_at is not None else None,
                        "status": key.status,
                        "redeemed_by_account_id": key.redeemed_by_id,
                        "created_at": key.created_at.isoformat(),
                    },
                    "license_key": plaintext,
                },
                status=201,
            )
            response["Cache-Control"] = "no-store, private"
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


license_keys.openapi = {
    "GET": {"operationId": "list_license_keys", "auth": "admin", "fields": ()},
    "POST": {
        "operationId": "issue_license_key",
        "auth": "admin",
        "fields": (("product_id", "int", True), ("max_devices", "int", True), ("expires_at", "dt?", False)),
    },
}


@csrf_exempt
def revoke_license_key(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "revoke_license_key"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(data)
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        key = LicenseKey.objects.filter(pk=pk).first()
        if key is None:
            raise Failure("not_found", "Unknown licensekey id.")
        key = services.revoke_key(key)
        ctx["product_id"] = key.product_id
        response = JsonResponse(
            {
                "key": {
                    "key_id": key.pk,
                    "product_id": key.product_id,
                    "key_prefix": key.key_prefix,
                    "max_devices": key.max_devices,
                    "expires_at": key.expires_at.isoformat() if key.expires_at is not None else None,
                    "status": key.status,
                    "redeemed_by_account_id": key.redeemed_by_id,
                    "created_at": key.created_at.isoformat(),
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


revoke_license_key.openapi = {"POST": {"operationId": "revoke_license_key", "auth": "admin", "fields": ()}}


@csrf_exempt
def set_entitlement_status(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "set_entitlement_status"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"status"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "status" not in data:
            raise Failure("validation_error", "Missing required field: status.")
        if type(data["status"]) is not str:
            raise Failure("validation_error", "Field status has an invalid value.")
        entitlement = Entitlement.objects.filter(pk=pk).first()
        if entitlement is None:
            raise Failure("not_found", "Unknown entitlement id.")
        if data["status"] not in ("active", "suspended", "revoked"):
            raise Failure("validation_error", "status must be active, suspended, or revoked.")
        entitlement.status = data["status"]
        entitlement.save(update_fields=("status",))
        ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
        response = JsonResponse(
            {
                "entitlement": {
                    "entitlement_id": entitlement.pk,
                    "account_id": entitlement.account_id,
                    "product_id": entitlement.product_id,
                    "max_devices": entitlement.max_devices,
                    "expires_at": entitlement.expires_at.isoformat()
                    if entitlement.expires_at is not None
                    else None,
                    "status": entitlement.status,
                    "source_key_id": entitlement.source_key_id,
                    "created_at": entitlement.created_at.isoformat(),
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


set_entitlement_status.openapi = {
    "POST": {"operationId": "set_entitlement_status", "auth": "admin", "fields": (("status", "str", True),)}
}


@csrf_exempt
def unbind_device(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "unbind_device"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(data)
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        device = Device.objects.filter(pk=pk).first()
        if device is None:
            raise Failure("not_found", "Unknown device id.")
        device = services.unbind(device)
        ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
        response = JsonResponse(
            {
                "device": {
                    "device_id": device.pk,
                    "entitlement_id": device.entitlement_id,
                    "device_fingerprint": device.device_fingerprint,
                    "display_name": device.display_name,
                    "bound_at": device.bound_at.isoformat(),
                    "status": device.status,
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


unbind_device.openapi = {"POST": {"operationId": "unbind_device", "auth": "admin", "fields": ()}}


@csrf_exempt
def list_accounts(request):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_accounts"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        response = JsonResponse(
            {
                "accounts": [
                    {
                        "account_id": item.pk,
                        "username": item.username,
                        "is_admin": item.is_staff,
                        "email": item.email or None,
                        "created_at": item.date_joined.isoformat(),
                    }
                    for item in User.objects.order_by("pk")
                ]
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


list_accounts.openapi = {"GET": {"operationId": "list_accounts", "auth": "admin", "fields": ()}}


@csrf_exempt
def list_entitlements(request):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_entitlements"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        response = JsonResponse(
            {
                "entitlements": [
                    {
                        "entitlement_id": item.pk,
                        "account_id": item.account_id,
                        "product_id": item.product_id,
                        "max_devices": item.max_devices,
                        "expires_at": item.expires_at.isoformat() if item.expires_at is not None else None,
                        "status": item.status,
                        "source_key_id": item.source_key_id,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in Entitlement.objects.order_by("pk")
                ]
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


list_entitlements.openapi = {"GET": {"operationId": "list_entitlements", "auth": "admin", "fields": ()}}


@csrf_exempt
def list_devices(request):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_devices"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        response = JsonResponse(
            {
                "devices": [
                    {
                        "device_id": item.pk,
                        "entitlement_id": item.entitlement_id,
                        "device_fingerprint": item.device_fingerprint,
                        "display_name": item.display_name,
                        "bound_at": item.bound_at.isoformat(),
                        "status": item.status,
                    }
                    for item in Device.objects.order_by("pk")
                ]
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


list_devices.openapi = {"GET": {"operationId": "list_devices", "auth": "admin", "fields": ()}}


@csrf_exempt
def get_account(request, pk):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "get_account"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        if not user.is_staff:
            raise Failure("forbidden", "Admin privileges required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        account = User.objects.filter(pk=pk).first()
        if account is None:
            raise Failure("not_found", "Unknown user id.")
        response = JsonResponse(
            {
                "account": {
                    "account_id": account.pk,
                    "username": account.username,
                    "is_admin": account.is_staff,
                    "email": account.email or None,
                    "created_at": account.date_joined.isoformat(),
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


get_account.openapi = {"GET": {"operationId": "get_account", "auth": "admin", "fields": ()}}


@csrf_exempt
def redeem_license_key(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "redeem_license_key"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"license_key"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "license_key" not in data:
            raise Failure("validation_error", "Missing required field: license_key.")
        if type(data["license_key"]) is not str:
            raise Failure("validation_error", "Field license_key has an invalid value.")
        entitlement, created = services.redeem(request.user, data["license_key"])
        ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk)
        response = JsonResponse(
            {
                "entitlement": {
                    "entitlement_id": entitlement.pk,
                    "account_id": entitlement.account_id,
                    "product_id": entitlement.product_id,
                    "max_devices": entitlement.max_devices,
                    "expires_at": entitlement.expires_at.isoformat()
                    if entitlement.expires_at is not None
                    else None,
                    "status": entitlement.status,
                    "source_key_id": entitlement.source_key_id,
                    "created_at": entitlement.created_at.isoformat(),
                }
            },
            status=201 if created else 200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


redeem_license_key.openapi = {
    "POST": {
        "operationId": "redeem_license_key",
        "auth": "session",
        "fields": (("license_key", "str", True),),
    }
}


@csrf_exempt
def list_my_entitlements(request):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_my_entitlements"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        response = JsonResponse(
            {
                "entitlements": [
                    {
                        "entitlement_id": e.pk,
                        "account_id": e.account_id,
                        "product_id": e.product_id,
                        "max_devices": e.max_devices,
                        "expires_at": e.expires_at.isoformat() if e.expires_at is not None else None,
                        "status": e.status,
                        "source_key_id": e.source_key_id,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in request.user.entitlements.order_by("pk")
                ]
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


list_my_entitlements.openapi = {
    "GET": {"operationId": "list_my_entitlements", "auth": "session", "fields": ()}
}


@csrf_exempt
def get_my_entitlement(request, pk):
    if request.method != "GET":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "get_my_entitlement"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        entitlement = Entitlement.objects.filter(pk=pk, account=request.user).first()
        if entitlement is None:
            raise Failure("not_found", "Not found.")
        response = JsonResponse(
            {
                "entitlement": {
                    "entitlement_id": entitlement.pk,
                    "account_id": entitlement.account_id,
                    "product_id": entitlement.product_id,
                    "max_devices": entitlement.max_devices,
                    "expires_at": entitlement.expires_at.isoformat()
                    if entitlement.expires_at is not None
                    else None,
                    "status": entitlement.status,
                    "source_key_id": entitlement.source_key_id,
                    "created_at": entitlement.created_at.isoformat(),
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


get_my_entitlement.openapi = {"GET": {"operationId": "get_my_entitlement", "auth": "session", "fields": ()}}


@csrf_exempt
def my_devices(request, pk):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "list_my_devices" if request.method == "GET" else "bind_my_device"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.method in ("POST", "PATCH"):
            origin = request.headers.get("Origin")
            if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
                raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.method == "GET":
            entitlement = Entitlement.objects.filter(pk=pk, account=request.user).first()
            if entitlement is None:
                raise Failure("not_found", "Not found.")
            response = JsonResponse(
                {
                    "devices": [
                        {
                            "device_id": d.pk,
                            "entitlement_id": d.entitlement_id,
                            "device_fingerprint": d.device_fingerprint,
                            "display_name": d.display_name,
                            "bound_at": d.bound_at.isoformat(),
                            "status": d.status,
                        }
                        for d in entitlement.devices.order_by("pk")
                    ]
                },
                status=200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
        else:
            if request.content_type != "application/json":
                raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
            if not request.body:
                data = {}
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, RecursionError):
                    raise Failure("validation_error", "Body must be a JSON object.")
            if not isinstance(data, dict):
                raise Failure("validation_error", "Body must be a JSON object.")
            for field, value in data.items():
                services.validate_text(field)
                if isinstance(value, str):
                    services.validate_text(value)
                elif isinstance(value, (list, dict)):
                    raise Failure("validation_error", "Nested values are not supported.")
            unknown = sorted(set(data) - {"display_name", "device_fingerprint"})
            if unknown:
                raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
            if "device_fingerprint" not in data:
                raise Failure("validation_error", "Missing required field: device_fingerprint.")
            if type(data["device_fingerprint"]) is not str:
                raise Failure("validation_error", "Field device_fingerprint has an invalid value.")
            if "display_name" in data:
                if not (data["display_name"] is None or type(data["display_name"]) is str):
                    raise Failure("validation_error", "Field display_name has an invalid value.")
            entitlement = Entitlement.objects.filter(pk=pk, account=request.user).first()
            if entitlement is None:
                raise Failure("not_found", "Not found.")
            device, created = services.bind(entitlement, data["device_fingerprint"], data.get("display_name"))
            ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk)
            response = JsonResponse(
                {
                    "device": {
                        "device_id": device.pk,
                        "entitlement_id": device.entitlement_id,
                        "device_fingerprint": device.device_fingerprint,
                        "display_name": device.display_name,
                        "bound_at": device.bound_at.isoformat(),
                        "status": device.status,
                    }
                },
                status=201 if created else 200,
            )
            ctx["outcome"] = "success"
            audit.emit(operation, ctx)
            return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


my_devices.openapi = {
    "GET": {"operationId": "list_my_devices", "auth": "session", "fields": ()},
    "POST": {
        "operationId": "bind_my_device",
        "auth": "session",
        "fields": (("device_fingerprint", "str", True), ("display_name", "str?", False)),
    },
}


@csrf_exempt
def unbind_my_device(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "unbind_my_device"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(data)
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        device = Device.objects.filter(pk=pk, entitlement__account=request.user).first()
        if device is None:
            raise Failure("not_found", "Not found.")
        device = services.unbind(device)
        ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
        response = JsonResponse(
            {
                "device": {
                    "device_id": device.pk,
                    "entitlement_id": device.entitlement_id,
                    "device_fingerprint": device.device_fingerprint,
                    "display_name": device.display_name,
                    "bound_at": device.bound_at.isoformat(),
                    "status": device.status,
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


unbind_my_device.openapi = {"POST": {"operationId": "unbind_my_device", "auth": "session", "fields": ()}}


@csrf_exempt
def set_my_device_display_name(request, pk):
    if request.method != "PATCH":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "set_my_device_display_name"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        origin = request.headers.get("Origin")
        if origin is not None and origin != f"{request.scheme}://{request.get_host()}":
            raise Failure("forbidden", "Cross-origin writes are not allowed.")
        user = request.user
        if not user.is_authenticated:
            raise Failure("unauthenticated", "A session cookie is required.")
        ctx.update(actor="admin" if user.is_staff else "customer", account_id=user.pk)
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"display_name"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "display_name" not in data:
            raise Failure("validation_error", "Missing required field: display_name.")
        if not (data["display_name"] is None or type(data["display_name"]) is str):
            raise Failure("validation_error", "Field display_name has an invalid value.")
        device = Device.objects.filter(pk=pk, entitlement__account=request.user).first()
        if device is None:
            raise Failure("not_found", "Not found.")
        services.rename_device(device, data["display_name"])
        ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
        response = JsonResponse(
            {
                "device": {
                    "device_id": device.pk,
                    "entitlement_id": device.entitlement_id,
                    "device_fingerprint": device.device_fingerprint,
                    "display_name": device.display_name,
                    "bound_at": device.bound_at.isoformat(),
                    "status": device.status,
                }
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


set_my_device_display_name.openapi = {
    "PATCH": {
        "operationId": "set_my_device_display_name",
        "auth": "session",
        "fields": (("display_name", "str?", True),),
    }
}


@csrf_exempt
def activate_device(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "activate_device"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"license_key", "display_name", "device_fingerprint"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "license_key" not in data:
            raise Failure("validation_error", "Missing required field: license_key.")
        if type(data["license_key"]) is not str:
            raise Failure("validation_error", "Field license_key has an invalid value.")
        if "device_fingerprint" not in data:
            raise Failure("validation_error", "Missing required field: device_fingerprint.")
        if type(data["device_fingerprint"]) is not str:
            raise Failure("validation_error", "Field device_fingerprint has an invalid value.")
        if "display_name" in data:
            if not (data["display_name"] is None or type(data["display_name"]) is str):
                raise Failure("validation_error", "Field display_name has an invalid value.")
        ctx["actor"] = "application"
        key, entitlement = services.resolve_redeemed_key(data["license_key"])
        device, created = services.bind(
            entitlement, data["device_fingerprint"], data.get("display_name"), source_key_id=key.pk
        )
        ctx.update(product_id=entitlement.product_id, entitlement_id=entitlement.pk, device_id=device.pk)
        response = JsonResponse(
            {
                "device": {
                    "device_id": device.pk,
                    "entitlement_id": device.entitlement_id,
                    "device_fingerprint": device.device_fingerprint,
                    "display_name": device.display_name,
                    "bound_at": device.bound_at.isoformat(),
                    "status": device.status,
                }
            },
            status=201 if created else 200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


activate_device.openapi = {
    "POST": {
        "operationId": "activate_device",
        "auth": "anonymous",
        "fields": (
            ("license_key", "str", True),
            ("device_fingerprint", "str", True),
            ("display_name", "str?", False),
        ),
    }
}


@csrf_exempt
def validate_device(request):
    if request.method != "POST":
        return JsonResponse({"error": "validation_error", "message": "Method not allowed."}, status=405)
    operation = "validate_device"
    ctx = {"actor": "anonymous", "rid": audit.request_id(request)}
    try:
        if request.content_type != "application/json":
            raise Failure("validation_error", "Write bodies must be Content-Type: application/json.")
        if not request.body:
            data = {}
        else:
            try:
                data = json.loads(request.body)
            except (ValueError, RecursionError):
                raise Failure("validation_error", "Body must be a JSON object.")
        if not isinstance(data, dict):
            raise Failure("validation_error", "Body must be a JSON object.")
        for field, value in data.items():
            services.validate_text(field)
            if isinstance(value, str):
                services.validate_text(value)
            elif isinstance(value, (list, dict)):
                raise Failure("validation_error", "Nested values are not supported.")
        unknown = sorted(set(data) - {"license_key", "device_fingerprint"})
        if unknown:
            raise Failure("validation_error", f"Unknown fields: {', '.join(unknown)}.")
        if "license_key" not in data:
            raise Failure("validation_error", "Missing required field: license_key.")
        if type(data["license_key"]) is not str:
            raise Failure("validation_error", "Field license_key has an invalid value.")
        if "device_fingerprint" not in data:
            raise Failure("validation_error", "Missing required field: device_fingerprint.")
        if type(data["device_fingerprint"]) is not str:
            raise Failure("validation_error", "Field device_fingerprint has an invalid value.")
        ctx["actor"] = "application"
        device = services.validate(data["license_key"], data["device_fingerprint"])
        ctx.update(entitlement_id=device.entitlement_id, device_id=device.pk)
        response = JsonResponse(
            {
                "valid": True,
                "device": {
                    "device_id": device.pk,
                    "entitlement_id": device.entitlement_id,
                    "device_fingerprint": device.device_fingerprint,
                    "display_name": device.display_name,
                    "bound_at": device.bound_at.isoformat(),
                    "status": device.status,
                },
            },
            status=200,
        )
        ctx["outcome"] = "success"
        audit.emit(operation, ctx)
        return response
    except (Failure, OperationalError, IntegrityError, DataError, RequestDataTooBig, UnicodeError) as exc:
        if isinstance(exc, Failure):
            error, message = (exc.error, exc.message)
        elif isinstance(exc, OperationalError):
            error, message = ("store_unavailable", "The license store is unavailable.")
        elif isinstance(exc, IntegrityError):
            error, message = ("conflict", "The requested change conflicts with existing data.")
        else:
            error, message = ("validation_error", "The request body is invalid or too large.")
        ctx["outcome"] = error
        audit.emit(operation, ctx)
        return JsonResponse({"error": error, "message": message}, status=HTTP_STATUS[error])


validate_device.openapi = {
    "POST": {
        "operationId": "validate_device",
        "auth": "anonymous",
        "fields": (("license_key", "str", True), ("device_fingerprint", "str", True)),
    }
}

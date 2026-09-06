"""SPEC Section 14.1 error classes. Status lives on each raiseable type."""


class Failure(Exception):
    code = "validation_error"
    status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _error(code, status):
    return type(code, (Failure,), {"code": code, "status": status})


validation_error = _error("validation_error", 400)
unauthenticated = _error("unauthenticated", 401)
forbidden = _error("forbidden", 403)
not_found = _error("not_found", 404)
unknown_key = _error("unknown_key", 404)
unknown_device = _error("unknown_device", 404)
conflict = _error("conflict", 409)
already_entitled = _error("already_entitled", 409)
key_already_redeemed = _error("key_already_redeemed", 409)
key_revoked = _error("key_revoked", 409)
seat_exhausted = _error("seat_exhausted", 409)
entitlement_suspended = _error("entitlement_suspended", 409)
entitlement_revoked = _error("entitlement_revoked", 409)
entitlement_expired = _error("entitlement_expired", 409)
rate_limited = _error("rate_limited", 429)
store_unavailable = _error("store_unavailable", 503)


def validate_text(value):
    if "\x00" in value:
        raise validation_error("Text must not contain null characters.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise validation_error("Text must contain valid Unicode characters.") from None

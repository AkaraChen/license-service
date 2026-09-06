"""SPEC Section 14.1 error classes. Status lives on each raiseable type."""


class Failure(Exception):
    code = "validation_error"
    status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ValidationError(Failure):
    code = "validation_error"
    status = 400


class Unauthenticated(Failure):
    code = "unauthenticated"
    status = 401


class Forbidden(Failure):
    code = "forbidden"
    status = 403


class NotFound(Failure):
    code = "not_found"
    status = 404


class UnknownKey(Failure):
    code = "unknown_key"
    status = 404


class UnknownDevice(Failure):
    code = "unknown_device"
    status = 404


class Conflict(Failure):
    code = "conflict"
    status = 409


class AlreadyEntitled(Failure):
    code = "already_entitled"
    status = 409


class KeyAlreadyRedeemed(Failure):
    code = "key_already_redeemed"
    status = 409


class KeyRevoked(Failure):
    code = "key_revoked"
    status = 409


class SeatExhausted(Failure):
    code = "seat_exhausted"
    status = 409


class EntitlementSuspended(Failure):
    code = "entitlement_suspended"
    status = 409


class EntitlementRevoked(Failure):
    code = "entitlement_revoked"
    status = 409


class EntitlementExpired(Failure):
    code = "entitlement_expired"
    status = 409


class RateLimited(Failure):
    code = "rate_limited"
    status = 429


class StoreUnavailable(Failure):
    code = "store_unavailable"
    status = 503


def validate_text(value):
    if "\x00" in value:
        raise ValidationError("Text must not contain null characters.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValidationError("Text must contain valid Unicode characters.") from None

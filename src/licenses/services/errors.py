"""SPEC Section 14.1 error classes. Status and code live on the type."""


class Failure(Exception):
    code, status, message = "validation_error", 400, "The request is invalid."

    def __init__(self, message=None):
        if message is not None:
            self.message = message
        super().__init__(self.message)

    def envelope(self):
        return {"error": self.code, "message": self.message}


class ValidationError(Failure):
    code, status, message = "validation_error", 400, "The request body is invalid or too large."


class Unauthenticated(Failure):
    code, status, message = "unauthenticated", 401, "A session cookie is required."


class Forbidden(Failure):
    code, status, message = "forbidden", 403, "Admin privileges required."


class NotFound(Failure):
    code, status, message = "not_found", 404, "Not found."


class UnknownKey(Failure):
    code, status, message = "unknown_key", 404, "This license key is not recognized."


class UnknownDevice(Failure):
    code, status, message = "unknown_device", 404, "No bound device matches this fingerprint."


class Conflict(Failure):
    code, status, message = "conflict", 409, "The requested change conflicts with existing data."


class AlreadyEntitled(Failure):
    code, status, message = (
        "already_entitled",
        409,
        "This account already has an entitlement for this product.",
    )


class KeyAlreadyRedeemed(Failure):
    code, status, message = (
        "key_already_redeemed",
        409,
        "This license key was already redeemed by another account.",
    )


class KeyRevoked(Failure):
    code, status, message = "key_revoked", 409, "This license key has been revoked."


class SeatExhausted(Failure):
    code, status, message = "seat_exhausted", 409, "This entitlement has no remaining device seats."


class EntitlementSuspended(Failure):
    code, status, message = "entitlement_suspended", 409, "This entitlement is suspended."


class EntitlementRevoked(Failure):
    code, status, message = "entitlement_revoked", 409, "This entitlement has been revoked."


class EntitlementExpired(Failure):
    code, status, message = "entitlement_expired", 409, "This entitlement has expired."


class RateLimited(Failure):
    code, status, message = "rate_limited", 429, "Registration limit reached. Please try again later."


class StoreUnavailable(Failure):
    code, status, message = "store_unavailable", 503, "The license store is unavailable."

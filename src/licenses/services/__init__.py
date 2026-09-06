"""License policy and shared validation/transaction helpers (SPEC 7, 16).
Account registration and authentication live in accounts.py.
"""

from .devices import (
    DEVICE_HISTORY_LIMIT,
    FINGERPRINT_MAX_LENGTH,
    bind,
    check_active,
    normalize_fingerprint,
    rename_device,
    resolve_redeemed_key,
    unbind,
    validate,
)
from .errors import Failure, validate_text
from .keys import hash_key, issue_key, revoke_key
from .redeem import redeem

__all__ = (
    "DEVICE_HISTORY_LIMIT",
    "FINGERPRINT_MAX_LENGTH",
    "Failure",
    "bind",
    "check_active",
    "hash_key",
    "issue_key",
    "normalize_fingerprint",
    "redeem",
    "rename_device",
    "resolve_redeemed_key",
    "revoke_key",
    "unbind",
    "validate",
    "validate_text",
)

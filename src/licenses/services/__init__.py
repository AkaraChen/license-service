"""License policy and shared validation/transaction helpers (SPEC 7, 16).
Account registration and authentication live in accounts.py.
"""

from .devices import (
    DEVICE_HISTORY_LIMIT,
    bind,
    check_active,
    rename_device,
    resolve_redeemed_key,
    unbind,
    validate,
)
from .errors import Failure
from .keys import hash_key, issue_key, revoke_key
from .redeem import redeem

__all__ = (
    "DEVICE_HISTORY_LIMIT",
    "Failure",
    "bind",
    "check_active",
    "hash_key",
    "issue_key",
    "redeem",
    "rename_device",
    "resolve_redeemed_key",
    "revoke_key",
    "unbind",
    "validate",
)

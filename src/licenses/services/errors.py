class Failure(Exception):
    """One SPEC Section 14.1 error class plus a human-readable message."""

    def __init__(self, error, message):
        super().__init__(message)
        self.error = error
        self.message = message


def validate_text(value):
    if "\x00" in value:
        raise Failure("validation_error", "Text must not contain null characters.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise Failure("validation_error", "Text must contain valid Unicode characters.") from None

class DjangoPaddleMorError(Exception):
    """Base package exception."""


class MissingPaddleIdentifierError(DjangoPaddleMorError):
    """Raised when a Paddle payload cannot be matched to a stable identifier."""


class UnsupportedResourceError(DjangoPaddleMorError):
    """Raised when a resource name is not mapped by the package."""


class NonPersistedResourceError(DjangoPaddleMorError):
    """Raised when a valid Paddle resource does not map to a persisted Django model."""


class WebhookVerificationError(DjangoPaddleMorError):
    """Raised when webhook verification cannot be attempted."""

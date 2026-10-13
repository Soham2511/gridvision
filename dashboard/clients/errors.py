"""Dashboard client errors that can be shown safely to the user."""


class APIClientError(RuntimeError):
    """Raised when the API is unreachable or returns an invalid/error response."""

"""Application errors. Each maps to one HTTP status in chatlpt.http."""


class AppError(Exception):
    """Base error."""

    status_code = 500


class NotAuthenticated(AppError):
    """No session, or an invalid one (401)."""

    status_code = 401


class UnverifiedEmail(NotAuthenticated):
    """The provider has no verified email for this account (D26)."""


class AccountDisabled(NotAuthenticated):
    """The account was disabled by an admin or retired by a claim."""


class SignupClosed(NotAuthenticated):
    """No account for this email, and signup is closed."""


class AccessDenied(AppError):
    """Signed in, but not allowed (403)."""

    status_code = 403


class NotFound(AppError):
    """No such record visible to this user (404). Never reveals another user's records."""

    status_code = 404


class InvalidRequest(AppError):
    """Malformed or unsupported request (400)."""

    status_code = 400


class Conflict(AppError):
    """The record already exists, for example an email already registered (409)."""

    status_code = 409


class ChatUnavailable(AppError):
    """No ready runner, the engine is not configured, or payment was refused everywhere (503)."""

    status_code = 503

    def __init__(self, message: str, retry_after_s: int = 10) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class TooManyAttempts(AppError):
    """Too many login, signup or claim attempts from this address or for this email (429, D26)."""

    status_code = 429

    def __init__(self, message: str, retry_after_s: int = 60) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ReplyFailed(AppError):
    """The runner answered with an error after the job was dispatched (502)."""

    status_code = 502

    def __init__(self, message: str, *, payment_sent: bool, uncertain: bool = False) -> None:
        super().__init__(message)
        self.payment_sent = payment_sent
        self.uncertain = uncertain


class NotImplementedYet(AppError):
    """A reserved feature (501). Loud, never silent."""

    status_code = 501

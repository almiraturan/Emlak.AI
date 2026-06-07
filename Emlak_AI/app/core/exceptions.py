"""Custom exception classes for EmlakAI API."""

from typing import Any


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, code: str | None = None, status_code: int = 500, details: dict[str, Any] | None = None):
        self.message = message
        self.code = code or "INTERNAL_ERROR"
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationException(AppException):
    """Validation-related errors (400)."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR", details: dict[str, Any] | None = None):
        super().__init__(message, code, status_code=400, details=details)


class ResourceNotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(message, code, status_code=404)


class DatabaseException(AppException):
    """Database operation errors (500)."""

    def __init__(self, message: str = "Database error occurred", code: str = "DATABASE_ERROR"):
        super().__init__(message, code, status_code=500)


class IngestionException(AppException):
    """Ingestion operation errors (422)."""

    def __init__(self, message: str, code: str = "INGESTION_ERROR", details: dict[str, Any] | None = None):
        super().__init__(message, code, status_code=422, details=details)

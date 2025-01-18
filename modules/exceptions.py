from datetime import datetime
from uuid import uuid4
from typing import Optional, List, Dict, Any
from http import HTTPStatus

class BaseError(Exception):
    """Base exception class for the application"""
    def __init__(
        self, 
        message: str,
        code: Optional[str] = None,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: Optional[List[Dict[str, Any]]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.timestamp = datetime.now()
        self.trace_id = str(uuid4())
        self.details = details or []
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "code": self.code,
            "status_code": self.status_code,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "details": self.details
        }

class APIError(BaseError):
    """API related errors"""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(
            message=message,
            code=code,
            status_code=HTTPStatus.BAD_GATEWAY
        )

class DatabaseError(BaseError):
    """Database related errors"""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(
            message=message,
            code=code,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE
        )

class ValidationError(BaseError):
    """Validation related errors"""
    def __init__(self, message: str, details: Optional[List[Dict[str, Any]]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            details=details
        )

class RateLimitError(BaseError):
    """Rate limiting related errors"""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=HTTPStatus.TOO_MANY_REQUESTS
        )

class AuthenticationError(BaseError):
    """Authentication related errors"""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=HTTPStatus.UNAUTHORIZED
        )
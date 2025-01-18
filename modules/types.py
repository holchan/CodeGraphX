from enum import Enum
from typing import TypedDict, Literal, Optional
from datetime import datetime
from uuid import UUID
from dataclasses import dataclass, field
from pydantic import BaseModel, validator
from .exceptions import ValidationError

# Enhanced Error Types
class UUIDValidationError(ValidationError):
    """Raised when UUID validation fails"""
    pass

class SearchTypeValidationError(ValidationError):
    """Raised when search type validation fails"""
    pass

class StatusValidationError(ValidationError):
    """Raised when repository status validation fails"""
    pass

class DateValidationError(ValidationError):
    """Raised when date validation fails"""
    pass

# Enhanced Enums
class SearchType(str, Enum):
    """Search types with descriptions"""
    SUMMARIES = "SUMMARIES"  # Get high-level overview of code
    INSIGHTS = "INSIGHTS"    # Extract key implementation details
    CHUNKS = "CHUNKS"        # Retrieve relevant code segments
    COMPLETION = "COMPLETION"  # Generate contextual responses

    @classmethod
    def validate(cls, value: str) -> "SearchType":
        try:
            return cls(value)
        except ValueError:
            raise SearchTypeValidationError(f"Invalid search type: {value}")

# Repository Status Types
class RepositoryStatusType(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SYNCING = "syncing"
    ERROR = "error"

    @classmethod
    def validate(cls, value: str) -> "RepositoryStatusType":
        try:
            return cls(value)
        except ValueError:
            raise StatusValidationError(f"Invalid repository status: {value}")

# Frozen Dataclasses
@dataclass(frozen=True)
class RepositoryId:
    """Immutable repository identifier"""
    value: UUID

    def __post_init__(self):
        if not isinstance(self.value, UUID):
            try:
                object.__setattr__(self, 'value', UUID(str(self.value)))
            except ValueError as e:
                raise UUIDValidationError(f"Invalid UUID format: {e}")

    def __str__(self) -> str:
        return str(self.value)

@dataclass(frozen=True)
class Timestamp:
    """Immutable timestamp with validation"""
    value: datetime

    def __post_init__(self):
        if not isinstance(self.value, datetime):
            try:
                object.__setattr__(self, 'value', datetime.fromisoformat(str(self.value)))
            except ValueError as e:
                raise DateValidationError(f"Invalid datetime format: {e}")

# Pydantic Models for Complex Types
class RepositoryStatus(BaseModel):
    """Repository status with validation"""
    url: str
    status: RepositoryStatusType
    last_sync: Optional[Timestamp]
    error_message: Optional[str]
    dataset_id: RepositoryId
    is_active: bool

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://', 'git://')):
            raise ValidationError("Invalid repository URL scheme")
        return v

    class Config:
        frozen = True
        arbitrary_types_allowed = True

class SearchHistoryItem(BaseModel):
    """Search history item with validation"""
    id: RepositoryId
    text: str
    user: str
    created_at: Timestamp
    search_type: SearchType
    repository_ids: Optional[str]

    @validator('repository_ids')
    def validate_repository_ids(cls, v):
        if v:
            try:
                # Validate each UUID in the comma-separated string
                for id_str in v.split(','):
                    UUID(id_str.strip())
            except ValueError as e:
                raise UUIDValidationError(f"Invalid repository ID format: {e}")
        return v

    class Config:
        frozen = True
        arbitrary_types_allowed = True

class APIResponse(BaseModel):
    """API response with validation"""
    status: Literal["success", "error"]
    message: str
    data: Optional[dict] = None
    errors: Optional[list[str]] = None

    @validator('status')
    def validate_status(cls, v):
        if v not in ("success", "error"):
            raise ValidationError("Status must be either 'success' or 'error'")
        return v

    @validator('errors')
    def validate_errors(cls, v, values):
        if values.get('status') == 'error' and not v:
            raise ValidationError("Errors must be provided when status is 'error'")
        return v

    class Config:
        frozen = True

# Type Aliases for improved readability
RepositoryIdStr = str  # Type alias for repository ID strings
UserIdStr = str       # Type alias for user ID strings
SearchTypeStr = str   # Type alias for search type strings

# Custom TypedDicts for specific use cases
class RepositoryMetadata(TypedDict, total=False):
    """Repository metadata with optional fields"""
    name: str
    description: Optional[str]
    stars: Optional[int]
    forks: Optional[int]
    last_updated: Optional[datetime]
    language: Optional[str]
    tags: Optional[list[str]]

class SearchMetadata(TypedDict, total=False):
    """Search metadata with optional fields"""
    query_time: float
    result_count: int
    filters_applied: Optional[dict]
    source_files: Optional[list[str]]
    context: Optional[dict]
from pydantic import BaseModel, validator
from typing import Optional
from uuid import UUID
from .types import SearchType

# Existing Pydantic schemas
class RepositoryAddSchema(BaseModel):
    url: str
    branch: Optional[str]
    auth_token: Optional[str]

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://', 'git://')):
            raise ValueError("Invalid repository URL scheme")
        return v

class MessageSchema(BaseModel):
    query: str
    search_type: SearchType
    parent_id: Optional[UUID]

    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty")
        if len(v) > 1000:
            raise ValueError("Query too long")
        return v

class SearchCriteriaSchema(BaseModel):
    query: Optional[str]
    search_type: Optional[SearchType]
    page: int
    page_size: int

    @validator('page')
    def validate_page(cls, v):
        if v < 1:
            raise ValueError("Page must be positive")
        return v

    @validator('page_size')
    def validate_page_size(cls, v):
        if v < 1:
            raise ValueError("Page size must be positive")
        return v

def validate_input(data: dict, types: dict) -> None:
    """
    Validates that input data matches expected types
    
    Args:
        data (dict): Dictionary containing the data to validate
        types (dict): Dictionary containing expected types for each key
    
    Raises:
        TypeError: If data type doesn't match expected type
        ValueError: If required data is missing
    """
    for key, expected_type in types.items():
        if key not in data:
            raise ValueError(f"Missing required field: {key}")
        
        if not isinstance(data[key], expected_type):
            raise TypeError(f"Field {key} must be of type {expected_type.__name__}")

__all__ = [
    'RepositoryAddSchema',
    'MessageSchema', 
    'SearchCriteriaSchema',
    'validate_input'
]
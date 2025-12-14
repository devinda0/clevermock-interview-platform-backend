from beanie import Document, Indexed
from datetime import datetime
from typing import Optional


class TokenBlacklist(Document):
    """
    Model for storing blacklisted JWT tokens.
    Used for logout functionality to invalidate tokens before expiration.
    """
    token_jti: Indexed(str, unique=True)  # JWT ID - unique identifier for the token
    exp: datetime  # Expiration time - used for auto-cleanup
    created_at: datetime = datetime.utcnow()

    class Settings:
        name = "token_blacklist"
        
    class Config:
        json_schema_extra = {
            "example": {
                "token_jti": "550e8400-e29b-41d4-a716-446655440000",
                "exp": "2024-12-07T00:00:00",
                "created_at": "2024-12-06T23:00:00"
            }
        }

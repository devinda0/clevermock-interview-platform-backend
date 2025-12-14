from beanie import Document, Indexed
from datetime import datetime
from typing import Optional


class PasswordReset(Document):
    """
    Model for storing password reset tokens.
    Used for the forgot password flow.
    """
    user_id: Indexed(str)  # Reference to the user
    token: Indexed(str, unique=True)  # Secure random token
    exp: datetime  # Expiration time (typically 1 hour)
    used: bool = False  # Whether the token has been used
    created_at: datetime = datetime.utcnow()

    class Settings:
        name = "password_resets"
        
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "507f1f77bcf86cd799439011",
                "token": "a1b2c3d4e5f6g7h8i9j0",
                "exp": "2024-12-07T00:00:00",
                "used": False,
                "created_at": "2024-12-06T23:00:00"
            }
        }

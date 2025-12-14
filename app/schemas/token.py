from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    jti: Optional[str] = None  # JWT ID for blacklisting

class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request body"""
    refresh_token: str


from pydantic import BaseModel, EmailStr


class PasswordResetRequest(BaseModel):
    """Schema for requesting a password reset email"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for confirming password reset with token and new password"""
    token: str
    new_password: str

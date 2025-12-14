import bcrypt
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
from app.core.config import settings

def _hash_password_pre(password: str) -> str:
    # SHA256 produces a 64-character hex string, which fits in bcrypt's 72-byte limit
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # We try verifying with the pre-hashed password (new standard)
    # If we wanted to support legacy passwords (plain bcrypt), we would need a migration strategy
    # For now, we assume this is a fresh implementation or breaking change is acceptable
    password_byte_enc = _hash_password_pre(plain_password).encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    password_byte_enc = _hash_password_pre(password).encode('utf-8')
    return bcrypt.hashpw(password_byte_enc, bcrypt.gensalt()).decode('utf-8')

def generate_jti() -> str:
    """Generate a unique JWT ID for token identification"""
    return secrets.token_urlsafe(32)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> tuple[str, str]:
    """
    Create an access token with a unique JTI.
    Returns tuple of (token, jti)
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    jti = generate_jti()
    to_encode = {"exp": expire, "sub": str(subject), "type": "access", "jti": jti}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt, jti

def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> tuple[str, str]:
    """
    Create a refresh token with a unique JTI.
    Returns tuple of (token, jti)
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    jti = generate_jti()
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh", "jti": jti}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt, jti

def create_password_reset_token() -> str:
    """Generate a secure random token for password reset"""
    return secrets.token_urlsafe(32)

def get_password_reset_expiry() -> datetime:
    """Get the expiration datetime for a password reset token"""
    return datetime.utcnow() + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)

def decode_token(token: str) -> dict:
    """Decode and return the payload of a JWT token"""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


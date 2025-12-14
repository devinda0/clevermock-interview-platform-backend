from typing import Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError

from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    get_password_hash, 
    verify_password,
    create_password_reset_token,
    get_password_reset_expiry,
    decode_token
)
from app.models.user import User
from app.models.token_blacklist import TokenBlacklist
from app.models.password_reset import PasswordReset
from app.schemas.user import UserCreate, UserOut, UserLogin
from app.schemas.token import Token, TokenPayload, RefreshTokenRequest
from app.schemas.password_reset import PasswordResetRequest, PasswordResetConfirm
from app.api import deps
from app.core.config import settings

router = APIRouter()

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


@router.post("/signup", response_model=UserOut)
async def signup(user_in: UserCreate) -> Any:
    """
    Create new user without the need to be logged in
    """
    user = await User.find_one(User.email == user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_active=user_in.is_active,
    )
    await user.create()
    return user


@router.post("/login", response_model=Token)
async def login(form_data: UserLogin) -> Any:
    """
    Get access token for future requests
    """
    user = await User.find_one(User.email == form_data.email)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token, _ = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(request: RefreshTokenRequest) -> Any:
    """
    Refresh access token using a valid refresh token
    """
    try:
        payload = decode_token(request.refresh_token)
        token_data = TokenPayload(**payload)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        
        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await deps.is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
            
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
        
    user = await User.get(token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    # Blacklist the old refresh token
    old_jti = payload.get("jti")
    if old_jti:
        exp = datetime.fromtimestamp(payload.get("exp", 0))
        blacklist_entry = TokenBlacklist(
            token_jti=old_jti,
            exp=exp,
        )
        await blacklist_entry.create()
    
    access_token, _ = create_access_token(user.id)
    new_refresh_token, _ = create_refresh_token(user.id)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(token: str = Depends(reusable_oauth2)) -> Any:
    """
    Logout user by blacklisting the current access token
    """
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        
        if jti:
            # Check if already blacklisted
            existing = await TokenBlacklist.find_one(TokenBlacklist.token_jti == jti)
            if not existing:
                exp = datetime.fromtimestamp(payload.get("exp", 0))
                blacklist_entry = TokenBlacklist(
                    token_jti=jti,
                    exp=exp,
                )
                await blacklist_entry.create()
        
        return {"message": "Successfully logged out"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


@router.post("/forget")
async def forget_password(request: PasswordResetRequest) -> Any:
    """
    Request a password reset. 
    Always returns success to prevent email enumeration attacks.
    """
    user = await User.find_one(User.email == request.email)
    
    if user:
        # Generate reset token
        token = create_password_reset_token()
        exp = get_password_reset_expiry()
        
        # Invalidate any existing reset tokens for this user
        await PasswordReset.find(
            PasswordReset.user_id == str(user.id),
            PasswordReset.used == False
        ).update({"$set": {"used": True}})
        
        # Create new reset token
        reset = PasswordReset(
            user_id=str(user.id),
            token=token,
            exp=exp,
        )
        await reset.create()
        
        # TODO: Send email with reset link
        # In production, integrate with email service (SendGrid, AWS SES, etc.)
        # For now, log the token for development purposes
        print(f"[DEV] Password reset token for {request.email}: {token}")
    
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(request: PasswordResetConfirm) -> Any:
    """
    Reset password using the reset token
    """
    # Find the reset token
    reset = await PasswordReset.find_one(
        PasswordReset.token == request.token,
        PasswordReset.used == False
    )
    
    if not reset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    
    # Check if token has expired
    if datetime.utcnow() > reset.exp:
        # Mark as used to prevent further attempts
        reset.used = True
        await reset.save()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )
    
    # Find the user
    user = await User.get(reset.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    await user.save()
    
    # Mark token as used
    reset.used = True
    await reset.save()
    
    return {"message": "Password has been reset successfully"}


@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(deps.get_current_user)) -> Any:
    """
    Get current user
    """
    return current_user


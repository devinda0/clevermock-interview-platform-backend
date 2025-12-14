from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Any
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(UserBase):
    id: Any
    created_at: datetime

    @field_validator('id', mode='before')
    @classmethod
    def convert_id_to_string(cls, v):
        return str(v) if v else None

    class Config:
        from_attributes = True


from typing import Optional, Dict
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class ReviewBase(BaseModel):
    overall_rating: int = Field(..., ge=1, le=5)
    ai_quality_rating: Optional[int] = Field(None, ge=1, le=5)
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_text: Optional[str] = None
    would_recommend: Optional[bool] = None

    @field_validator("overall_rating", "ai_quality_rating", "difficulty_rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("Rating must be between 1 and 5")
        return v


class ReviewCreate(ReviewBase):
    pass


class ReviewResponse(ReviewBase):
    id: UUID
    conversation_id: UUID
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewStats(BaseModel):
    average_rating: float
    total_reviews: int
    rating_distribution: Dict[str, int]

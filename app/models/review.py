from typing import Optional
from datetime import datetime
from beanie import Document
from pydantic import Field, field_validator
from uuid import UUID, uuid4


class Review(Document):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    user_id: str
    overall_rating: int
    ai_quality_rating: Optional[int] = None
    difficulty_rating: Optional[int] = None
    feedback_text: Optional[str] = None
    would_recommend: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("overall_rating", "ai_quality_rating", "difficulty_rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("Rating must be between 1 and 5")
        return v

    class Settings:
        name = "reviews"

from typing import List, Optional
from datetime import datetime
from beanie import Document, Link
from pydantic import BaseModel, Field
from uuid import UUID, uuid4

class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    content: str
    sender_type: str  # "user" or "ai"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Conversation(Document):
    id: UUID = Field(default_factory=uuid4)
    user_id: Optional[str] = None
    title: Optional[str] = None
    participants: List[str] = []
    messages: List[Message] = []
    transcript: List[dict] = []
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "conversations"

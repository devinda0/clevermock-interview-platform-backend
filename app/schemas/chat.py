from typing import List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class MessageBase(BaseModel):
    content: str
    sender_type: str

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationBase(BaseModel):
    title: Optional[str] = None

class ConversationCreate(ConversationBase):
    pass

class ConversationResponse(ConversationBase):
    id: UUID
    messages: List[MessageResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

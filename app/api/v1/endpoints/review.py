from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.models.user import User
from app.models.chat import Conversation
from app.models.review import Review
from app.schemas.review import ReviewCreate, ReviewResponse

router = APIRouter()

@router.post("/{conversation_id}", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    conversation_id: UUID,
    review_in: ReviewCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create a new review for a completed conversation.
    """
    # 1. Validate conversation exists and belongs to the user
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is the owner (user_id matches) or a participant
    # The requirement says "belongs to the current user".
    # Based on app/models/chat.py, user_id is the creator.
    if str(conversation.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to review this conversation"
        )

    # 2. Validate that the interview has a transcript (i.e., is completed)
    # We check if 'transcript' field is populated and not empty
    if not conversation.transcript:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot review an incomplete interview (no transcript found)"
        )

    # 3. Validate that a review doesn't already exist for this conversation
    existing_review = await Review.find_one(Review.conversation_id == conversation_id)
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A review already exists for this conversation"
        )

    # 4. Create and return the review
    review = Review(
        conversation_id=conversation_id,
        user_id=str(current_user.id),
        **review_in.model_dump()
    )
    await review.insert()
    
    return review

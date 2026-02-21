from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.models.user import User
from app.models.chat import Conversation
from app.models.review import Review
from app.schemas.review import ReviewCreate, ReviewResponse, ReviewStats

router = APIRouter()

@router.get("/stats", response_model=ReviewStats)
async def get_review_stats() -> Any:
    """
    Get aggregated review statistics.
    Returns average rating, total number of reviews, and rating distribution.
    This is a public/admin endpoint that does not require authentication.
    """
    pipeline = [
        {
            "$facet": {
                "overview": [
                    {
                        "$group": {
                            "_id": None,
                            "average_rating": {"$avg": "$overall_rating"},
                            "total_reviews": {"$sum": 1}
                        }
                    }
                ],
                "distribution": [
                    {
                        "$group": {
                            "_id": "$overall_rating",
                            "count": {"$sum": 1}
                        }
                    }
                ]
            }
        }
    ]

    cursor = Review.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    
    if not results or not results[0]["overview"]:
        return ReviewStats(
            average_rating=0.0,
            total_reviews=0,
            rating_distribution={"5": 0}
        )
        
    overview = results[0]["overview"][0]
    distribution = results[0]["distribution"]
    
    # Format distribution array into dict with default 0s for missing ratings
    dist_dict = {str(i): 0 for i in range(1, 6)}
    for item in distribution:
        # Pydantic dict expects string keys
        dist_dict[str(item["_id"])] = item["count"]

    return ReviewStats(
        average_rating=round(overview["average_rating"], 1),
        total_reviews=overview["total_reviews"],
        rating_distribution=dist_dict
    )

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

@router.get("/{conversation_id}", response_model=ReviewResponse)
async def get_review(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Retrieve a review for a specific conversation.
    """
    review = await Review.find_one(Review.conversation_id == conversation_id)
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check if the current user is the owner of the review
    if str(review.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this review"
        )
        
    return review

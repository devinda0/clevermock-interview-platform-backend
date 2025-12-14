from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.models.user import User
from app.core.config import settings
from livekit import api
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Agent name must match the one defined in agent.py
AGENT_NAME = "interview-agent"

@router.get("/token")
async def get_livekit_token(
    room: str,
    current_user: User = Depends(get_current_user)
):
    """
    Generate a LiveKit token for a specific room.
    The room name is typically the conversation ID.
    This token includes agent dispatch configuration to ensure
    the interview agent joins the room when the participant connects.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise HTTPException(status_code=500, detail="LiveKit credentials not configured")

    try:
        # Create a grant for the token using new SDK pattern
        grants = api.VideoGrants(
            room_join=True,
            room=room,
        )
        
        # Create room configuration with agent dispatch
        # This tells the LiveKit server to dispatch the interview agent
        # when a participant connects with this token
        room_config = api.RoomConfiguration(
            agents=[
                api.RoomAgentDispatch(
                    agent_name=AGENT_NAME,
                    metadata=f'{{"room": "{room}", "user_id": "{str(current_user.id)}"}}',
                )
            ]
        )
        
        # Create access token using builder pattern
        access_token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(str(current_user.id))
            .with_name(current_user.full_name or current_user.email)
            .with_grants(grants)
            .with_room_config(room_config)
        )
        
        token = access_token.to_jwt()
        
        logger.info(f"Generated LiveKit token for room {room} with agent dispatch for {AGENT_NAME}")
        
        return {
            "token": token, 
            "identity": str(current_user.id), 
            "room": room,
            "serverUrl": settings.LIVEKIT_URL
        }

    except Exception as e:
        logger.error(f"Error generating LiveKit token: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate LiveKit token")

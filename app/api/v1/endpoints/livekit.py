from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.models.user import User
from app.core.config import settings
from livekit import api
from livekit.api.agent_dispatch_service import AgentDispatchService
import aiohttp
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/token")
async def get_livekit_token(
    room: str,
    current_user: User = Depends(get_current_user)
):
    """
    Generate a LiveKit token for a specific room.
    The room name is typically the conversation ID.
    The agent will automatically join the room when created.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise HTTPException(status_code=500, detail="LiveKit credentials not configured")

    try:
        # Create a grant for the token
        grants = api.VideoGrants(
            room_join=True,
            room=room,
            room_create=True,
        )
        access_token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(str(current_user.id))
            .with_name(current_user.full_name or current_user.email)
            .with_grants(grants)
        )
        
        token = access_token.to_jwt()

        # Dispatch the interview agent to the room
        try:
            async with aiohttp.ClientSession() as session:
                dispatch_service = AgentDispatchService(
                    session,
                    settings.LIVEKIT_URL.replace("wss://", "https://").replace("ws://", "http://"),
                    settings.LIVEKIT_API_KEY,
                    settings.LIVEKIT_API_SECRET,
                )
                await dispatch_service.create_dispatch(
                    api.CreateAgentDispatchRequest(
                        room=room,
                        agent_name="interview-agent",
                    )
                )
                logger.info(f"Dispatched interview-agent to room {room}")
        except Exception as dispatch_err:
            logger.warning(f"Agent dispatch failed (agent may auto-join): {dispatch_err}")
        
        logger.info(f"Generated LiveKit token for room {room}")
        
        return {
            "token": token, 
            "identity": str(current_user.id), 
            "room": room,
            "serverUrl": settings.LIVEKIT_URL
        }

    except Exception as e:
        logger.error(f"Error generating LiveKit token: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate LiveKit token")

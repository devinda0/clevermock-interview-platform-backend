from typing import List
from uuid import UUID
from app.models.chat import Conversation, Message
from app.models.user import User
from app.api.deps import get_current_user
from app.schemas.chat import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse
from fastapi import APIRouter, HTTPException, status, WebSocket, WebSocketDisconnect, Depends

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Map user_id to list of active WebSockets (user might have multiple tabs)
        self.active_connections: dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast(self, message: str, limit_to_users: List[str] = None):
        if limit_to_users:
            for user_id in limit_to_users:
                if user_id in self.active_connections:
                    for connection in self.active_connections[user_id]:
                        try:
                            await connection.send_text(message)
                        except RuntimeError:
                            # Connection might be closed
                            pass
        else:
            # Broadcast to everyone (fallback)
            for user_connections in self.active_connections.values():
                for connection in user_connections:
                    try:
                        await connection.send_text(message)
                    except RuntimeError:
                        pass

manager = ConnectionManager()

@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: UUID, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        # Add user to conversation participants if not already there
        conversation = await Conversation.get(conversation_id)
        if conversation and user_id not in conversation.participants:
            conversation.participants.append(user_id)
            await conversation.save()

        while True:
            data = await websocket.receive_text()
            
            conversation = await Conversation.get(conversation_id)
            if conversation:
                import json
                try:
                    message_data = json.loads(data)
                    content = message_data.get("content")
                    sender_type = message_data.get("sender_type", "user")
                except json.JSONDecodeError:
                    content = data
                    sender_type = "user"

                message = Message(content=content, sender_type=sender_type)
                conversation.messages.append(message)
                conversation.updated_at = message.created_at
                await conversation.save()
                
                response_data = {
                    "id": str(message.id),
                    "content": message.content,
                    "sender_type": message.sender_type,
                    "created_at": message.created_at.isoformat()
                }
                # Broadcast only to participants
                await manager.broadcast(json.dumps(response_data), limit_to_users=conversation.participants)
            else:
                 await websocket.send_text("Error: Conversation not found")

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conversation_in: ConversationCreate,
    current_user: User = Depends(get_current_user)
):
    conversation_data = conversation_in.dict()
    conversation_data["user_id"] = str(current_user.id)
    # Add creator to participants if not already present
    if str(current_user.id) not in conversation_data.get("participants", []):
        conversation_data.setdefault("participants", []).append(str(current_user.id))
        
    conversation = Conversation(**conversation_data)
    await conversation.insert()
    return conversation

@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: UUID):
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def create_message(conversation_id: UUID, message_in: MessageCreate):
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    message = Message(**message_in.dict())
    conversation.messages.append(message)
    conversation.updated_at = message.created_at
    await conversation.save()
    
    # Broadcast to WebSocket clients
    response_data = {
        "id": str(message.id),
        "content": message.content,
        "sender_type": message.sender_type,
        "created_at": message.created_at.isoformat()
    }
    import json
    await manager.broadcast(json.dumps(response_data))

    return message

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(conversation_id: UUID):
    conversation = await Conversation.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.messages

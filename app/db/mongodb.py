from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings

async def init_db():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME], 
        document_models=[
            "app.models.chat.Conversation", 
            "app.models.user.User",
            "app.models.token_blacklist.TokenBlacklist",
            "app.models.password_reset.PasswordReset",
            "app.models.review.Review",
        ]
    )


import logging
import asyncio
import os
from uuid import UUID

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    inference,
    room_io,
)
from livekit.plugins import noise_cancellation, silero, openai

from livekit.plugins.google.beta import GeminiTTS
from livekit.plugins.google import LLM as GoogleLLM
from livekit.plugins import deepgram


from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

logger = logging.getLogger("agent")

load_dotenv(".env")

# MongoDB connection settings
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "interview_assistant")

# MongoDB client (lazy initialization)
_mongo_client = None
_db = None


def get_db():
    """Get MongoDB database instance."""
    global _mongo_client, _db
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGODB_URL, uuidRepresentation="standard")
        _db = _mongo_client[DATABASE_NAME]
    return _db


async def get_interview_instructions(room_name: str) -> str:
    """Fetch interview instructions from MongoDB based on room name (conversation ID)."""
    try:
        db = get_db()
        
        # Room name is the Conversation ID (UUID)
        try:
            conversation_id = UUID(room_name)
        except ValueError:
             logger.warning(f"Invalid UUID for room name: {room_name}")
             return "You are a professional interviewer. Conduct a technical interview professionally."

        conversation = await db["conversations"].find_one({"_id": conversation_id})

        if conversation and conversation.get("metadata"):
            interview_details = conversation["metadata"].get("interview_details", "")
            if interview_details:
                logger.info(f"Fetched interview instructions for room {room_name}")
                return interview_details
        
        logger.warning(f"No interview instructions found for room {room_name}, using default")
        return "You are a professional interviewer. Conduct a technical interview professionally."
        
    except Exception as e:
        logger.error(f"Error fetching interview instructions: {e}")
        return "You are a professional interviewer. Conduct a technical interview professionally."


class Assistant(Agent):
    def __init__(self, instructions: str = "") -> None:
        extra_instructions = " The interview is strictly limited to 10 minutes. Please manage the time effectively to cover key topics and evaluate the candidate within this timeframe."
        super().__init__(
            instructions=(instructions or "You are a professional interviewer. Conduct a technical interview professionally.") + extra_instructions,
        )

    # To add tools, use the @function_tool decorator.
    # Here's an example that adds a simple weather tool.
    # You also have to add `from livekit.agents import function_tool, RunContext` to the top of this file
    # @function_tool
    # async def lookup_weather(self, context: RunContext, location: str):
    #     """Use this tool to look up current weather information in the given location.
    #
    #     If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.
    #
    #     Args:
    #         location: The location to look up weather information for (e.g. city name)
    #     """
    #
    #     logger.info(f"Looking up weather for {location}")
    #
    #     return "sunny with a temperature of 70 degrees."


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="interview-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(
            model="nova-3",
            language="en-US",
        ),
        # stt=openai.STT.with_openrouter(
        #     model="google/gemini-2.0-flash-lite-001"
        # ),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        # llm=openai.LLM.with_openrouter(
        #     model="amazon/nova-2-lite-v1:free",
        #     api_key=os.getenv("OPENROUTER_API_KEY"),
        # ),
        llm=GoogleLLM(
            model="gemini-2.5-flash-lite",
        ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        # tts= GeminiTTS(
        #     model="gemini-2.5-flash-preview-tts",
        #     voice_name="Zephyr",
        #     instructions="Speak in a friendly and engaging tone.",
        # ),
        tts=deepgram.TTS(
            model="aura-luna-en",
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        # turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # First, connect to the room (MUST be done before session.start())
    await ctx.connect()

    # Fetch interview instructions from MongoDB using room name as conversation ID
    interview_instructions = await get_interview_instructions(ctx.room.name)
    logger.info(f"Interview instructions: {interview_instructions}")
    logger.info(f"Starting interview with instructions for room: {ctx.room.name}")

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(instructions=interview_instructions),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )

    # Agent initiates the conversation
    await session.generate_reply(instructions="Start the interview.")

    # Limit the interview to 10 minutes (600 seconds)
    INTERVIEW_DURATION_SECONDS = 600
    try:
        await asyncio.sleep(INTERVIEW_DURATION_SECONDS)
        logger.info(f"Interview time limit of {INTERVIEW_DURATION_SECONDS}s reached. Disconnecting.")
        await ctx.room.disconnect()
    except asyncio.CancelledError:
        logger.info("Interview timer cancelled (likely due to early disconnection)")


if __name__ == "__main__":
    cli.run_app(server)
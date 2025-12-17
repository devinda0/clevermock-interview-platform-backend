import logging
import asyncio
import os
from uuid import UUID
from datetime import datetime, timezone

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

# Interview time constants (in seconds)
MAIN_INTERVIEW_DURATION = 600  # 10 minutes for main interview
SUMMARY_PHASE_DURATION = 300   # 5 minutes for summary (10-15 min mark)
TOTAL_INTERVIEW_DURATION = MAIN_INTERVIEW_DURATION + SUMMARY_PHASE_DURATION  # 15 minutes total

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


def get_elapsed_time_info(start_time: datetime) -> dict:
    """Calculate elapsed time and return time-related information."""
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - start_time).total_seconds()
    elapsed_minutes = int(elapsed_seconds // 60)
    elapsed_secs = int(elapsed_seconds % 60)
    remaining_main = max(0, MAIN_INTERVIEW_DURATION - elapsed_seconds)
    remaining_main_minutes = int(remaining_main // 60)
    
    return {
        "elapsed_seconds": elapsed_seconds,
        "elapsed_minutes": elapsed_minutes,
        "elapsed_secs": elapsed_secs,
        "remaining_main_minutes": remaining_main_minutes,
        "is_summary_phase": elapsed_seconds >= MAIN_INTERVIEW_DURATION,
        "is_interview_complete": elapsed_seconds >= TOTAL_INTERVIEW_DURATION,
    }


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


class InterviewAssistant(Agent):
    """Interview assistant agent with time awareness."""
    
    def __init__(self, instructions: str = "", start_time: datetime = None, is_summary_phase: bool = False) -> None:
        self.start_time = start_time or datetime.now(timezone.utc)
        self.is_summary_phase = is_summary_phase
        
        if is_summary_phase:
            # Summary phase instructions (10-15 minutes)
            time_instructions = """

IMPORTANT: The main interview phase has ended. You are now in the SUMMARY PHASE (10-15 minutes).

During this summary phase, you must ONLY:
1. Summarize the candidate's STRONG POINTS based on the interview
2. Identify the candidate's WEAK POINTS or areas that need improvement
3. Provide constructive feedback on HOW THE CANDIDATE CAN IMPROVE themselves

Do NOT ask any new interview questions. Focus entirely on providing valuable feedback to help the candidate grow professionally.
Be constructive, specific, and encouraging while being honest about areas for improvement.

Start by thanking the candidate for their time and then provide the summary."""
        else:
            # Main interview phase instructions (0-10 minutes)
            time_info = get_elapsed_time_info(self.start_time)
            time_instructions = f"""

CURRENT TIME STATUS:
- Interview elapsed time: {time_info['elapsed_minutes']} minutes and {time_info['elapsed_secs']} seconds
- Time remaining for main interview: approximately {time_info['remaining_main_minutes']} minutes
- The main interview phase is strictly limited to 10 minutes. Manage your questions effectively.

Please pace your interview accordingly. As time runs low, focus on the most important evaluation criteria."""
        
        base_instructions = instructions or "You are a professional interviewer. Conduct a technical interview professionally."
        
        super().__init__(
            instructions=base_instructions + time_instructions,
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


@server.rtc_session()
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    
    # Record interview start time
    interview_start_time = datetime.now(timezone.utc)
    logger.info(f"Interview starting at {interview_start_time.isoformat()}")

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
            model="aura-2-thalia-en",
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

    # Start the session with main interview phase agent
    await session.start(
        agent=InterviewAssistant(
            instructions=interview_instructions,
            start_time=interview_start_time,
            is_summary_phase=False
        ),
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

    # Main interview phase (10 minutes)
    try:
        await asyncio.sleep(MAIN_INTERVIEW_DURATION)
        logger.info(f"Main interview phase complete after {MAIN_INTERVIEW_DURATION}s. Transitioning to summary phase.")
        
        # Transition to summary phase
        summary_agent = InterviewAssistant(
            instructions=interview_instructions,
            start_time=interview_start_time,
            is_summary_phase=True
        )
        
        # Update the session with summary phase agent
        session.update_agent(summary_agent)
        
        # Prompt the agent to start the summary
        await session.generate_reply(
            instructions="The main interview phase has ended. Now provide a comprehensive summary of the candidate's performance, including their strong points, weak points, and specific suggestions for how they can improve."
        )
        
        # Summary phase (5 more minutes, total 15 minutes)
        await asyncio.sleep(SUMMARY_PHASE_DURATION)
        logger.info(f"Interview complete after {TOTAL_INTERVIEW_DURATION}s total. Disconnecting.")
        
        # Thank the candidate and disconnect
        await session.generate_reply(
            instructions="Wrap up the interview by thanking the candidate and wishing them well. Let them know the interview session is now complete."
        )
        
        # Give time for the final message to be spoken
        await asyncio.sleep(10)
        await ctx.room.disconnect()
        
    except asyncio.CancelledError:
        logger.info("Interview timer cancelled (likely due to early disconnection)")


if __name__ == "__main__":
    cli.run_app(server)
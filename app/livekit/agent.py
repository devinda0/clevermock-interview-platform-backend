import logging
import asyncio
import os
from uuid import UUID
from datetime import datetime, timezone

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AgentServer,
    JobContext,
    JobProcess,
    cli,
    room_io,
    llm,
)

from livekit.plugins import silero

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
TRANSCRIPT_SAVE_INTERVAL = 30  # Save transcript every 30 seconds


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
        return "You are a professional interviewer named CleverMock. Conduct a technical interview professionally."
        
    except Exception as e:
        logger.error(f"Error fetching interview instructions: {e}")
        return "You are a professional interviewer. Conduct a technical interview professionally."


async def save_transcript(room_name: str, chat_ctx: llm.ChatContext):
    """Save the interview transcript to MongoDB."""
    try:
        db = get_db()
        
        try:
             conversation_id = UUID(room_name)
        except ValueError:
             logger.warning(f"Invalid UUID for room name (cannot save transcript): {room_name}")
             return

        # Convert ChatMessage objects to a serializable format
        messages = []
        for item in chat_ctx.items:
            msg = item if hasattr(item, 'role') else None
            if msg is None:
                continue
            messages.append({
                "role": str(msg.role),  # system, user, assistant
                "content": msg.text_content if hasattr(msg, 'text_content') else str(msg.content),
                "timestamp": datetime.now(timezone.utc)
            })

        logger.info(f"Saving {len(messages)} messages for conversation {conversation_id}")

        await db["conversations"].update_one(
            {"_id": conversation_id},
            {"$set": {"transcript": messages, "updated_at": datetime.now(timezone.utc)}}
        )
        logger.info(f"Transcript saved for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error saving transcript: {e}")


async def periodic_transcript_saver(room_name: str, chat_ctx: llm.ChatContext):
    """Periodically save the transcript to MongoDB."""
    logger.info(f"Starting periodic transcript saver for room {room_name}")
    try:
        while True:
            await asyncio.sleep(TRANSCRIPT_SAVE_INTERVAL)
            await save_transcript(room_name, chat_ctx)
    except asyncio.CancelledError:
        logger.info(f"Periodic transcript saver cancelled for room {room_name}")
    except Exception as e:
        logger.error(f"Error in periodic transcript saver: {e}")


class InterviewAgent:
    """Helper to manage interview instructions."""
    @staticmethod
    def get_instructions(instructions: str = "", start_time: datetime = None, is_summary_phase: bool = False) -> str:
        start_time = start_time or datetime.now(timezone.utc)
        
        if is_summary_phase:
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
            time_info = get_elapsed_time_info(start_time)
            time_instructions = f"""
CURRENT TIME STATUS:
- Interview elapsed time: {time_info['elapsed_minutes']} minutes and {time_info['elapsed_secs']} seconds
- Time remaining for main interview: approximately {time_info['remaining_main_minutes']} minutes
- The main interview phase is strictly limited to 10 minutes. Manage your questions effectively.

Please pace your interview accordingly. As time runs low, focus on the most important evaluation criteria."""
        
        base_instructions = instructions or "You are a professional interviewer named CleverMock. Conduct a technical interview professionally."
        if "CleverMock" not in base_instructions:
             base_instructions = f"Your name is CleverMock. {base_instructions}"
        
        tts_formatting = """
        IMPORTANT: Output suitable for Text-To-Speech.
        - Do NOT use markdown formatting (no bold **, no italics *, no headers #).
        - Do NOT use lists with asterisks or hyphens unless you want them read as "dash".
        - Do NOT use special symbols.
        - Just write the words exactly as they should be spoken.
        """
        
        return base_instructions + time_instructions + tts_formatting


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="interview-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    
    # Record interview start time
    interview_start_time = datetime.now(timezone.utc)
    logger.info(f"Interview starting at {interview_start_time.isoformat()}")

    # Fetch interview instructions
    interview_instructions = await get_interview_instructions(ctx.room.name)

    # Create the Agent with instructions
    interview_agent = Agent(
        instructions=InterviewAgent.get_instructions(
            instructions=interview_instructions,
            start_time=interview_start_time,
            is_summary_phase=False
        ),
    )

    # Set up the voice session
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=GoogleLLM(model="gemini-2.5-flash-lite"),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        preemptive_generation=True,
    )

    # First, connect to the room
    await ctx.connect()

    # Start the periodic transcript saver
    transcript_saver_task = asyncio.create_task(
        periodic_transcript_saver(ctx.room.name, session.chat_ctx)
    )

    # Start the session with the agent
    await session.start(agent=interview_agent, room=ctx.room)

    # Agent initiates the conversation
    await session.say("Hello! I am CleverMock, your interviewer for today. Shall we begin?")

    # Main interview phase
    try:
        await asyncio.sleep(MAIN_INTERVIEW_DURATION)
        logger.info(f"Main interview phase complete. Transitioning to summary phase.")
        
        # Transition to summary phase
        session.chat_ctx.add_message(
            role="system",
            content=InterviewAgent.get_instructions(
                instructions=interview_instructions,
                start_time=interview_start_time,
                is_summary_phase=True
            )
        )
        
        await session.say("The main interview phase has ended. Now I will provide a comprehensive summary of your performance, including your strong points, weak points, and specific suggestions for how you can improve.")
        
        # Summary phase
        await asyncio.sleep(SUMMARY_PHASE_DURATION)
        logger.info(f"Interview complete. Disconnecting.")
        
        await session.say("Thank you for your time today. The interview session is now complete. I wish you the best of luck!")
        
        # Save the transcript
        await save_transcript(ctx.room.name, session.chat_ctx)
        
        # Give time for the final message to be spoken
        await asyncio.sleep(5)
        await ctx.room.disconnect()
        
    except asyncio.CancelledError:
        logger.info("Interview timer cancelled")
    finally:
        if transcript_saver_task:
            transcript_saver_task.cancel()
            try:
                await transcript_saver_task
            except asyncio.CancelledError:
                pass
        
        # Final save of the transcript
        await save_transcript(ctx.room.name, session.chat_ctx)


if __name__ == "__main__":
    cli.run_app(server)

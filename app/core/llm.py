from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings

def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-lite",
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.7
    )

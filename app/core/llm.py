from langchain_openai import ChatOpenAI
# from google.generativeai import genai
from app.core.config import settings

def get_llm():
    return ChatOpenAI(
        # model="kwaipilot/kat-coder-pro:free",
        model="amazon/nova-2-lite-v1:free",
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.7
    )
    # return genai.Client(api_key=settings.GOOGLE_API_KEY)

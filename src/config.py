import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("DASHSCOPE_API_KEY", os.getenv("OPENAI_API_KEY", ""))))

# API Endpoints
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Model configurations
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct")

# Default settings
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "250"))


def get_gemini_client(temperature: float = 0.0, model_name: Optional[str] = None):
    """
    Initializes and returns the ChatGoogleGenerativeAI instance.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in the environment or .env file.")
    
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    return ChatGoogleGenerativeAI(
        model=model_name or GEMINI_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=8192,
    )


def get_llm_client(
    provider: str = "gemini",
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.0,
):
    """
    Universal factory for LLM clients supporting Gemini, OpenRouter (Qwen 2.5), OpenAI,
    Groq, or local endpoints (Ollama/vLLM).
    """
    prov = (provider or "gemini").lower()
    
    if prov == "gemini":
        key = api_key or GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name or GEMINI_MODEL,
            google_api_key=key,
            temperature=temperature,
            max_output_tokens=8192,
        )

    elif prov in ("qwen", "openrouter", "openai_compatible", "openai"):
        key = api_key or (QWEN_API_KEY if prov in ("qwen", "openrouter") else OPENAI_API_KEY)
        endpoint = base_url or (QWEN_BASE_URL if prov in ("qwen", "openrouter") else OPENAI_BASE_URL)
        model = model_name or (QWEN_MODEL if prov in ("qwen", "openrouter") else OPENAI_MODEL)
        
        if not key:
            raise ValueError(f"API key is required for provider '{prov}'. Set OPENROUTER_API_KEY or QWEN_API_KEY.")
            
        headers = None
        if "openrouter.ai" in endpoint.lower():
            headers = {
                "HTTP-Referer": "https://sid-ai.local",
                "X-Title": "SID-AI Engineering Engine"
            }

        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            openai_api_key=key,
            openai_api_base=endpoint,
            temperature=temperature,
            max_tokens=4096,
            default_headers=headers,
        )
        
    elif prov == "groq":
        key = api_key or GROQ_API_KEY
        if not key:
            raise ValueError("GROQ_API_KEY is required for Groq provider.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model_name=model_name or GROQ_MODEL,
            openai_api_key=key,
            openai_api_base="https://api.groq.com/openai/v1",
            temperature=temperature,
        )
        
    else:
        # Fallback to Gemini
        return get_gemini_client(temperature=temperature, model_name=model_name)

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# ── API Keys ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
QWEN_API_KEY       = os.getenv("QWEN_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("DASHSCOPE_API_KEY", os.getenv("OPENAI_API_KEY", ""))))
PATHNOVO_API_KEY   = os.getenv("PATHNOVO_API_KEY", "")

# ── API Endpoints ──────────────────────────────────────────────────────────────
QWEN_BASE_URL    = os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_BASE_URL  = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
PATHNOVO_BASE_URL = os.getenv("PATHNOVO_BASE_URL", "https://api.pathnovo.com/v1/pid/extract")

# ── Model Versions ─────────────────────────────────────────────────────────────
# Gemini: upgraded to 2.5-flash (faster, higher context) with 2.5-pro available for accuracy
GEMINI_MODEL       = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_PRO_MODEL   = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o")
GROQ_MODEL         = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Qwen: upgraded to qwen2.5-vl-72b-instruct for better vision understanding
QWEN_MODEL         = os.getenv("QWEN_MODEL", "qwen/qwen2.5-vl-72b-instruct")

# ── Text Chunking ──────────────────────────────────────────────────────────────
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "250"))

# ── Per-Agent Token Budgets ────────────────────────────────────────────────────
# TextRecognitionAgent needs high token budget for dense tag extraction
TEXT_AGENT_MAX_TOKENS      = int(os.getenv("TEXT_AGENT_MAX_TOKENS", "16384"))
# SymbolRecognitionAgent: moderate budget for bounding-box structured output
SYMBOL_AGENT_MAX_TOKENS    = int(os.getenv("SYMBOL_AGENT_MAX_TOKENS", "8192"))
# PipelineRecognitionAgent: moderate budget for relation/geometry lists
PIPELINE_AGENT_MAX_TOKENS  = int(os.getenv("PIPELINE_AGENT_MAX_TOKENS", "8192"))
# CompilerAgent: highest budget — builds the full engineering graph
COMPILER_MAX_TOKENS        = int(os.getenv("COMPILER_MAX_TOKENS", "32768"))
# Default fallback for all other agents
DEFAULT_MAX_TOKENS         = int(os.getenv("DEFAULT_MAX_TOKENS", "8192"))

# ── Per-Agent Temperature Tuning ───────────────────────────────────────────────
# Text extraction: deterministic (temperature=0.0) for consistent tag parsing
TEXT_AGENT_TEMPERATURE     = float(os.getenv("TEXT_AGENT_TEMPERATURE", "0.0"))
# Symbol detection: slight randomness helps with ambiguous symbols
SYMBOL_AGENT_TEMPERATURE   = float(os.getenv("SYMBOL_AGENT_TEMPERATURE", "0.1"))
# Pipeline/relation tracing: deterministic for consistent topology
PIPELINE_AGENT_TEMPERATURE = float(os.getenv("PIPELINE_AGENT_TEMPERATURE", "0.0"))

# ── Retry & Backoff Policy ─────────────────────────────────────────────────────
LLM_MAX_RETRIES        = int(os.getenv("LLM_MAX_RETRIES", "5"))
LLM_BASE_DELAY_SECONDS = float(os.getenv("LLM_BASE_DELAY_SECONDS", "2.0"))
LLM_MAX_DELAY_SECONDS  = float(os.getenv("LLM_MAX_DELAY_SECONDS", "60.0"))

# ── Pathnovo Enhanced Fallback Settings ───────────────────────────────────────
PATHNOVO_TIMEOUT     = int(os.getenv("PATHNOVO_TIMEOUT", "60"))
PATHNOVO_MAX_RETRIES = int(os.getenv("PATHNOVO_MAX_RETRIES", "3"))

# ── Token Budget Warning Threshold (fraction of max_tokens) ───────────────────
LLM_TOKEN_BUDGET_WARN_THRESHOLD = float(os.getenv("LLM_TOKEN_BUDGET_WARN_THRESHOLD", "0.85"))


def get_gemini_client(temperature: float = 0.0, model_name: Optional[str] = None,
                      max_tokens: Optional[int] = None):
    """
    Initializes and returns the ChatGoogleGenerativeAI instance.
    Defaults to gemini-2.5-flash with configurable token budget.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in the environment or .env file.")
    
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    return ChatGoogleGenerativeAI(
        model=model_name or GEMINI_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=max_tokens or DEFAULT_MAX_TOKENS,
    )


def get_llm_client(
    provider: str = "gemini",
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
):
    """
    Universal factory for LLM clients supporting Gemini (2.5-flash / 2.5-pro),
    OpenRouter (Qwen2.5-VL-72B), OpenAI, Groq, Pathnovo, and local PaddleOCR fallback.
    Accepts per-agent max_tokens for fine-grained token budget control.
    """
    prov = (provider or "gemini").lower()
    _max_tokens = max_tokens or DEFAULT_MAX_TOKENS
    
    if prov == "gemini":
        key = api_key or GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name or GEMINI_MODEL,
            google_api_key=key,
            temperature=temperature,
            max_output_tokens=_max_tokens,
        )

    elif prov == "gemini_pro":
        # High-accuracy path: use Gemini 2.5 Pro for complex structured extraction
        key = api_key or GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini Pro provider.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info(f"Using Gemini Pro model: {GEMINI_PRO_MODEL} (higher accuracy, slower).")
        return ChatGoogleGenerativeAI(
            model=model_name or GEMINI_PRO_MODEL,
            google_api_key=key,
            temperature=temperature,
            max_output_tokens=_max_tokens,
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
            max_tokens=_max_tokens,
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
            max_tokens=_max_tokens,
        )

    elif prov in ("pathnovo", "pathnovo_api"):
        # Pathnovo is a REST API client, not an LLM — return None here;
        # agents handle Pathnovo via PathnovoAPIClient directly.
        logger.info("Provider 'pathnovo' selected. Agents will use PathnovoAPIClient directly.")
        return None

    elif prov in ("paddle", "local", "paddle_ocr"):
        # PaddleOCR is a local OCR engine — return None here;
        # agents handle PaddleOCR via run_paddle_ocr() directly.
        logger.info("Provider 'paddle' selected. Agents will use PaddleOCR locally (zero API cost).")
        return None

    else:
        # Fallback to Gemini
        logger.warning(f"Unknown provider '{prov}'. Falling back to Gemini.")
        return get_gemini_client(temperature=temperature, model_name=model_name, max_tokens=_max_tokens)

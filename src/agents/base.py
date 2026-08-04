import base64
import os
import time
import random
import logging
from typing import Type, TypeVar, Optional, Union, List, Dict, Any
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage
from src.config import get_gemini_client, get_llm_client

T = TypeVar('T', bound=BaseModel)
logger = logging.getLogger(__name__)

class BaseAgent:
    """
    Base Agent class providing multi-provider LLM capabilities (Gemini, Qwen 2.5, OpenAI, Groq, vLLM)
    and multimodal structured decoding.
    """
    def __init__(self, temperature: float = 0.0):
        try:
            self.llm = get_gemini_client(temperature=temperature)
        except Exception:
            self.llm = None

    def encode_image(self, image_path: str) -> str:
        """
        Helper method to encode an image file to a base64 string.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def upload_file_to_api(self, file_path: str) -> Optional[Dict[str, str]]:
        """
        Uploads a file to the Google GenAI File API using the google-genai Client.
        Polls until the file becomes ACTIVE.
        """
        from google import genai
        from src.config import GEMINI_API_KEY
        
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. Skipping File API upload.")
            return None
            
        if not os.path.exists(file_path):
            logger.error(f"File to upload not found: {file_path}")
            return None
            
        try:
            logger.info(f"Uploading file '{file_path}' to Google GenAI File API...")
            client = genai.Client(api_key=GEMINI_API_KEY)
            uploaded = client.files.upload(file=file_path)
            
            # Wait for file to become active
            attempts = 0
            while uploaded.state.name == "PROCESSING" and attempts < 15:
                time.sleep(1)
                uploaded = client.files.get(name=uploaded.name)
                attempts += 1
                
            if uploaded.state.name == "ACTIVE":
                logger.info(f"File uploaded successfully! Name: {uploaded.name}, URI: {uploaded.uri}")
                return {
                    "uri": uploaded.uri,
                    "mime": uploaded.mime_type or "image/png",
                    "name": uploaded.name
                }
            else:
                logger.error(f"File processing failed or timed out. State: {uploaded.state.name}")
                return None
        except Exception as e:
            logger.error(f"Failed to upload file via Google GenAI File API: {e}")
            return None

    def get_target_llm(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ):
        """
        Helper to select the requested LLM client (Gemini, Qwen, OpenAI, etc.).
        """
        if provider and provider.lower() not in ("default", "gemini"):
            return get_llm_client(
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
            )
        if self.llm is not None:
            return self.llm
        return get_gemini_client(temperature=temperature, model_name=model_name)

    def invoke_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        image_path: Optional[str] = None,
        image_mime: str = "image/png",
        image_uri: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> T:
        """
        Invokes the target model with a requested Pydantic output schema.
        Supports text-only and multimodal structured extraction across providers.
        """
        llm_instance = self.get_target_llm(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
        )
        
        structured_llm = llm_instance.with_structured_output(schema)
        
        messages = []
        if system_instruction:
            messages.append(SystemMessage(content=system_instruction))
            
        if image_uri:
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "media",
                    "file_uri": image_uri,
                    "mime_type": image_mime
                }
            ]
            messages.append(HumanMessage(content=content))
        elif image_path:
            base64_image = self.encode_image(image_path)
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_mime};base64,{base64_image}"}
                }
            ]
            messages.append(HumanMessage(content=content))
        else:
            messages.append(HumanMessage(content=prompt))
            
        max_attempts = 5
        delay = 4
        for attempt in range(max_attempts):
            try:
                response = structured_llm.invoke(messages)
                return response
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota exceeded" in err_msg:
                    if attempt < max_attempts - 1:
                        jitter = random.uniform(0.5, 2.5)
                        wait_time = delay + jitter
                        logger.warning(f"Rate limit 429 hit. Waiting {wait_time:.2f} seconds before retry...")
                        time.sleep(wait_time)
                        delay *= 2
                        continue
                raise e

    def invoke_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image_path: Optional[str] = None,
        image_mime: str = "image/png",
        image_uri: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> str:
        """
        Standard text-based model invocation (returns raw string).
        Supports multimodal context via image path or file URI across providers.
        """
        llm_instance = self.get_target_llm(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
        )
        
        messages = []
        if system_instruction:
            messages.append(SystemMessage(content=system_instruction))
            
        if image_uri:
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "media",
                    "file_uri": image_uri,
                    "mime_type": image_mime
                }
            ]
            messages.append(HumanMessage(content=content))
        elif image_path:
            base64_image = self.encode_image(image_path)
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_mime};base64,{base64_image}"}
                }
            ]
            messages.append(HumanMessage(content=content))
        else:
            messages.append(HumanMessage(content=prompt))
            
        max_attempts = 5
        delay = 4
        for attempt in range(max_attempts):
            try:
                response = llm_instance.invoke(messages)
                return str(response.content)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota exceeded" in err_msg:
                    if attempt < max_attempts - 1:
                        jitter = random.uniform(0.5, 2.5)
                        wait_time = delay + jitter
                        logger.warning(f"Rate limit 429 hit. Waiting {wait_time:.2f} seconds before retry...")
                        time.sleep(wait_time)
                        delay *= 2
                        continue
                raise e

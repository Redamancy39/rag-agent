import json
import re
from typing import Any

from app.core.config import get_settings


class LLMConfigError(RuntimeError):
    pass


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise LLMConfigError("OPENAI_API_KEY is required when LLM preprocessing is enabled")
        if not settings.OPENAI_MODEL_NAME:
            raise LLMConfigError("OPENAI_MODEL_NAME is required when LLM preprocessing is enabled")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMConfigError(
                "LLM preprocessing requires openai. Install: pip install -r requirements-rag.txt"
            ) from exc

        self.model_name = settings.OPENAI_MODEL_NAME
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.PREPROCESS_LLM_TIMEOUT_SECONDS,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        content = self.complete_text(system_prompt, user_prompt)
        return _parse_json_object(content)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}

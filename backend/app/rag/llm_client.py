import json
import re
from typing import Any

from app.core.config import get_settings
from app.rag.llm_budget import IngestionLlmBudget


class LLMConfigError(RuntimeError):
    pass


class OpenAICompatibleLLM:
    def __init__(self, *, budget: IngestionLlmBudget | None = None, max_output_tokens: int | None = None) -> None:
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
        self.budget = budget
        self.max_output_tokens = max_output_tokens
        self.last_usage = None
        self.last_finish_reason = None
        self.request_timeout = settings.PREPROCESS_LLM_TIMEOUT_SECONDS
        self.output_limit = getattr(settings, 'INGESTION_LLM_MAX_OUTPUT_TOKENS', 2048)
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.PREPROCESS_LLM_TIMEOUT_SECONDS,
            **({'max_retries': 0} if budget is not None else {}),
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        content = self.complete_text(system_prompt, user_prompt)
        return _parse_json_object(content)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        from openai import APIConnectionError, APIStatusError
        retry_limit = self.budget.max_retries if self.budget else 0
        for attempt in range(retry_limit + 1):
            remaining = self.budget.reserve(retry=attempt > 0) if self.budget else self.request_timeout
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{'role': 'system', 'content': system_prompt},
                              {'role': 'user', 'content': user_prompt}],
                    temperature=0,
                    timeout=min(self.request_timeout, remaining),
                    **({'max_tokens': self.output_limit} if self.budget else {}),
                    **({'max_tokens': self.max_output_tokens} if self.max_output_tokens is not None and not self.budget else {}),
                )
            except Exception as exc:
                if self.budget:
                    self.budget.failures += 1
                    self.budget.emit('API 请求失败')
                retryable = isinstance(exc, APIConnectionError) or (
                    isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500))
                if not self.budget or not retryable or attempt >= retry_limit:
                    raise
                continue
            if self.budget:
                self.budget.successes += 1
                self.budget.emit('收到 API 响应')
            self.last_usage = getattr(response, 'usage', None)
            self.last_finish_reason = getattr(response.choices[0], 'finish_reason', None)
            return response.choices[0].message.content or ''
        raise RuntimeError('LLM retry loop did not return')


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

from collections.abc import Sequence
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import Settings, get_settings
import logging

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    reasoning_details: Any | None = None

    model_config = ConfigDict(extra="allow")


class LLMResponse(BaseModel):
    content: str
    reasoning_details: Any | None = None
    raw_message: dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""

    model_config = ConfigDict(extra="forbid")


class OpenRouterClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if self.settings.openrouter_api_key is None:
            msg = "OPENROUTER_API_KEY is required to initialize the OpenRouter client."
            raise ValueError(msg)
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.settings.openrouter_api_key.get_secret_value(),
        )

    def generate_completion(
        self,
        model: str,
        messages: Sequence[ChatMessage | dict[str, Any]],
        use_reasoning: bool,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload_messages = [
            message.model_dump(exclude_none=True) if isinstance(message, ChatMessage) else message
            for message in messages
        ]
        request: dict[str, Any] = {
            "model": model,
            "messages": payload_messages,
            "temperature": temperature,
        }
        if use_reasoning:
            request["extra_body"] = {"reasoning": {"enabled": True}}

        response = self.client.chat.completions.create(**request)
        message = response.choices[0].message
        raw_message = message.model_dump(exclude_none=True)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
        logger.info(
            "LLM call: model=%s, prompt_tokens=%d, completion_tokens=%d, total_tokens=%d",
            model, prompt_tokens, completion_tokens, total_tokens,
        )
        return LLMResponse(
            content=message.content or "",
            reasoning_details=getattr(message, "reasoning_details", None),
            raw_message=raw_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
        )


def get_openrouter_client(settings: Settings | None = None) -> OpenRouterClient:
    return OpenRouterClient(settings=settings)

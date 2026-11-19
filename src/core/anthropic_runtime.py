"""
Anthropic (Claude) runtime cho Red / Red Advance khi ``RED_TEAM_PROVIDER=claude``.

  - ``AnthropicRunner``   : cùng giao diện plugin như ``OpenAIRunner`` nhưng gọi
                            Claude qua Anthropic SDK (Messages API).
  - ``AnthropicNemoModel``: adapter ``nemoguardrails.types.LLMModel`` để NeMo
                            self-check input/output cũng chạy bằng Claude.

Model mặc định: ``claude-haiku-5-5`` (rẻ nhất). Haiku 5.5 không nhận giá trị
``temperature`` / ``top_p`` / ``top_k`` khác mặc định, nên adapter bỏ qua các tham số
sampling mà starter / NeMo truyền vào.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, List, Optional, Union

from core.config import get_anthropic_api_key, get_red_model
from core.openai_runtime import OpenAIAgent, OpenAIRunner

# Effort thấp cho chatbot / phân loại → ít token thinking, rẻ hơn.
DEFAULT_EFFORT = "low"
DEFAULT_MAX_TOKENS = 8000


def _anthropic_kwargs() -> dict:
    key = get_anthropic_api_key()
    return {"api_key": key} if key else {}


def _response_text(message) -> str:
    """Ghép các text block; refusal không có text → trả câu từ chối ngắn."""
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if not text and message.stop_reason == "refusal":
        return "I can't help with that request."
    return text


@dataclass
class AnthropicRunner(OpenAIRunner):
    """``OpenAIRunner`` với bước LLM thay bằng Claude Messages API."""

    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS

    def _client(self):
        import anthropic

        return anthropic.AsyncAnthropic(**_anthropic_kwargs())

    async def _complete(self, agent: OpenAIAgent, user_message: str) -> str:
        client = self._client()
        message = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=agent.instruction,
            messages=[{"role": "user", "content": user_message}],
            output_config={"effort": self.effort},
        )
        return _response_text(message)


def create_anthropic_pair(
    *,
    name: str,
    instruction: str,
    app_name: str,
    plugins: list | None = None,
    input_hooks: list | None = None,
    output_hooks: list | None = None,
    model: str | None = None,
    **_ignored: Any,  # temperature: Haiku 5.5 không nhận giá trị khác mặc định
) -> tuple[OpenAIAgent, AnthropicRunner]:
    agent = OpenAIAgent(name=name, instruction=instruction, provider="anthropic")
    runner = AnthropicRunner(
        app_name=app_name,
        model=model or get_red_model(),
        provider="anthropic",
        plugins=list(plugins or []),
        input_hooks=list(input_hooks or []),
        output_hooks=list(output_hooks or []),
    )
    return agent, runner


class AnthropicNemoModel:
    """NeMo Guardrails ``LLMModel`` backed by the Anthropic SDK (self-check rails)."""

    def __init__(self, model: str | None = None, *, effort: str = DEFAULT_EFFORT,
                 max_tokens: int = 4000):
        import anthropic

        self._model = model or get_red_model()
        self._effort = effort
        self._max_tokens = max_tokens
        self._client = anthropic.AsyncAnthropic(**_anthropic_kwargs())

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> Optional[str]:
        return "anthropic"

    @property
    def provider_url(self) -> Optional[str]:
        return str(self._client.base_url)

    @staticmethod
    def _split(prompt: Union[str, List[Any]]) -> tuple[str | None, list[dict]]:
        if isinstance(prompt, str):
            return None, [{"role": "user", "content": prompt}]
        system_parts: list[str] = []
        messages: list[dict] = []
        for msg in prompt:
            d = msg.to_dict() if hasattr(msg, "to_dict") else dict(msg)
            role, content = d.get("role"), d.get("content") or ""
            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
        if not messages or messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": "(context)"})
        return ("\n\n".join(system_parts) or None), messages

    async def generate_async(self, prompt, *, stop: Optional[List[str]] = None, **kwargs):
        from nemoguardrails.types import LLMResponse

        system, messages = self._split(prompt)
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max(int(kwargs.get("max_tokens") or 0), self._max_tokens),
            "messages": messages,
            "output_config": {"effort": self._effort},
        }
        if system:
            params["system"] = system
        if stop:
            params["stop_sequences"] = list(stop)
        message = await self._client.messages.create(**params)
        return LLMResponse(
            content=_response_text(message),
            model=message.model,
            finish_reason="stop" if message.stop_reason != "max_tokens" else "length",
            request_id=getattr(message, "_request_id", None),
        )

    async def stream_async(self, prompt, *, stop: Optional[List[str]] = None,
                           **kwargs) -> AsyncIterator[Any]:
        from nemoguardrails.types import LLMResponseChunk

        response = await self.generate_async(prompt, stop=stop, **kwargs)
        yield LLMResponseChunk(delta_content=response.content, model=response.model,
                               finish_reason=response.finish_reason)

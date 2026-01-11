"""
Unified LLM provider abstraction layer.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests
import structlog

from .telemetry import meter

logger = structlog.get_logger(__name__)


# Telemetry instruments
provider_calls_counter = meter.create_counter(
    "llm.api.calls.total",
    description="Total number of LLM API calls across providers",
)
provider_errors_counter = meter.create_counter(
    "llm.api.errors.total",
    description="Total number of LLM API errors across providers",
)
provider_latency_histogram = meter.create_histogram(
    "llm.api.latency.ms", description="Latency of LLM calls across providers"
)
provider_overload_counter = meter.create_counter(
    "llm.api.overloads.total",
    description="Total number of overload or rate-limit responses",
)


@dataclass
class LLMResult:
    """Structured response for LLM providers."""

    success: bool
    response_text: Optional[str] = None
    error_message: Optional[str] = None
    provider: str = "grok"
    model: Optional[str] = None
    channel_used: Optional[str] = "default"
    latency_ms: float = 0.0
    status_code: Optional[int] = None
    raw_response: Optional[Any] = None
    request_id: Optional[str] = None
    rate_limited: bool = False
    load_info: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_overloaded(self) -> bool:
        if self.rate_limited:
            return True
        if self.status_code in (429, 503):
            return True
        if self.error_message:
            lower = self.error_message.lower()
            return "overload" in lower or "rate limit" in lower or "too many" in lower
        return False

    @property
    def extracted_load(self) -> Optional[int]:
        if self.load_info and isinstance(self.load_info, dict):
            return self.load_info.get("load")
        if not self.error_message:
            return None
        if "load=" in self.error_message:
            try:
                return int(self.error_message.split("load=")[1].split()[0].strip(","))
            except Exception:
                return None
        return None

    @property
    def extracted_requests(self) -> Optional[int]:
        if self.load_info and isinstance(self.load_info, dict):
            return self.load_info.get("num_requests")
        if not self.error_message:
            return None
        if "num_requests=" in self.error_message:
            try:
                return int(
                    self.error_message.split("num_requests=")[1].split()[0].strip(",")
                )
            except Exception:
                return None
        return None


class LLMProvider:
    """Abstract provider."""

    provider_name: str = "base"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def call(self, prompt: str, **kwargs) -> LLMResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def _record_metrics(self, result: LLMResult):
        labels = {"provider": result.provider, "model": result.model or self.model or ""}
        provider_calls_counter.add(1, labels=labels)
        provider_latency_histogram.record(result.latency_ms, labels=labels)
        if not result.success:
            provider_errors_counter.add(1, labels=labels)
        if result.is_overloaded:
            provider_overload_counter.add(1, labels=labels)

    def _request_json(
        self, url: str, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> (requests.Response, float):
        start_time = time.time()
        response = requests.post(
            url, headers=headers, json=payload, timeout=self.timeout
        )
        latency_ms = (time.time() - start_time) * 1000
        return response, latency_ms


class GrokProvider(LLMProvider):
    provider_name = "grok"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = "grok-beta",
        base_url: Optional[str] = "https://api.x.ai/v1",
        timeout: float = 30.0,
    ):
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

    def call(self, prompt: str, channel: Optional[str] = None, was_reduced: bool = False):
        selected_channel = channel or "default"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Client-Version": "grok-ppo/1.0",
        }
        if channel:
            headers["X-Grok-Channel"] = channel

        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": self.model or "grok-beta",
            "max_tokens": 1000,
            "temperature": 0.7,
        }
        if was_reduced:
            payload["note"] = "prompt_reduced_for_load"

        try:
            response, latency_ms = self._request_json(
                f"{self.base_url}/chat/completions", headers, payload
            )
            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                result = LLMResult(
                    success=True,
                    response_text=text,
                    provider=self.provider_name,
                    model=payload["model"],
                    channel_used=selected_channel,
                    latency_ms=latency_ms,
                    raw_response=data,
                    request_id=data.get("id"),
                )
            else:
                result = LLMResult(
                    success=False,
                    error_message=response.text,
                    provider=self.provider_name,
                    model=payload["model"],
                    channel_used=selected_channel,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                )
        except requests.exceptions.Timeout:
            result = LLMResult(
                success=False,
                error_message=f"Timeout after {int(self.timeout)}s",
                provider=self.provider_name,
                model=self.model,
                channel_used=selected_channel,
                latency_ms=self.timeout * 1000,
                status_code=408,
            )
        except Exception as exc:  # pragma: no cover - defensive
            result = LLMResult(
                success=False,
                error_message=f"Network error: {exc}",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel or "default",
                latency_ms=0.0,
            )

        self._record_metrics(result)
        return result


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = "gpt-4o-mini",
        base_url: Optional[str] = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ):
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

    def call(self, prompt: str, **kwargs):
        channel = kwargs.get("channel") or "default"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response, latency_ms = self._request_json(
                f"{self.base_url}/chat/completions", headers, payload
            )
            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                result = LLMResult(
                    success=True,
                    response_text=text,
                    provider=self.provider_name,
                    model=payload["model"],
                    channel_used=channel,
                    latency_ms=latency_ms,
                    raw_response=data,
                    request_id=data.get("id"),
                )
            else:
                result = LLMResult(
                    success=False,
                    error_message=response.text,
                    provider=self.provider_name,
                    model=payload["model"],
                    channel_used=channel,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                )
        except requests.exceptions.Timeout:
            result = LLMResult(
                success=False,
                error_message=f"Timeout after {int(self.timeout)}s",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=self.timeout * 1000,
                status_code=408,
            )
        except Exception as exc:  # pragma: no cover
            result = LLMResult(
                success=False,
                error_message=f"Network error: {exc}",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=0.0,
            )

        self._record_metrics(result)
        return result


class GoogleProvider(LLMProvider):
    provider_name = "google"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = "gemini-1.5-pro",
        base_url: Optional[str] = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 30.0,
    ):
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

    def call(self, prompt: str, **kwargs):
        channel = kwargs.get("channel") or "default"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        try:
            response, latency_ms = self._request_json(url, headers, payload)
            if response.status_code == 200:
                data = response.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text")
                )
                result = LLMResult(
                    success=True,
                    response_text=text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    raw_response=data,
                    request_id=data.get("responseId") or data.get("id"),
                )
            else:
                result = LLMResult(
                    success=False,
                    error_message=response.text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                )
        except requests.exceptions.Timeout:
            result = LLMResult(
                success=False,
                error_message=f"Timeout after {int(self.timeout)}s",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=self.timeout * 1000,
                status_code=408,
            )
        except Exception as exc:  # pragma: no cover
            result = LLMResult(
                success=False,
                error_message=f"Network error: {exc}",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=0.0,
            )

        self._record_metrics(result)
        return result


class AnthropicProvider(LLMProvider):
    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = "claude-3-opus-20240229",
        base_url: Optional[str] = "https://api.anthropic.com",
        timeout: float = 30.0,
        api_version: str = "2023-06-01",
    ):
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)
        self.api_version = api_version

    def call(self, prompt: str, **kwargs):
        channel = kwargs.get("channel") or "default"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response, latency_ms = self._request_json(
                f"{self.base_url}/v1/messages", headers, payload
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("content", [{}])[0].get("text")
                result = LLMResult(
                    success=True,
                    response_text=text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    raw_response=data,
                    request_id=data.get("id"),
                )
            else:
                result = LLMResult(
                    success=False,
                    error_message=response.text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                )
        except requests.exceptions.Timeout:
            result = LLMResult(
                success=False,
                error_message=f"Timeout after {int(self.timeout)}s",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=self.timeout * 1000,
                status_code=408,
            )
        except Exception as exc:  # pragma: no cover
            result = LLMResult(
                success=False,
                error_message=f"Network error: {exc}",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=0.0,
            )

        self._record_metrics(result)
        return result


class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = "deepseek-chat",
        base_url: Optional[str] = "https://api.deepseek.com",
        timeout: float = 30.0,
    ):
        super().__init__(api_key, model=model, base_url=base_url, timeout=timeout)

    def call(self, prompt: str, **kwargs):
        channel = kwargs.get("channel") or "default"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response, latency_ms = self._request_json(
                f"{self.base_url}/v1/chat/completions", headers, payload
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content")
                result = LLMResult(
                    success=True,
                    response_text=text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    raw_response=data,
                    request_id=data.get("id"),
                )
            else:
                result = LLMResult(
                    success=False,
                    error_message=response.text,
                    provider=self.provider_name,
                    model=self.model,
                    channel_used=channel,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                )
        except requests.exceptions.Timeout:
            result = LLMResult(
                success=False,
                error_message=f"Timeout after {int(self.timeout)}s",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=self.timeout * 1000,
                status_code=408,
            )
        except Exception as exc:  # pragma: no cover
            result = LLMResult(
                success=False,
                error_message=f"Network error: {exc}",
                provider=self.provider_name,
                model=self.model,
                channel_used=channel,
                latency_ms=0.0,
            )

        self._record_metrics(result)
        return result


def build_provider(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMProvider:
    """Factory to create a provider with sensible defaults and env fallbacks."""
    name = (provider_name or "grok").lower()
    provider_env_map = {
        "grok": ["GROK_API_KEY", "XAI_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "google": ["GOOGLE_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
    }

    resolved_key = api_key
    for candidate_env in provider_env_map.get(name, []):
        if resolved_key:
            break
        resolved_key = os.getenv(candidate_env)

    if not resolved_key:
        raise ValueError(
            f"API key for provider '{provider_name}' not provided. "
            f"Set one of {provider_env_map.get(name, ['<none>'])} or pass --api-key."
        )

    provider_kwargs = {"api_key": resolved_key, "model": model}
    if base_url is not None:
        provider_kwargs["base_url"] = base_url

    if name == "grok":
        return GrokProvider(**provider_kwargs)
    if name == "openai":
        return OpenAIProvider(**provider_kwargs)
    if name == "google":
        return GoogleProvider(**provider_kwargs)
    if name == "anthropic":
        return AnthropicProvider(**provider_kwargs)
    if name == "deepseek":
        return DeepSeekProvider(**provider_kwargs)

    raise ValueError(f"Unsupported provider '{provider_name}'")

from types import SimpleNamespace

import grok_ppo_enterprise.llm_provider as llm
from grok_ppo_enterprise.llm_provider import (
    AnthropicProvider,
    DeepSeekProvider,
    GoogleProvider,
    GrokProvider,
    LLMResult,
    OpenAIProvider,
    build_provider,
)
from grok_ppo_enterprise.grok_env import GrokAPIEnvironment, GrokAction
from grok_ppo_enterprise.telemetry import meter


class DummyResponse(SimpleNamespace):
    def __init__(self, status_code=200, json_data=None, text=""):
        super().__init__(status_code=status_code, _json=json_data or {}, text=text)

    def json(self):
        return self._json


def _fake_post(expected_payload, response_obj):
    def _post(url, headers=None, json=None, timeout=None):
        # mirror a minimal requests.Response interface
        assert json["messages"][0]["content"] == expected_payload
        return response_obj

    return _post


def test_build_provider_env_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    provider = build_provider("openai")
    assert isinstance(provider, OpenAIProvider)
    assert provider.api_key == "env-openai-key"


def test_grok_provider_success(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(
        status_code=200,
        json_data={"choices": [{"message": {"content": "grok reply"}},], "id": "1"},
    )
    monkeypatch.setattr(llm.requests, "post", _fake_post("hello", response))
    provider = GrokProvider(api_key="test-key", model="grok-beta")
    result = provider.call("hello")
    assert isinstance(result, LLMResult)
    assert result.success is True
    assert result.response_text == "grok reply"
    assert result.provider == "grok"


def test_openai_provider_error(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(status_code=500, text="internal error")
    monkeypatch.setattr(llm.requests, "post", _fake_post("hi", response))
    provider = OpenAIProvider(api_key="openai-key", model="gpt-4o")
    result = provider.call("hi")
    assert result.success is False
    assert "internal error" in (result.error_message or "")
    assert result.channel_used == "default"


def test_google_provider_success(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(
        status_code=200,
        json_data={
            "candidates": [{"content": {"parts": [{"text": "gemini reply"}]}}],
            "responseId": "resp-1",
        },
    )

    def _google_post(url, headers=None, json=None, timeout=None):
        assert "generateContent" in url
        return response

    monkeypatch.setattr(llm.requests, "post", _google_post)
    provider = GoogleProvider(api_key="google-key", model="gemini-pro")
    result = provider.call("anything")
    assert result.success
    assert result.response_text == "gemini reply"
    assert result.channel_used == "default"


def test_anthropic_provider_success(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(
        status_code=200,
        json_data={"content": [{"text": "claude reply"}], "id": "anthropic-id"},
    )

    def _anthropic_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/v1/messages")
        return response

    monkeypatch.setattr(llm.requests, "post", _anthropic_post)
    provider = AnthropicProvider(api_key="anthropic-key")
    result = provider.call("hello world")
    assert result.success
    assert result.response_text == "claude reply"
    assert result.channel_used == "default"


def test_deepseek_provider_success(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(
        status_code=200,
        json_data={
            "choices": [{"message": {"content": "deepseek reply"}}],
            "id": "deep-id",
        },
    )

    def _deepseek_post(url, headers=None, json=None, timeout=None):
        assert "/v1/chat/completions" in url
        return response

    monkeypatch.setattr(llm.requests, "post", _deepseek_post)
    provider = DeepSeekProvider(api_key="deepseek-key")
    result = provider.call("question")
    assert result.success
    assert result.response_text == "deepseek reply"
    assert result.channel_used == "default"


def test_build_provider_retains_default_base_urls(monkeypatch):
    provider_defaults = {
        "grok": ("GROK_API_KEY", "https://api.x.ai/v1"),
        "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
        "google": ("GOOGLE_API_KEY", "https://generativelanguage.googleapis.com/v1beta"),
        "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com"),
        "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    }

    for name, (env_var, expected_url) in provider_defaults.items():
        monkeypatch.setenv(env_var, f"{name}-key")
        provider = build_provider(name)
        assert provider.base_url == expected_url


def test_providers_propagate_channel_used(monkeypatch):
    meter.clear_metrics()
    response = DummyResponse(
        status_code=200,
        json_data={"choices": [{"message": {"content": "openai reply"}}], "id": "2"},
    )
    monkeypatch.setattr(llm.requests, "post", _fake_post("chan-test", response))
    provider = OpenAIProvider(api_key="openai-key")
    result = provider.call("chan-test", channel="backup-1")
    assert result.channel_used == "backup-1"

    default_channel_result = provider.call("chan-test")
    assert default_channel_result.channel_used == "default"


def test_build_provider_preserves_default_base_urls():
    providers = [
        ("grok", GrokProvider, "https://api.x.ai/v1"),
        ("openai", OpenAIProvider, "https://api.openai.com/v1"),
        (
            "google",
            GoogleProvider,
            "https://generativelanguage.googleapis.com/v1beta",
        ),
        ("anthropic", AnthropicProvider, "https://api.anthropic.com"),
        ("deepseek", DeepSeekProvider, "https://api.deepseek.com"),
    ]

    for name, klass, default_url in providers:
        provider = build_provider(name, api_key=f"{name}-key")
        assert isinstance(provider, klass)
        assert provider.base_url == default_url


def test_calculate_reward_handles_missing_channel():
    env = GrokAPIEnvironment(
        api_key="dummy", provider=OpenAIProvider(api_key="openai-key"), provider_name="openai"
    )
    result = LLMResult(
        success=True,
        response_text="ok",
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=800,
        channel_used=None,
    )

    reward = env._calculate_reward(GrokAction.TRY_CURRENT_CHANNEL, result)
    assert reward == 3.0

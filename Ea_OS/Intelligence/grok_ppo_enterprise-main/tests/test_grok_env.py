import pytest

from grok_ppo_enterprise.grok_env import GrokAPIEnvironment, GrokAction
from grok_ppo_enterprise.llm_provider import LLMResult, OpenAIProvider


def test_calculate_reward_handles_missing_channel_and_error_message(monkeypatch):
    provider = OpenAIProvider(api_key="dummy-key")
    env = GrokAPIEnvironment(
        api_key="dummy-key", provider=provider, provider_name="openai", model="gpt-4o"
    )

    result = LLMResult(
        success=False,
        error_message=None,
        channel_used=None,
        provider="openai",
        model="gpt-4o",
        latency_ms=100.0,
    )

    reward = env._calculate_reward(GrokAction.TRY_CURRENT_CHANNEL, result)
    assert isinstance(reward, float)

from grok_ppo_enterprise.cli_integration import SmartLLMCaller, create_smart_caller


def test_create_smart_caller_uses_provider_name(monkeypatch):
    caller = create_smart_caller(api_key="fake-key", provider_name="openai", model="gpt-4o")
    assert isinstance(caller, SmartLLMCaller)
    assert caller.env.provider.provider_name == "openai"
    assert caller.env.provider.model == "gpt-4o"

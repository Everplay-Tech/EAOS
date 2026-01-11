# Grok PPO Enterprise 🤖

Smart API caller that learns to avoid rate limits and overloads using Reinforcement Learning from Human Feedback (RLHF). Now supports multiple enterprise-grade LLM backends through a unified provider interface.

## ✨ Features

- **Smart API Routing**: Learns which API channels are least loaded and adapts dynamically.
- **Multi-Provider LLM Support**: Grok (default), OpenAI, Google Gemini, Anthropic Claude, and DeepSeek via a pluggable `LLMProvider` abstraction.
- **Automatic Retry Logic**: Intelligently retries failed requests with optimal strategies.
- **RLHF Integration**: Learn from human/YGI preferences about what constitutes "good" API behavior.
- **DPO Training**: Direct Preference Optimization for aligning with human preferences.
- **Real-time Monitoring**: Telemetry and metrics for all API interactions with provider/model labels.
- **Caching**: Smart response caching to reduce API load.

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/yourusername/grok-ppo-enterprise.git
cd grok-ppo-enterprise
pip install -e .
```

### Configure API keys

Set one of the following environment variables depending on the provider you want to call:

- Grok: `GROK_API_KEY` or `XAI_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- Google Gemini: `GOOGLE_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- DeepSeek: `DEEPSEEK_API_KEY`

You can also pass `--api-key` directly to the CLI for one-off overrides.

### Call the LLM

```bash
# Default (Grok) remains unchanged
grok-ppo call "Explain quantum computing to a 5-year-old"

# OpenAI
grok-ppo call "Summarize this legal text" --provider openai --model gpt-4o --api-key $OPENAI_API_KEY

# Anthropic
grok-ppo call "Write code" --provider anthropic --model claude-3-opus-20240229

# Google Gemini
grok-ppo call "Explain this" --provider google --model gemini-1.5-pro --api-key $GOOGLE_API_KEY

# DeepSeek
grok-ppo call "Innovative AI research" --provider deepseek --model deepseek-chat
```

Use `-v` to see the agent’s reasoning and channel/telemetry details:

```bash
grok-ppo call -v "Debug this SQL" --provider openai
```

### Other commands

- Train DPO on collected preferences: `grok-ppo train-dpo`
- Check metrics/status: `grok-ppo status --metrics`
- RLHF utilities: `grok-ppo rlhf list|visualize|label|stats`

## 📐 Architecture

- **LLMProvider abstraction**: Implements authentication, request/response adaptation, and metrics per provider.
- **SmartLLMCaller**: RL-powered caller that selects actions to avoid overloads while remaining provider-agnostic.
- **Telemetry**: Provider/model labels added to latency, error, and overload metrics for observability.

## 🧪 Development

```bash
pip install -e ".[dev,cli]"
pytest
```

Contributions welcome! Open issues or PRs for new providers or improvements.

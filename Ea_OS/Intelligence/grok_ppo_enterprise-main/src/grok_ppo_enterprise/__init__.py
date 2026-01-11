"""
Grok PPO Enterprise - Smart API Optimization with RLHF
"""
__version__ = "1.0.0"
__author__ = "Grok PPO Team"
__description__ = "Smart API caller that learns to avoid rate limits using RLHF"

# Export main classes and functions
from .agent import PPOActorCritic, ReplayBuffer
from .dpo import DPOTrainer
from .rlhf import RLHFCollector, rlhf_collector
from .telemetry import TelemetryMeter, meter, Counter, Histogram, Gauge
from .grok_env import GrokAPIEnvironment, GrokAction
from .llm_provider import (
    LLMProvider,
    LLMResult,
    GrokProvider,
    OpenAIProvider,
    GoogleProvider,
    AnthropicProvider,
    DeepSeekProvider,
    build_provider,
)
from .cli_integration import SmartLLMCaller, SmartGrokCaller, create_smart_caller

# For easy import
__all__ = [
    # Core components
    "PPOActorCritic",
    "ReplayBuffer",
    "DPOTrainer",
    "RLHFCollector",
    "rlhf_collector",
    "TelemetryMeter",
    "meter",
    "Counter",
    "Histogram",
    "Gauge",
    # Providers
    "LLMProvider",
    "LLMResult",
    "GrokProvider",
    "OpenAIProvider",
    "GoogleProvider",
    "AnthropicProvider",
    "DeepSeekProvider",
    "build_provider",
    # Grok API environment
    "GrokAPIEnvironment",
    "GrokAction",
    # CLI integration
    "SmartLLMCaller",
    "SmartGrokCaller",
    "create_smart_caller",
]

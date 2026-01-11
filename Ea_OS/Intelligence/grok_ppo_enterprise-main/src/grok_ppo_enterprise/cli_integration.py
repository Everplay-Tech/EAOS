"""
FILE: src/grok_ppo_enterprise/cli_integration.py
Integration of GrokAPIEnvironment with existing CLI and multi-provider support.
"""
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import torch

from .agent import PPOActorCritic
from .grok_env import GrokAPIEnvironment, GrokAction
from .llm_provider import LLMProvider, build_provider
from .rlhf import rlhf_collector


class SmartLLMCaller:
    """
    Replaces direct API calls with learned agent that avoids overloads.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model_path: Optional[Path] = None,
    ):
        self.env = GrokAPIEnvironment(
            api_key=provider.api_key,
            provider=provider,
            provider_name=provider.provider_name,
            model=provider.model,
            base_url=provider.base_url or "",
        )

        # Initialize or load agent
        self.agent = PPOActorCritic(
            state_dim=self.env.state_dim, action_dim=self.env.action_dim
        )

        if model_path and model_path.exists():
            self.agent.load_state_dict(torch.load(model_path))
            print(f"✓ Loaded trained agent from {model_path}")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.agent.to(self.device)

    def call_with_learning(
        self, prompt: str, max_attempts: int = 5, verbose: bool = False
    ) -> str:
        """
        Make a smart API call that learns from experience.
        Returns the response or error message.
        """
        # Reset for new request
        state = self.env.reset()
        states_history = [state.copy()]
        actions_history = []
        results_history = []
        rewards_history = []

        attempt = 0
        response_text = None

        if verbose:
            print(f"\n🤖 Smart API call for: {prompt[:50]}...")
            print(
                f"   Provider: {self.env.provider.provider_name}, "
                f"Model: {self.env.provider.model}"
            )
            print(f"   Initial channel: {self.env.current_channel}")

        while attempt < max_attempts:
            attempt += 1

            # Agent chooses action based on state
            with torch.no_grad():
                state_tensor = torch.tensor(
                    state, dtype=torch.float32, device=self.device
                ).unsqueeze(0)
                logits, _ = self.agent(state_tensor)
                action_idx = torch.argmax(logits, dim=-1).item()

            action = GrokAction(action_idx)

            if verbose:
                print(f"\n  Attempt {attempt}:")
                print(f"    State: {self._format_state(state)}")
                print(f"    Action: {action.description}")

            # Execute action
            new_state, reward, done, result = self.env.step(action_idx, prompt)

            # Record for trajectory
            states_history.append(new_state.copy())
            actions_history.append(action_idx)
            results_history.append(
                {
                    "success": result.success,
                    "error": result.error_message,
                    "channel": result.channel_used,
                    "latency_ms": result.latency_ms,
                    "overloaded": result.is_overloaded,
                    "provider": result.provider,
                    "model": result.model,
                }
            )
            rewards_history.append(reward)

            if verbose:
                if result.success:
                    print(f"    ✅ Success on channel: {result.channel_used}")
                    print(f"    Latency: {result.latency_ms:.0f}ms")
                else:
                    if result.is_overloaded:
                        print(f"    ❌ OVERLOADED: {result.channel_used}")
                        if result.extracted_load:
                            print(
                                f"       Load: {result.extracted_load}, "
                                f"Requests: {result.extracted_requests or 'N/A'}"
                            )
                    else:
                        err_msg = result.error_message or "Unknown error"
                        print(f"    ❌ Error: {err_msg[:80]}...")
                    print(f"    Reward: {reward:.2f}")

            if result.success:
                response_text = result.response_text
                if verbose:
                    print(f"\n🎯 Success in {attempt} attempts!")
                    print(f"   Final channel: {result.channel_used}")
                    print(f"   Total reward: {sum(rewards_history):.2f}")
                break

            if done:
                if verbose:
                    print(f"\n⚠️  Stopping after {attempt} attempts (done flag)")
                break

            state = new_state

        # Record trajectory for DPO training
        trajectory = self._create_trajectory(
            prompt=prompt,
            states=states_history,
            actions=actions_history,
            results=results_history,
            rewards=rewards_history,
            success=result.success if "result" in locals() else False,
            final_channel=self.env.current_channel,
            attempts=attempt,
            provider=self.env.provider.provider_name,
            model=self.env.provider.model,
        )

        traj_id = rlhf_collector.record_trajectory(trajectory)

        if verbose and traj_id:
            print(f"\n📊 Trajectory saved: {traj_id}")
            print(f"   Total steps: {len(actions_history)}")

        if response_text:
            return response_text
        elif results_history:
            last_error = results_history[-1].get("error", "Unknown error")
            return f"Error after {attempt} attempts: {last_error}"
        else:
            return "Error: No API attempts made"

    def _create_trajectory(self, **kwargs) -> Dict:
        return {
            **kwargs,
            "timestamp": time.time(),
            "state_dim": self.env.state_dim,
            "action_meanings": self.env.get_action_meanings(),
        }

    def _format_state(self, state: List[float]) -> str:
        if len(state) >= 10:
            return (
                f"Load:{state[0]:.1%} Err:{state[2]:.1%} "
                f"Retry:{state[5]*5:.0f}/5 Alt:{state[9]:.0%}"
            )
        return str(state)

    def get_channel_report(self) -> str:
        report = self.env.get_channel_report()
        lines = [
            "📡 Channel Status:",
            f"  Provider: {self.env.provider.provider_name}",
            f"  Model: {self.env.provider.model}",
        ]
        for channel, stats in report.items():
            status = "✅" if stats["is_available"] else "❌"
            lines.append(
                f"  {status} {channel}: "
                f"Success={stats['success_rate']} "
                f"Latency={stats['avg_latency_ms']}ms "
                f"Load={stats['load_estimate']}"
            )
        return "\n".join(lines)

    def save_agent(self, path: Path):
        """Save the trained agent"""
        torch.save(self.agent.state_dict(), path)
        print(f"✓ Agent saved to {path}")


def create_smart_caller(
    api_key: Optional[str] = None,
    provider_name: str = "grok",
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> SmartLLMCaller:
    """
    Factory function to create SmartLLMCaller.
    If no API key provided, tries to get it from environment for the provider.
    """
    provider = build_provider(provider_name, api_key=api_key, model=model, base_url=base_url)

    # Check for saved model
    model_path = Path("~/.grok_ppo_enterprise/models/smart_caller.pt").expanduser()

    return SmartLLMCaller(provider, model_path if model_path.exists() else None)


# Backwards compatibility export
SmartGrokCaller = SmartLLMCaller

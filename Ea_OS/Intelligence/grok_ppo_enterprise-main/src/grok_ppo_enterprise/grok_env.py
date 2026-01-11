"""
FILE: src/grok_ppo_enterprise/grok_env.py
Real Grok API Environment for Learning to Avoid Rate Limits
Generalized to support multiple LLM providers while retaining legacy naming.
"""
import json
import random
import re
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .llm_provider import LLMProvider, LLMResult, build_provider

logger = structlog.get_logger(__name__)


class GrokAction(Enum):
    """Actions the agent can take to manage API calls"""

    TRY_CURRENT_CHANNEL = 0
    SWITCH_TO_BACKUP = 1
    WAIT_100MS = 2
    WAIT_500MS = 3
    WAIT_2000MS = 4
    REDUCE_PROMPT_SIZE = 5
    USE_CACHED_RESPONSE = 6
    FALLBACK_LEGACY_API = 7
    BATCH_WITH_NEXT = 8
    CANCEL_AND_RETRY_LATER = 9

    @property
    def description(self):
        return {
            self.TRY_CURRENT_CHANNEL: "Try current channel",
            self.SWITCH_TO_BACKUP: "Switch to backup channel",
            self.WAIT_100MS: "Wait 100ms then retry",
            self.WAIT_500MS: "Wait 500ms then retry",
            self.WAIT_2000MS: "Wait 2s then retry",
            self.REDUCE_PROMPT_SIZE: "Reduce prompt size",
            self.USE_CACHED_RESPONSE: "Use cached response",
            self.FALLBACK_LEGACY_API: "Use legacy API",
            self.BATCH_WITH_NEXT: "Batch with next request",
            self.CANCEL_AND_RETRY_LATER: "Cancel and retry later",
        }[self]

class ChannelTracker:
    """Tracks performance of different API channels (where applicable)."""

    def __init__(self):
        self.channels: Dict[str, Dict] = {}

    def record_success(self, channel: str, latency_ms: float):
        if channel not in self.channels:
            self.channels[channel] = {
                "successes": 0,
                "failures": 0,
                "total_latency": 0,
                "last_load": 0,
                "last_call": time.time(),
                "recent_errors": [],
                "concurrent_estimate": 1,
            }

        chan = self.channels[channel]
        chan["successes"] += 1
        chan["total_latency"] += latency_ms
        chan["last_call"] = time.time()
        chan["recent_errors"] = [
            e for e in chan["recent_errors"] if time.time() - e["time"] < 300
        ]

    def record_overload(self, channel: str, error_msg: str):
        if channel not in self.channels:
            self.channels[channel] = {
                "successes": 0,
                "failures": 0,
                "total_latency": 0,
                "last_load": 0,
                "last_call": time.time(),
                "recent_errors": [],
                "concurrent_estimate": 1,
            }

        chan = self.channels[channel]
        chan["failures"] += 1

        load = self._extract_load_from_error(error_msg)
        if load:
            chan["last_load"] = load

        requests = self._extract_requests_from_error(error_msg)
        if requests:
            chan["concurrent_estimate"] = requests

        chan["recent_errors"].append(
            {"time": time.time(), "error": error_msg, "load": load, "requests": requests}
        )
        chan["recent_errors"] = chan["recent_errors"][-10:]
        chan["last_call"] = time.time()

    def record_error(self, channel: str, error_msg: str):
        if channel not in self.channels:
            self.channels[channel] = {
                "successes": 0,
                "failures": 0,
                "total_latency": 0,
                "last_load": 0,
                "last_call": time.time(),
                "recent_errors": [],
                "concurrent_estimate": 1,
            }

        chan = self.channels[channel]
        chan["failures"] += 1
        chan["recent_errors"].append({"time": time.time(), "error": error_msg})
        chan["recent_errors"] = chan["recent_errors"][-10:]
        chan["last_call"] = time.time()

    def get_channel_stats(self, channel: str) -> Dict:
        if channel not in self.channels:
            return {
                "success_rate": 0.5,
                "avg_latency": 1000.0,
                "load_estimate": 0.5,
                "error_rate": 0.0,
                "time_since_last_call": 60.0,
                "is_available": True,
            }

        chan = self.channels[channel]
        total_calls = chan["successes"] + chan["failures"]

        return {
            "success_rate": chan["successes"] / max(total_calls, 1),
            "avg_latency": chan["total_latency"] / max(chan["successes"], 1),
            "load_estimate": (
                min(chan["last_load"] / 500000.0, 1.0)
                if chan["last_load"] > 0
                else 0.5
            ),
            "error_rate": len(
                [e for e in chan["recent_errors"] if time.time() - e["time"] < 300]
            )
            / 10.0,
            "time_since_last_call": time.time() - chan["last_call"],
            "is_available": len(
                [e for e in chan["recent_errors"] if time.time() - e["time"] < 60]
            )
            < 3,
            "concurrent_estimate": chan["concurrent_estimate"],
        }

    def get_best_channel(self, exclude: List[str] = None) -> Optional[str]:
        if exclude is None:
            exclude = []

        available = []
        for channel, stats in self.channels.items():
            if channel in exclude:
                continue

            chan_stats = self.get_channel_stats(channel)
            if chan_stats["is_available"]:
                score = chan_stats["success_rate"] * 0.7 + (
                    1.0 - min(chan_stats["avg_latency"] / 5000.0, 1.0)
                ) * 0.3
                available.append((score, channel))

        if not available:
            return None

        available.sort(reverse=True)
        return available[0][1]

    def _extract_load_from_error(self, error_msg: str) -> Optional[int]:
        match = re.search(r"load=(\d+)", error_msg)
        return int(match.group(1)) if match else None

    def _extract_requests_from_error(self, error_msg: str) -> Optional[int]:
        match = re.search(r"num_requests=(\d+)", error_msg)
        return int(match.group(1)) if match else None

class GrokAPIEnvironment:
    """API environment that learns to avoid overloads for multiple providers."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        provider: Optional[LLMProvider] = None,
        provider_name: str = "grok",
        model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url or "https://api.x.ai/v1"
        self.cache_dir = cache_dir or Path("~/.grok_ppo_enterprise/cache").expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.provider = provider or build_provider(
            provider_name, api_key=api_key, model=model, base_url=base_url
        )
        self.provider_name = provider_name
        self.model = model

        self.channel_tracker = ChannelTracker()
        self.current_channel = "default"
        self.known_channels = ["default", "backup-1", "backup-2", "backup-3"]

        self.retry_count = 0
        self.request_start_time = None
        self.consecutive_errors = 0

        self.response_cache: Dict[str, Tuple[float, str]] = {}
        self.cache_ttl = 300

        self.state_dim = 10
        self.action_dim = len(GrokAction)
        self.peak_hours = {17, 18, 19, 20}

    def get_state(self, prompt: Optional[str] = None) -> List[float]:
        state = []
        now = time.time()
        current_hour = datetime.fromtimestamp(now).hour
        
        stats = self.channel_tracker.get_channel_stats(self.current_channel)
        state.append(stats['load_estimate'])
        state.append(min(stats['concurrent_estimate'] / 20.0, 1.0))
        state.append(stats['error_rate'])
        
        state.append(current_hour / 24.0)
        state.append(1.0 if current_hour in self.peak_hours else 0.0)
        
        state.append(min(self.retry_count / 5.0, 1.0))
        state.append(min(self.consecutive_errors / 3.0, 1.0))
        
        time_since = stats['time_since_last_call']
        state.append(min(time_since / 10.0, 1.0))
        
        if prompt:
            prompt_complexity = min(len(prompt) / 1000.0, 1.0)
        else:
            prompt_complexity = 0.5
        state.append(prompt_complexity)
        
        alt_channels = [c for c in self.known_channels if c != self.current_channel]
        available_alts = sum(1 for c in alt_channels 
                           if self.channel_tracker.get_channel_stats(c)['is_available'])
        state.append(available_alts / len(alt_channels) if alt_channels else 0.0)
        
        return state
    
    def reset(self) -> List[float]:
        self.retry_count = 0
        self.request_start_time = time.time()
        self.consecutive_errors = 0
        return self.get_state()
    
    def step(
        self, 
        action_idx: int, 
        prompt: str,
        force_channel: Optional[str] = None
    ) -> Tuple[List[float], float, bool, LLMResult]:
        self.retry_count += 1
        action = GrokAction(action_idx)
        
        result = self._execute_action(action, prompt, force_channel)
        
        if result.success:
            self.consecutive_errors = 0
        else:
            self.consecutive_errors += 1
        
        reward = self._calculate_reward(action, result)
        new_state = self.get_state(prompt)
        
        done = (
            result.success or
            self.retry_count >= 5 or
            action == GrokAction.CANCEL_AND_RETRY_LATER or
            (result.is_overloaded and self.retry_count >= 3)
        )
        
        return new_state, reward, done, result

    def _execute_action(
        self, 
        action: GrokAction, 
        prompt: str,
        force_channel: Optional[str] = None
    ) -> LLMResult:
        if action == GrokAction.USE_CACHED_RESPONSE:
            cached = self._get_cached_response(prompt)
            if cached:
                return LLMResult(
                    success=True,
                    response_text=cached,
                    channel_used="cache",
                    latency_ms=1.0,
                )
        
        channel = force_channel or self.current_channel
        
        if action == GrokAction.SWITCH_TO_BACKUP:
            backup = self.channel_tracker.get_best_channel(exclude=[self.current_channel])
            if backup:
                channel = backup
                self.current_channel = channel
        
        elif action in [GrokAction.WAIT_100MS, GrokAction.WAIT_500MS, GrokAction.WAIT_2000MS]:
            wait_times = {
                GrokAction.WAIT_100MS: 0.1,
                GrokAction.WAIT_500MS: 0.5,
                GrokAction.WAIT_2000MS: 2.0,
            }
            time.sleep(wait_times[action])
        
        elif action == GrokAction.REDUCE_PROMPT_SIZE:
            if len(prompt) > 200:
                prompt = prompt[:200] + "... [truncated]"
        
        elif action == GrokAction.FALLBACK_LEGACY_API:
            return self._call_legacy_api(prompt, channel)
        
        elif action == GrokAction.BATCH_WITH_NEXT:
            time.sleep(0.5)
        
        elif action == GrokAction.CANCEL_AND_RETRY_LATER:
            return LLMResult(
                success=False,
                error_message="Cancelled for later retry",
                channel_used=channel,
            )
        
        return self._call_grok_api(prompt, channel, action == GrokAction.REDUCE_PROMPT_SIZE)
    
    def _call_grok_api(
        self, prompt: str, channel: str, was_reduced: bool = False
    ) -> LLMResult:
        result = self.provider.call(prompt, channel=channel, was_reduced=was_reduced)
        if result.success:
            if result.response_text:
                self._cache_response(prompt, result.response_text)
            self.channel_tracker.record_success(
                channel, latency_ms=result.latency_ms or 0.0
            )
        else:
            if result.is_overloaded:
                self.channel_tracker.record_overload(
                    channel, result.error_message or "overloaded"
                )
            else:
                self.channel_tracker.record_error(channel, result.error_message or "")
        return result
    
    def _call_legacy_api(self, prompt: str, channel: str) -> LLMResult:
        time.sleep(1.5)
        
        if random.random() < 0.8:
            return LLMResult(
                success=True,
                response_text=f"[Legacy API] Response to: {prompt[:50]}...",
                channel_used=f"legacy-{channel}",
                latency_ms=1500.0,
                provider=self.provider_name,
                model=self.model,
            )
        else:
            return LLMResult(
                success=False,
                error_message="Legacy API also busy",
                channel_used=f"legacy-{channel}",
                latency_ms=1500.0,
                provider=self.provider_name,
                model=self.model,
            )
    
    def _calculate_reward(self, action: GrokAction, result: LLMResult) -> float:
        reward = 0.0
        channel_used = result.channel_used or self.current_channel or "default"
        error_message = result.error_message or ""
        
        if result.success:
            reward += 2.0
            
            if result.latency_ms < 1000:
                reward += 1.0
            elif result.latency_ms > 5000:
                reward -= 0.5
            
            if "backup" in channel_used or "legacy" in channel_used:
                reward += 0.3
            
            if channel_used == "cache":
                reward += 1.5
            
        else:
            reward -= 1.0
            
            if result.is_overloaded:
                reward -= 3.0
                
                stats = self.channel_tracker.get_channel_stats(channel_used)
                if stats['load_estimate'] > 0.7:
                    reward -= 2.0
            
            if "timeout" in error_message.lower():
                reward -= 1.5
        
        if action == GrokAction.WAIT_100MS and not result.success:
            reward += 0.1
        
        if action == GrokAction.SWITCH_TO_BACKUP and result.success:
            reward += 0.5
        
        if action == GrokAction.TRY_CURRENT_CHANNEL and result.is_overloaded:
            reward -= 0.5
        
        if action == GrokAction.REDUCE_PROMPT_SIZE:
            reward -= 0.2
        
        if action == GrokAction.CANCEL_AND_RETRY_LATER:
            reward -= 0.5
        
        if self.retry_count > 3:
            reward -= 0.1 * (self.retry_count - 3)
        
        return reward
    
    def _get_cached_response(self, prompt: str) -> Optional[str]:
        prompt_hash = str(hash(prompt))
        
        if prompt_hash in self.response_cache:
            timestamp, response = self.response_cache[prompt_hash]
            if time.time() - timestamp < self.cache_ttl:
                return response
        
        return None
    
    def _cache_response(self, prompt: str, response: str):
        prompt_hash = str(hash(prompt))
        self.response_cache[prompt_hash] = (time.time(), response)
        
        cache_file = self.cache_dir / f"{prompt_hash}.json"
        try:
            cache_file.write_text(json.dumps({
                "prompt": prompt[:100],
                "response": response,
                "timestamp": time.time(),
                "channel": self.current_channel,
            }))
        except:
            pass
    
    def _extract_load_from_error(self, error_msg: str) -> Optional[int]:
        match = re.search(r'load=(\d+)', error_msg)
        return int(match.group(1)) if match else None
    
    def _extract_requests_from_error(self, error_msg: str) -> Optional[int]:
        match = re.search(r'num_requests=(\d+)', error_msg)
        return int(match.group(1)) if match else None
    
    def get_action_meanings(self) -> List[str]:
        return [action.description for action in GrokAction]
    
    def get_channel_report(self) -> Dict:
        report = {}
        for channel in self.known_channels:
            stats = self.channel_tracker.get_channel_stats(channel)
            report[channel] = {
                'success_rate': f"{stats['success_rate']:.1%}",
                'avg_latency_ms': f"{stats['avg_latency']:.0f}",
                'load_estimate': f"{stats['load_estimate']:.1%}",
                'last_call_sec': f"{stats['time_since_last_call']:.1f}",
                'is_available': stats['is_available'],
            }
        return report
    
    def save_state(self, path: Path):
        state = {
            'channel_tracker': self.channel_tracker.channels,
            'current_channel': self.current_channel,
            'known_channels': self.known_channels,
            'timestamp': time.time(),
        }
        path.write_text(json.dumps(state, indent=2))
    
    def load_state(self, path: Path):
        if path.exists():
            state = json.loads(path.read_text())
            self.channel_tracker.channels = state['channel_tracker']
            self.current_channel = state['current_channel']
            self.known_channels = state['known_channels']


# Backwards compatibility alias
GrokAPIResult = LLMResult

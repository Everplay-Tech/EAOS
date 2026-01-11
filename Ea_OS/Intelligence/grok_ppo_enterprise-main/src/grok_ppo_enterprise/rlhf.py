"""
FILE: src/grok_ppo_enterprise/rlhf.py
================================================================================
RLHF Infrastructure for YGI Command Center
"""
from pathlib import Path
import json
from typing import List, Dict, Optional
import uuid
import time
import structlog

logger = structlog.get_logger(__name__)

class RLHFCollector:
    """
    YGI Command Interface: Record trajectories and label preferences.
    This is how YGI teaches the agent what "good API behavior" truly means.
    """
    def __init__(self, storage_path: Path = Path("~/.grok_ppo_enterprise/trajectories")):
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.preferences_path = Path("~/.grok_ppo_enterprise/dpo_preferences.json").expanduser()
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory buffer for recent trajectories
        self.buffer: List[Dict] = []
        self.buffer_max_size = 100

    def record_trajectory(self, trajectory: Dict) -> str:
        """
        Record a complete interaction trajectory.
        
        Args:
            trajectory: Dict containing states, actions, results, etc.
            
        Returns:
            traj_id: Unique identifier for the trajectory
        """
        traj_id = str(uuid.uuid4())
        
        # Add metadata
        trajectory_with_meta = {
            **trajectory,
            "id": traj_id,
            "timestamp": time.time(),
            "version": "1.0"
        }
        
        # Save to file
        path = self.storage_path / f"{traj_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(trajectory_with_meta, f, indent=2)
            
            # Add to in-memory buffer
            self.buffer.append({**trajectory_with_meta, "path": str(path)})
            if len(self.buffer) > self.buffer_max_size:
                self.buffer.pop(0)
            
            logger.info("Trajectory recorded", 
                       traj_id=traj_id, 
                       path=str(path),
                       steps=len(trajectory.get("actions", [])))
            
            return traj_id
            
        except Exception as e:
            logger.error("Failed to record trajectory", traj_id=traj_id, error=str(e))
            raise

    def label_preference(self, traj_id_a: str, traj_id_b: str, winner: str = "a", note: str = "") -> bool:
        """
        Label a preference between two trajectories.
        
        Args:
            traj_id_a: ID of first trajectory
            traj_id_b: ID of second trajectory
            winner: "a" if trajectory A is better, "b" if trajectory B is better
            note: Optional note from YGI
            
        Returns:
            bool: True if preference was successfully recorded
        """
        try:
            # Load both trajectories
            traj_a = self._load_traj(traj_id_a)
            traj_b = self._load_traj(traj_id_b)
            
            if not traj_a or not traj_b:
                logger.error("Failed to load trajectories for preference", 
                           traj_id_a=traj_id_a, 
                           traj_id_b=traj_id_b)
                return False
            
            # Create preference object
            if winner.lower() == "a":
                chosen, rejected = traj_a, traj_b
            else:
                chosen, rejected = traj_b, traj_a
            
            preference = {
                "chosen": {
                    "id": chosen.get("id"),
                    "states": chosen.get("states", []),
                    "actions": chosen.get("actions", []),
                    "results": chosen.get("results", []),
                    "rewards": chosen.get("rewards", []),
                    "success": chosen.get("success", False),
                },
                "rejected": {
                    "id": rejected.get("id"),
                    "states": rejected.get("states", []),
                    "actions": rejected.get("actions", []),
                    "results": rejected.get("results", []),
                    "rewards": rejected.get("rewards", []),
                    "success": rejected.get("success", False),
                },
                "timestamp": time.time(),
                "winner": winner.lower(),
                "ygi_note": note or "YGI direct preference",
                "version": "1.0"
            }
            
            # Load existing preferences
            existing_prefs = []
            if self.preferences_path.exists():
                try:
                    with open(self.preferences_path, "r") as f:
                        existing_prefs = json.load(f)
                except:
                    existing_prefs = []
            
            # Add new preference
            existing_prefs.append(preference)
            
            # Save back
            with open(self.preferences_path, "w") as f:
                json.dump(existing_prefs, f, indent=2)
            
            logger.info("Preference labeled", 
                       winner=winner,
                       chosen_id=preference["chosen"]["id"],
                       rejected_id=preference["rejected"]["id"],
                       note=note)
            
            return True
            
        except Exception as e:
            logger.error("Failed to label preference", 
                       traj_id_a=traj_id_a, 
                       traj_id_b=traj_id_b, 
                       error=str(e))
            return False

    def _load_traj(self, traj_id: str) -> Optional[Dict]:
        """Load trajectory from disk."""
        try:
            path = self.storage_path / f"{traj_id}.json"
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            # Try to find in buffer
            for traj in self.buffer:
                if traj.get("id") == traj_id:
                    return traj
            return None
        except Exception as e:
            logger.error("Failed to load trajectory", traj_id=traj_id, error=str(e))
            return None

    def get_recent_trajectories(self, limit: int = 10) -> List[Dict]:
        """Get most recent trajectories."""
        return self.buffer[-limit:] if self.buffer else []

    def get_preference_stats(self) -> Dict:
        """Get statistics about collected preferences."""
        if not self.preferences_path.exists():
            return {"total": 0, "recent": 0}
        
        try:
            with open(self.preferences_path, "r") as f:
                prefs = json.load(f)
            
            total = len(prefs)
            recent = len([p for p in prefs if time.time() - p.get("timestamp", 0) < 86400])
            
            return {
                "total": total,
                "recent": recent,
                "last_added": max([p.get("timestamp", 0) for p in prefs]) if prefs else 0
            }
        except:
            return {"total": 0, "recent": 0}

    def visualize_trajectory(self, traj_id: str) -> str:
        """
        Create a human-readable visualization of a trajectory.
        
        Args:
            traj_id: ID of trajectory to visualize
            
        Returns:
            str: Human-readable visualization
        """
        traj = self._load_traj(traj_id)
        if not traj:
            return f"Trajectory {traj_id} not found"
        
        output = []
        output.append(f"=== Trajectory: {traj_id} ===")
        output.append(f"Timestamp: {time.ctime(traj.get('timestamp', 0))}")
        output.append(f"Success: {traj.get('success', False)}")
        output.append(f"Attempts: {traj.get('attempts', 0)}")
        output.append(f"Final Channel: {traj.get('final_channel', 'unknown')}")
        output.append("")
        
        # Show steps
        states = traj.get("states", [])
        actions = traj.get("actions", [])
        results = traj.get("results", [])
        
        if states and actions and results:
            output.append("Steps:")
            for i, (state, action, result) in enumerate(zip(states, actions, results)):
                output.append(f"  Step {i}:")
                output.append(f"    State: {self._format_state(state)}")
                output.append(f"    Action: {self._get_action_name(action)}")
                
                if isinstance(result, dict):
                    if result.get("success"):
                        output.append(f"    ✅ Success on channel: {result.get('channel', 'unknown')}")
                        output.append(f"    Latency: {result.get('latency_ms', 0):.0f}ms")
                    else:
                        if result.get("overloaded"):
                            output.append(f"    ❌ OVERLOADED: {result.get('channel', 'unknown')}")
                        else:
                            err = result.get("error", "Unknown error")
                            output.append(f"    ❌ Error: {err[:80]}...")
                output.append("")
        
        # Show total reward if available
        rewards = traj.get("rewards", [])
        if rewards:
            output.append(f"Total Reward: {sum(rewards):.2f}")
        
        return "\n".join(output)
    
    def _format_state(self, state: List[float]) -> str:
        """Format state vector for display."""
        if len(state) >= 10:
            return (f"Load:{state[0]:.1%} Err:{state[2]:.1%} "
                   f"Retry:{state[5]*5:.0f}/5 Alt:{state[9]:.0%}")
        return f"State dim: {len(state)}"
    
    def _get_action_name(self, action_idx: int) -> str:
        """Get human-readable action name."""
        action_names = [
            "Try current channel",
            "Switch to backup", 
            "Wait 100ms",
            "Wait 500ms",
            "Wait 2s",
            "Reduce prompt size",
            "Use cached response",
            "Use legacy API",
            "Batch with next",
            "Cancel and retry later"
        ]
        return action_names[action_idx] if 0 <= action_idx < len(action_names) else f"Action {action_idx}"

# Global RLHF collector — activated on import
rlhf_collector = RLHFCollector()

"""
FILE: src/grok_ppo_enterprise/dpo.py
================================================================================
Direct Preference Optimization for API Call Optimization
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from typing import List, Dict, Tuple, Optional
import json
from pathlib import Path
import structlog
import time

logger = structlog.get_logger(__name__)

class DPOTrainer:
    """
    Direct Preference Optimization for API Call Optimization
    Replaces hand-crafted reward with learned human/YGI preference signal.
    """
    def __init__(
        self,
        policy_model: nn.Module,
        reference_model: nn.Module,
        beta: float = 0.1,
        lr: float = 1e-5,
        device: str = "cpu"
    ):
        self.policy = policy_model.to(device)
        self.reference = reference_model.to(device)
        self.reference.eval()
        for param in self.reference.parameters():
            param.requires_grad = False

        self.beta = beta
        self.optimizer = Adam(self.policy.parameters(), lr=lr)
        self.device = device
        self.training_history = []

    def _load_preferences(self, path: Path) -> List[Dict]:
        """Load YGI-labeled preference pairs: (traj_chosen, traj_rejected)"""
        if not path.exists():
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load preferences", path=str(path), error=str(e))
            return []

    def _save_preferences(self, preferences: List[Dict], path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(preferences, f, indent=2)

    def dpo_loss(
        self,
        policy_chosen_logprobs: torch.Tensor,
        policy_rejected_logprobs: torch.Tensor,
        ref_chosen_logprobs: torch.Tensor,
        ref_rejected_logprobs: torch.Tensor
    ) -> torch.Tensor:
        """
        DPO Loss from: Direct Preference Optimization: Your Language Model is Secretly a Reward Model
        https://arxiv.org/abs/2305.18290
        """
        policy_logratio = policy_chosen_logprobs - policy_rejected_logprobs
        ref_logratio = ref_chosen_logprobs - ref_rejected_logprobs

        losses = -F.logsigmoid(self.beta * (policy_logratio - ref_logratio))
        return losses.mean()

    def train_step(self, preferences_path: Optional[Path] = None) -> Dict:
        """
        Perform one DPO training step.
        
        Args:
            preferences_path: Path to preferences JSON file
            
        Returns:
            Dict with loss, accuracy, and pair count
        """
        if preferences_path is None:
            preferences_path = Path("~/.grok_ppo_enterprise/dpo_preferences.json").expanduser()
        
        prefs = self._load_preferences(preferences_path)
        if len(prefs) == 0:
            logger.warning("No preferences found for DPO training", path=str(preferences_path))
            return {"dpo_loss": 0.0, "accuracy": 0.0, "n_pairs": 0}

        # Use all available pairs (can be batched if needed)
        batch_size = min(32, len(prefs))
        batch = prefs[:batch_size]

        policy_chosen_logprobs = []
        policy_rejected_logprobs = []
        ref_chosen_logprobs = []
        ref_rejected_logprobs = []
        
        correct = 0
        total = len(batch)

        # Process each preference pair
        for pair in batch:
            try:
                # Extract trajectories
                chosen = pair.get("chosen", {})
                rejected = pair.get("rejected", {})
                
                if not chosen or not rejected:
                    continue
                
                # Get states and actions
                chosen_states = chosen.get("states", [])
                chosen_actions = chosen.get("actions", [])
                rejected_states = rejected.get("states", [])
                rejected_actions = rejected.get("actions", [])
                
                if not chosen_states or not chosen_actions or not rejected_states or not rejected_actions:
                    continue
                
                # Convert to tensors - handle variable length by using last state
                # In production, you'd want proper sequence handling
                chosen_state_tensor = torch.tensor(chosen_states[-1], dtype=torch.float32, device=self.device).unsqueeze(0)
                rejected_state_tensor = torch.tensor(rejected_states[-1], dtype=torch.float32, device=self.device).unsqueeze(0)
                
                chosen_action_tensor = torch.tensor([chosen_actions[-1]], dtype=torch.long, device=self.device)
                rejected_action_tensor = torch.tensor([rejected_actions[-1]], dtype=torch.long, device=self.device)
                
                # Reference model forward (frozen)
                with torch.no_grad():
                    ref_chosen_logits, _ = self.reference(chosen_state_tensor)
                    ref_rejected_logits, _ = self.reference(rejected_state_tensor)
                    
                    ref_chosen_logprobs_tensor = F.log_softmax(ref_chosen_logits, dim=-1)
                    ref_rejected_logprobs_tensor = F.log_softmax(ref_rejected_logits, dim=-1)
                    
                    ref_chosen_logprob = ref_chosen_logprobs_tensor.gather(1, chosen_action_tensor.unsqueeze(1)).squeeze(1)
                    ref_rejected_logprob = ref_rejected_logprobs_tensor.gather(1, rejected_action_tensor.unsqueeze(1)).squeeze(1)
                    
                    ref_chosen_logprobs.append(ref_chosen_logprob)
                    ref_rejected_logprobs.append(ref_rejected_logprob)
                
                # Policy model forward (trainable)
                policy_chosen_logits, _ = self.policy(chosen_state_tensor)
                policy_rejected_logits, _ = self.policy(rejected_state_tensor)
                
                policy_chosen_logprobs_tensor = F.log_softmax(policy_chosen_logits, dim=-1)
                policy_rejected_logprobs_tensor = F.log_softmax(policy_rejected_logits, dim=-1)
                
                policy_chosen_logprob = policy_chosen_logprobs_tensor.gather(1, chosen_action_tensor.unsqueeze(1)).squeeze(1)
                policy_rejected_logprob = policy_rejected_logprobs_tensor.gather(1, rejected_action_tensor.unsqueeze(1)).squeeze(1)
                
                policy_chosen_logprobs.append(policy_chosen_logprob)
                policy_rejected_logprobs.append(policy_rejected_logprob)
                
                # Track accuracy
                if policy_chosen_logprob.item() > policy_rejected_logprob.item():
                    correct += 1
                    
            except Exception as e:
                logger.error("Error processing preference pair", error=str(e))
                total -= 1
        
        if total == 0:
            return {"dpo_loss": 0.0, "accuracy": 0.0, "n_pairs": 0}
        
        # Stack all tensors
        policy_chosen = torch.cat(policy_chosen_logprobs)
        policy_rejected = torch.cat(policy_rejected_logprobs)
        ref_chosen = torch.cat(ref_chosen_logprobs)
        ref_rejected = torch.cat(ref_rejected_logprobs)
        
        # Compute loss
        loss = self.dpo_loss(policy_chosen, policy_rejected, ref_chosen, ref_rejected)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), 1.0)
        self.optimizer.step()
        
        # Calculate accuracy
        accuracy = correct / total
        
        # Record in history
        self.training_history.append({
            "timestamp": time.time(),
            "loss": loss.item(),
            "accuracy": accuracy,
            "n_pairs": total
        })
        
        logger.info("DPO training step completed", 
                   loss=loss.item(), 
                   accuracy=accuracy, 
                   pairs=total)
        
        return {"dpo_loss": loss.item(), "accuracy": accuracy, "n_pairs": total}

    def save_reference_snapshot(self, path: Path):
        """Save current policy as new reference snapshot."""
        torch.save(self.policy.state_dict(), path)
        logger.info("DPO reference model snapshot saved", path=str(path))
    
    def save_checkpoint(self, path: Path):
        """Save complete trainer state."""
        checkpoint = {
            'policy_state_dict': self.policy.state_dict(),
            'reference_state_dict': self.reference.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_history': self.training_history,
            'beta': self.beta,
        }
        torch.save(checkpoint, path)
        logger.info("DPO checkpoint saved", path=str(path))
    
    def load_checkpoint(self, path: Path):
        """Load trainer state from checkpoint."""
        checkpoint = torch.load(path, map_location=self.device)
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.reference.load_state_dict(checkpoint['reference_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.training_history = checkpoint['training_history']
        self.beta = checkpoint.get('beta', self.beta)
        logger.info("DPO checkpoint loaded", path=str(path))

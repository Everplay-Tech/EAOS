"""
FILE: src/grok_ppo_enterprise/agent.py
================================================================================
PPO Actor-Critic Agent for Grok API Optimization
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple

class PPOActorCritic(nn.Module):
    """
    Actor-Critic network for PPO.
    Actor: Policy network that selects actions
    Critic: Value network that estimates state value
    """
    
    def __init__(self, state_dim: int = 10, action_dim: int = 10, hidden_dim: int = 256):
        super().__init__()
        
        # Shared feature extractor
        self.shared_net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
        )
        
        # Actor (policy) head
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, action_dim)
        )
        
        # Critic (value) head
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1)
        )
        
        # Initialize weights
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=0.01)
            nn.init.constant_(module.bias, 0.0)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            x: State tensor of shape [batch_size, state_dim]
            
        Returns:
            logits: Action logits [batch_size, action_dim]
            value: State value estimate [batch_size, 1]
        """
        features = self.shared_net(x)
        logits = self.actor(features)
        value = self.critic(features)
        return logits, value
    
    def get_action(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample an action from the policy.
        
        Args:
            state: State tensor of shape [batch_size, state_dim]
            
        Returns:
            action: Sampled action indices [batch_size]
            log_prob: Log probability of chosen actions [batch_size]
            value: State value estimate [batch_size, 1]
        """
        logits, value = self.forward(state)
        probs = F.softmax(logits, dim=-1)
        dist = torch.distributions.Categorical(probs)
        action = dist.sample()
        log_prob = dist.log_prob(action)
        return action, log_prob, value
    
    def get_value(self, state: torch.Tensor) -> torch.Tensor:
        """Get value estimate without sampling action."""
        _, value = self.forward(state)
        return value
    
    def evaluate_actions(self, state: torch.Tensor, action: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluate actions for PPO loss computation.
        
        Args:
            state: State tensor [batch_size, state_dim]
            action: Action indices [batch_size]
            
        Returns:
            log_prob: Log probability of actions [batch_size]
            entropy: Entropy of policy distribution [batch_size]
            value: State value estimate [batch_size, 1]
        """
        logits, value = self.forward(state)
        probs = F.softmax(logits, dim=-1)
        dist = torch.distributions.Categorical(probs)
        
        log_prob = dist.log_prob(action)
        entropy = dist.entropy()
        
        return log_prob, entropy, value

class ReplayBuffer:
    """
    Buffer for storing and sampling trajectories.
    """
    
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self.buffer = []
        self.position = 0
    
    def push(self, state, action, reward, next_state, done, log_prob, value):
        """Store a transition."""
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        self.buffer[self.position] = (
            state, action, reward, next_state, done, log_prob, value
        )
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size: int):
        """Sample a batch of transitions."""
        indices = torch.randint(0, len(self.buffer), (batch_size,))
        batch = [self.buffer[i] for i in indices]
        
        states, actions, rewards, next_states, dones, log_probs, values = zip(*batch)
        
        return (
            torch.stack(states),
            torch.stack(actions),
            torch.tensor(rewards, dtype=torch.float32),
            torch.stack(next_states),
            torch.tensor(dones, dtype=torch.float32),
            torch.stack(log_probs),
            torch.stack(values),
        )
    
    def __len__(self):
        return len(self.buffer)

#!/usr/bin/env python3
"""
FILE: src/grok_ppo_enterprise/cli.py
================================================================================
Main CLI Interface for Grok PPO Enterprise
"""
import os
import sys
import argparse
import json
from pathlib import Path
from typing import Optional
import structlog

# Setup logging
logger = structlog.get_logger(__name__)

# Import our modules
from .cli_integration import SmartLLMCaller, create_smart_caller
from .rlhf import rlhf_collector
from .dpo import DPOTrainer
from .agent import PPOActorCritic
from .telemetry import meter

def setup_parser() -> argparse.ArgumentParser:
    """Setup command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Grok PPO Enterprise - Smart API Caller with RLHF",
        prog="grok-ppo"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Call command
    call_parser = subparsers.add_parser(
        "call", help="Make a smart API call to an LLM provider"
    )
    call_parser.add_argument(
        "prompt", help="Prompt to send to the provider"
    )
    call_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed agent reasoning"
    )
    call_parser.add_argument(
        "--max-attempts",
        "-m",
        type=int,
        default=5,
        help="Maximum retry attempts",
    )
    call_parser.add_argument(
        "--api-key",
        "-k",
        help="API key for the selected provider (env fallback)",
    )
    call_parser.add_argument(
        "--provider",
        "-p",
        default="grok",
        choices=["grok", "openai", "google", "anthropic", "deepseek"],
        help="LLM provider to use (default: grok)",
    )
    call_parser.add_argument(
        "--model",
        help="Model identifier for the provider (optional)",
    )
    call_parser.add_argument(
        "--base-url",
        help="Override base URL for the provider (advanced)",
    )
    
    # Train command
    train_parser = subparsers.add_parser("train-dpo", help="Train DPO model on collected preferences")
    train_parser.add_argument("--epochs", "-e", type=int, default=1, help="Number of training epochs")
    train_parser.add_argument("--save-path", "-s", help="Path to save trained model")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status and metrics")
    status_parser.add_argument("--metrics", "-m", action="store_true", help="Show detailed metrics")
    
    # RLHF commands
    rlhf_parser = subparsers.add_parser("rlhf", help="RLHF trajectory management")
    rlhf_subparsers = rlhf_parser.add_subparsers(dest="rlhf_command", help="RLHF subcommand")
    
    # RLHF list
    list_parser = rlhf_subparsers.add_parser("list", help="List recent trajectories")
    list_parser.add_argument("--limit", "-l", type=int, default=10, help="Number of trajectories to show")
    
    # RLHF visualize
    viz_parser = rlhf_subparsers.add_parser("visualize", help="Visualize a trajectory")
    viz_parser.add_argument("traj_id", help="Trajectory ID to visualize")
    
    # RLHF label
    label_parser = rlhf_subparsers.add_parser("label", help="Label a preference between two trajectories")
    label_parser.add_argument("traj_a", help="ID of first trajectory")
    label_parser.add_argument("traj_b", help="ID of second trajectory")
    label_parser.add_argument("--winner", "-w", choices=["a", "b"], default="a", help="Which trajectory is better")
    label_parser.add_argument("--note", "-n", help="Optional note about the preference")
    
    # RLHF stats
    rlhf_subparsers.add_parser("stats", help="Show RLHF statistics")
    
    # Configure command
    config_parser = subparsers.add_parser("configure", help="Configure system settings")
    config_parser.add_argument("--api-key", "-k", help="Set Grok API key")
    config_parser.add_argument("--show", "-s", action="store_true", help="Show current configuration")
    
    return parser

def call_command(args) -> int:
    """Handle call command."""
    try:
        caller = create_smart_caller(
            api_key=args.api_key,
            provider_name=args.provider,
            model=args.model,
            base_url=args.base_url,
        )
        
        print(f"🤖 Calling {args.provider} with: {args.prompt[:100]}...")
        
        response = caller.call_with_learning(
            prompt=args.prompt,
            verbose=args.verbose,
            max_attempts=args.max_attempts
        )
        
        print(f"\n📝 Response:")
        print(f"{response}")
        
        if args.verbose:
            print(f"\n{caller.get_channel_report()}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

def train_dpo_command(args) -> int:
    """Handle train-dpo command."""
    try:
        print("🧠 Training DPO model on collected preferences...")
        
        # Initialize models
        policy = PPOActorCritic(state_dim=10, action_dim=10)
        reference = PPOActorCritic(state_dim=10, action_dim=10)
        
        # Load existing models if available
        model_dir = Path("~/.grok_ppo_enterprise/models").expanduser()
        model_dir.mkdir(exist_ok=True)
        
        policy_path = model_dir / "policy.pt"
        if policy_path.exists():
            import torch
            policy.load_state_dict(torch.load(policy_path))
            print(f"✓ Loaded policy from {policy_path}")
        
        reference_path = model_dir / "reference.pt"
        if reference_path.exists():
            import torch
            reference.load_state_dict(torch.load(reference_path))
            print(f"✓ Loaded reference from {reference_path}")
        
        # Initialize trainer
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        trainer = DPOTrainer(policy, reference, device=device)
        
        # Train for specified epochs
        total_loss = 0.0
        total_accuracy = 0.0
        total_pairs = 0
        
        for epoch in range(args.epochs):
            print(f"\nEpoch {epoch + 1}/{args.epochs}:")
            results = trainer.train_step()
            
            if results["n_pairs"] > 0:
                total_loss += results["dpo_loss"]
                total_accuracy += results["accuracy"]
                total_pairs += results["n_pairs"]
                
                print(f"  Loss: {results['dpo_loss']:.4f}")
                print(f"  Accuracy: {results['accuracy']:.2%}")
                print(f"  Pairs used: {results['n_pairs']}")
            else:
                print("  No preferences found for training")
                break
        
        # Save results
        if total_pairs > 0:
            # Save updated policy
            torch.save(policy.state_dict(), policy_path)
            print(f"\n✓ Updated policy saved to {policy_path}")
            
            # Also save as smart caller
            smart_caller_path = model_dir / "smart_caller.pt"
            torch.save(policy.state_dict(), smart_caller_path)
            print(f"✓ Smart caller saved to {smart_caller_path}")
            
            # Save reference snapshot
            trainer.save_reference_snapshot(reference_path)
            
            # Print summary
            print(f"\n🎯 Training Summary:")
            print(f"  Average loss: {total_loss/args.epochs:.4f}")
            print(f"  Average accuracy: {total_accuracy/args.epochs:.2%}")
            print(f"  Total pairs processed: {total_pairs}")
        else:
            print("\n⚠️  No training performed (no preference data)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Training error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

def status_command(args) -> int:
    """Handle status command."""
    try:
        print("📊 Grok PPO Enterprise - System Status")
        print("=" * 50)
        
        # Check API keys per provider
        providers = {
            "grok": ["GROK_API_KEY", "XAI_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "google": ["GOOGLE_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
        }
        print("🔑 API Keys:")
        for provider, env_vars in providers.items():
            api_key = next((os.getenv(env) for env in env_vars if os.getenv(env)), None)
            if api_key:
                print(f"  ✓ {provider}: {'*' * 8}{api_key[-4:]}")
            else:
                print(f"  ✗ {provider}: Not set (env: {', '.join(env_vars)})")
        
        # Check directories
        base_dir = Path("~/.grok_ppo_enterprise").expanduser()
        trajectories_dir = base_dir / "trajectories"
        models_dir = base_dir / "models"
        
        print(f"\n📁 Data Directories:")
        print(f"  Base: {base_dir} {'✓' if base_dir.exists() else '✗'}")
        print(f"  Trajectories: {trajectories_dir} {'✓' if trajectories_dir.exists() else '✗'}")
        print(f"  Models: {models_dir} {'✓' if models_dir.exists() else '✗'}")
        
        # Count trajectories
        if trajectories_dir.exists():
            traj_files = list(trajectories_dir.glob("*.json"))
            print(f"  Trajectories stored: {len(traj_files)}")
        
        # RLHF stats
        print(f"\n🎯 RLHF Status:")
        stats = rlhf_collector.get_preference_stats()
        print(f"  Total preferences: {stats.get('total', 0)}")
        print(f"  Recent (24h): {stats.get('recent', 0)}")
        
        # Model status
        print(f"\n🤖 Model Status:")
        smart_caller_path = models_dir / "smart_caller.pt"
        if smart_caller_path.exists():
            print(f"  Smart caller: ✓ ({smart_caller_path})")
        else:
            print(f"  Smart caller: ✗ (not trained yet)")
        
        # Metrics if requested
        if args.metrics:
            print(f"\n📈 Detailed Metrics:")
            metrics = meter.get_metrics()
            for metric in metrics[-10:]:  # Show last 10 metrics
                print(f"  {metric['name']}: {metric['value']}")
        
        print(f"\n💡 Tips:")
        print(f"  • Use 'grok-ppo call \"your prompt\"' to make smart API calls")
        print(f"  • Use 'grok-ppo train-dpo' to train on collected preferences")
        print(f"  • Use 'grok-ppo rlhf list' to see recent trajectories")
        
        return 0
        
    except Exception as e:
        print(f"❌ Status error: {e}", file=sys.stderr)
        return 1

def rlhf_command(args) -> int:
    """Handle RLHF commands."""
    try:
        if args.rlhf_command == "list":
            trajectories = rlhf_collector.get_recent_trajectories(args.limit)
            
            if not trajectories:
                print("No trajectories found")
                return 0
            
            print(f"📋 Recent Trajectories (last {len(trajectories)}):")
            print("-" * 80)
            
            for traj in trajectories:
                traj_id = traj.get("id", "unknown")
                timestamp = traj.get("timestamp", 0)
                success = traj.get("success", False)
                attempts = traj.get("attempts", 0)
                prompt_preview = str(traj.get("prompt", ""))[:50]
                
                status = "✅" if success else "❌"
                print(f"{status} {traj_id}")
                print(f"  Prompt: {prompt_preview}...")
                print(f"  Attempts: {attempts}, Success: {success}")
                print(f"  Time: {timestamp}")
                print()
            
            return 0
            
        elif args.rlhf_command == "visualize":
            visualization = rlhf_collector.visualize_trajectory(args.traj_id)
            print(visualization)
            return 0
            
        elif args.rlhf_command == "label":
            success = rlhf_collector.label_preference(
                args.traj_a, 
                args.traj_b, 
                args.winner, 
                args.note
            )
            
            if success:
                print(f"✓ Preference labeled: Trajectory {args.traj_a if args.winner == 'a' else args.traj_b} is better")
                if args.note:
                    print(f"  Note: {args.note}")
            else:
                print(f"✗ Failed to label preference")
                return 1
            
            return 0
            
        elif args.rlhf_command == "stats":
            stats = rlhf_collector.get_preference_stats()
            
            print("📊 RLHF Statistics:")
            print(f"  Total preferences: {stats.get('total', 0)}")
            print(f"  Recent (24h): {stats.get('recent', 0)}")
            
            if stats.get('last_added', 0) > 0:
                import time
                last_time = time.ctime(stats['last_added'])
                print(f"  Last added: {last_time}")
            
            # Also show trajectory count
            traj_dir = Path("~/.grok_ppo_enterprise/trajectories").expanduser()
            if traj_dir.exists():
                traj_count = len(list(traj_dir.glob("*.json")))
                print(f"  Total trajectories: {traj_count}")
            
            return 0
            
        else:
            print("Please specify an RLHF subcommand: list, visualize, label, or stats")
            return 1
            
    except Exception as e:
        print(f"❌ RLHF error: {e}", file=sys.stderr)
        return 1

def configure_command(args) -> int:
    """Handle configure command."""
    try:
        config_dir = Path("~/.grok_ppo_enterprise").expanduser()
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        
        # Load existing config
        config = {}
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except:
                config = {}
        
        # Update config
        updated = False
        
        if args.api_key:
            config["api_key"] = args.api_key
            updated = True
            print(f"✓ API key updated")
            
            # Also set environment variable for current session
            os.environ["GROK_API_KEY"] = args.api_key
        
        if args.show or not updated:
            print("📋 Current Configuration:")
            print(f"  Config file: {config_file}")
            
            if config:
                for key, value in config.items():
                    if key == "api_key" and value:
                        print(f"  {key}: {'*' * 8}{value[-4:]}")
                    else:
                        print(f"  {key}: {value}")
            else:
                print("  No configuration set")
        
        # Save config
        if updated:
            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configuration saved to {config_file}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr)
        return 1

def main():
    """Main CLI entry point."""
    parser = setup_parser()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    # Route to appropriate command handler
    if args.command == "call":
        return call_command(args)
    elif args.command == "train-dpo":
        return train_dpo_command(args)
    elif args.command == "status":
        return status_command(args)
    elif args.command == "rlhf":
        return rlhf_command(args)
    elif args.command == "configure":
        return configure_command(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())

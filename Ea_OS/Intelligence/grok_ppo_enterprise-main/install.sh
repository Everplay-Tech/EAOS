#!/bin/bash
# Grok PPO Enterprise Installation Script

set -e  # Exit on error

echo "🚀 Installing Grok PPO Enterprise..."
echo "====================================="

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION detected"

# Check for pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 not found. Please install pip first."
    exit 1
fi

# Install torch first (can be tricky)
echo "📦 Installing PyTorch..."
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
echo "📦 Installing dependencies..."
pip3 install requests structlog typing-extensions rich

# Install the package
echo "📦 Installing grok-ppo-enterprise..."
pip3 install -e .

# Create config directory
CONFIG_DIR="$HOME/.grok_ppo_enterprise"
mkdir -p "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/trajectories"
mkdir -p "$CONFIG_DIR/models"
mkdir -p "$CONFIG_DIR/cache"

echo "✓ Configuration directories created: $CONFIG_DIR"

# Ask for API key
echo ""
echo "🔑 Please enter your Grok API key (or press Enter to skip):"
read -r API_KEY

if [ -n "$API_KEY" ]; then
    echo "GROK_API_KEY=$API_KEY" > "$CONFIG_DIR/config.env"
    export GROK_API_KEY="$API_KEY"
    echo "✓ API key saved to $CONFIG_DIR/config.env"
else
    echo "⚠️  No API key provided. You'll need to set GROK_API_KEY environment variable."
fi

# Create example script
cat > "$CONFIG_DIR/example.sh" << 'EOF'
#!/bin/bash
# Example usage of Grok PPO Enterprise

# Set API key if not already set
if [ -z "$GROK_API_KEY" ] && [ -f ~/.grok_ppo_enterprise/config.env ]; then
    source ~/.grok_ppo_enterprise/config.env
fi

# Test the installation
echo "🧪 Testing Grok PPO Enterprise..."
grok-ppo status

echo ""
echo "💡 Try these commands:"
echo "  grok-ppo call 'Hello, how are you?'"
echo "  grok-ppo call -v 'Explain quantum computing'"
echo "  grok-ppo train-dpo"
echo "  grok-ppo rlhf list"
EOF

chmod +x "$CONFIG_DIR/example.sh"

echo ""
echo "🎉 Installation complete!"
echo ""
echo "📖 Quick start:"
echo "  1. Set your API key: export GROK_API_KEY='your-key'"
echo "  2. Test: grok-ppo status"
echo "  3. Make your first smart call: grok-ppo call 'Hello!'"
echo ""
echo "💡 Run the example script: bash $CONFIG_DIR/example.sh"
echo ""
echo "📚 Full documentation: https://github.com/yourusername/grok-ppo-enterprise"

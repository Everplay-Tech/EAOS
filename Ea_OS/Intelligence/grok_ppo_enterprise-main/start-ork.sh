#!/bin/bash
# Start an Ork design session

echo "🦍 Starting Ork File System Design Session"
echo "=========================================="

# Set API key if needed
if [ -z "$GROK_API_KEY" ]; then
    echo "Enter your Grok API key: "
    read -s api_key
    export GROK_API_KEY="$api_key"
fi

# Create session file
SESSION_FILE="ork-sessions/$(date +%Y-%m-%d-%H-%M).txt"
mkdir -p ork-sessions

echo "Session started at $(date)" > "$SESSION_FILE"
echo "Session log: $SESSION_FILE"

# Interactive loop
while true; do
    echo ""
    echo "💭 Your question (or 'save', 'train', 'quit'): "
    read -r question
    
    case "$question" in
        quit)
            echo "👋 Ending Ork session"
            break
            ;;
        save)
            echo "💾 Session saved to $SESSION_FILE"
            ;;
        train)
            echo "🧠 Training Ork on your preferences..."
            ork train-dpo
            ;;
        *)
            # Ask Ork and log both question and response
            echo "Q: $question" >> "$SESSION_FILE"
            echo "🦍 Thinking..."
            response=$(ork call "$question")
            echo "A: $response" >> "$SESSION_FILE"
            echo "📝 $response"
            ;;
    esac
done

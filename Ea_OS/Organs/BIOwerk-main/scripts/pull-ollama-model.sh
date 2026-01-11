#!/bin/bash

# Ollama Model Puller Script
# Usage: ./scripts/pull-ollama-model.sh [model_name]

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MODEL=${1:-phi3:mini}

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  BIOwerk Ollama Model Puller${NC}"
echo -e "${BLUE}================================================${NC}"
echo

# Check if Ollama container is running
if ! docker ps | grep -q biowerk-ollama; then
    echo -e "${YELLOW}Ollama container not running. Starting services...${NC}"
    docker compose up -d ollama
    echo -e "${GREEN}Waiting for Ollama to be ready...${NC}"
    sleep 10
fi

echo -e "${GREEN}Pulling model: ${MODEL}${NC}"
echo

docker exec -it biowerk-ollama ollama pull $MODEL

echo
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Model ${MODEL} pulled successfully!${NC}"
echo -e "${GREEN}================================================${NC}"
echo
echo -e "To use this model, update your .env file:"
echo -e "${YELLOW}  LLM_PROVIDER=ollama${NC}"
echo -e "${YELLOW}  OLLAMA_MODEL=${MODEL}${NC}"
echo
echo "Available models:"
docker exec -it biowerk-ollama ollama list
echo
echo -e "${BLUE}Recommended models:${NC}"
echo -e "  ${GREEN}phi3:mini${NC}      - Fast, 2.3GB (DEFAULT)"
echo -e "  ${GREEN}llama3.2${NC}       - Fast, 2GB"
echo -e "  ${GREEN}mistral${NC}        - High quality, 4.1GB"
echo -e "  ${GREEN}qwen2.5:7b${NC}     - Structured data, 4.7GB"
echo

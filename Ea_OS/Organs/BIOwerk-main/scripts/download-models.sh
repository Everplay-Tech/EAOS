#!/bin/bash

# Model Download Script for BIOwerk
# Downloads LLM models and installs them into each service's local models directory
# Usage: ./scripts/download-models.sh [model_name] [services...]

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_MODEL="phi3-mini"

# Service groups
WORKER_SERVICES=("osteon" "synapse" "myocyte" "nucleus" "chaperone" "circadian")
STOOGE_SERVICES=("larry" "moe" "harry")  # The 3 Stooges!
ALL_SERVICES=("${WORKER_SERVICES[@]}" "${STOOGE_SERVICES[@]}")

# Model registry - maps friendly names to HuggingFace repo and file
declare -A MODEL_REGISTRY
MODEL_REGISTRY["phi2"]="microsoft/phi-2:phi-2.Q4_K_M.gguf"
MODEL_REGISTRY["phi3-mini"]="microsoft/Phi-3-mini-4k-instruct-gguf:Phi-3-mini-4k-instruct-q4.gguf"
MODEL_REGISTRY["phi3"]="microsoft/Phi-3-mini-4k-instruct-gguf:Phi-3-mini-4k-instruct-q4.gguf"
MODEL_REGISTRY["llama3.2"]="hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF:llama-3.2-3b-instruct-q4_k_m.gguf"
MODEL_REGISTRY["mistral"]="TheBloke/Mistral-7B-Instruct-v0.2-GGUF:mistral-7b-instruct-v0.2.Q4_K_M.gguf"
MODEL_REGISTRY["qwen2.5"]="Qwen/Qwen2.5-7B-Instruct-GGUF:qwen2.5-7b-instruct-q4_k_m.gguf"

# Special shortcuts
MODEL_REGISTRY["stooges"]="phi2"  # Install phi2 to the 3 stooges
MODEL_REGISTRY["workers"]="phi3-mini"  # Install phi3-mini to worker services

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  BIOwerk Model Download & Installation${NC}"
echo -e "${BLUE}================================================${NC}"
echo

# Parse arguments
MODEL_NAME="${1:-$DEFAULT_MODEL}"
shift || true
SERVICES=("$@")

# Handle special shortcuts
if [ "$MODEL_NAME" == "stooges" ]; then
    MODEL_NAME="phi2"
    if [ ${#SERVICES[@]} -eq 0 ]; then
        SERVICES=("${STOOGE_SERVICES[@]}")
    fi
elif [ "$MODEL_NAME" == "workers" ]; then
    MODEL_NAME="phi3-mini"
    if [ ${#SERVICES[@]} -eq 0 ]; then
        SERVICES=("${WORKER_SERVICES[@]}")
    fi
else
    # If no services specified, use all
    if [ ${#SERVICES[@]} -eq 0 ]; then
        SERVICES=("${ALL_SERVICES[@]}")
    fi
fi

# Validate model name
if [ -z "${MODEL_REGISTRY[$MODEL_NAME]}" ]; then
    echo -e "${RED}Error: Unknown model '$MODEL_NAME'${NC}"
    echo -e "${YELLOW}Available models:${NC}"
    for model in "${!MODEL_REGISTRY[@]}"; do
        echo -e "  - ${GREEN}$model${NC}"
    done
    exit 1
fi

# Get model info
MODEL_INFO="${MODEL_REGISTRY[$MODEL_NAME]}"
IFS=':' read -r REPO_ID FILE_NAME <<< "$MODEL_INFO"

echo -e "${GREEN}Model:${NC} $MODEL_NAME"
echo -e "${GREEN}Repository:${NC} $REPO_ID"
echo -e "${GREEN}File:${NC} $FILE_NAME"
echo -e "${GREEN}Services:${NC} ${SERVICES[*]}"
echo

# Check if huggingface-cli is available
if ! command -v huggingface-cli &> /dev/null; then
    echo -e "${YELLOW}huggingface-cli not found. Installing...${NC}"
    pip install -q huggingface_hub
fi

# Create temp directory for download
TEMP_DIR="/tmp/biowerk-models"
mkdir -p "$TEMP_DIR"

echo -e "${BLUE}Downloading model from HuggingFace...${NC}"
echo -e "${YELLOW}This may take several minutes depending on model size${NC}"
echo

# Download model using huggingface-cli
huggingface-cli download "$REPO_ID" "$FILE_NAME" \
    --local-dir "$TEMP_DIR" \
    --local-dir-use-symlinks False

DOWNLOADED_FILE="$TEMP_DIR/$FILE_NAME"

if [ ! -f "$DOWNLOADED_FILE" ]; then
    echo -e "${RED}Error: Model file not found after download${NC}"
    exit 1
fi

# Get file size
FILE_SIZE=$(du -h "$DOWNLOADED_FILE" | cut -f1)
echo
echo -e "${GREEN}Download complete! Size: $FILE_SIZE${NC}"
echo

# Copy to each service
echo -e "${BLUE}Installing model to services...${NC}"
for service in "${SERVICES[@]}"; do
    SERVICE_DIR="services/$service/models"

    if [ ! -d "$SERVICE_DIR" ]; then
        echo -e "${YELLOW}Warning: Service directory not found: $SERVICE_DIR${NC}"
        continue
    fi

    # Create model-specific subdirectory
    MODEL_DIR="$SERVICE_DIR/$MODEL_NAME"
    mkdir -p "$MODEL_DIR"

    # Copy model file
    echo -e "${GREEN}Installing to $service...${NC}"
    cp "$DOWNLOADED_FILE" "$MODEL_DIR/"

    # Create metadata file
    cat > "$MODEL_DIR/model.json" <<EOF
{
  "name": "$MODEL_NAME",
  "file": "$FILE_NAME",
  "repo": "$REPO_ID",
  "size": "$FILE_SIZE",
  "installed": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

    echo -e "  ${GREEN}✓${NC} $service: $MODEL_DIR/$FILE_NAME"
done

# Cleanup
rm -rf "$TEMP_DIR"

echo
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo
echo -e "${BLUE}Model installed to:${NC}"
for service in "${SERVICES[@]}"; do
    if [ -d "services/$service/models/$MODEL_NAME" ]; then
        echo -e "  ${GREEN}✓${NC} services/$service/models/$MODEL_NAME/"
    fi
done
echo
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Update your .env file to use local models"
echo -e "  2. Set ${GREEN}LLM_PROVIDER=local${NC} or configure per-service"
echo -e "  3. Restart services to load the new models"
echo
echo -e "${BLUE}To install additional models:${NC}"
echo -e "  ${GREEN}./scripts/download-models.sh llama3.2${NC}"
echo -e "  ${GREEN}./scripts/download-models.sh mistral osteon synapse${NC} (specific services)"
echo

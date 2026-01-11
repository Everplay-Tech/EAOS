# Ollama Setup Guide - Local Open-Source LLMs

## Overview

BIOwerk now supports **completely open-source, locally-hosted LLMs** via Ollama! This means:
- ✅ **Zero API costs** - No external API fees
- ✅ **Full privacy** - Data never leaves your infrastructure
- ✅ **No rate limits** - Unlimited requests
- ✅ **Offline capable** - Works without internet after model download
- ✅ **Easy to deploy** - Included in docker-compose

## Recommended Models

### Best for Production

**Phi-3-mini (3.8B parameters)** - DEFAULT
```bash
docker exec -it biowerk-ollama ollama pull phi3:mini
```
- Size: ~2.3GB
- RAM: 8GB minimum
- Speed: Very fast
- Quality: Excellent for most tasks
- **Best for**: General use, reasoning, code

**Llama 3.2 (3B parameters)**
```bash
docker exec -it biowerk-ollama ollama pull llama3.2
```
- Size: ~2GB
- RAM: 8GB minimum
- Speed: Very fast
- Quality: Great for general tasks
- **Best for**: Conversation, content generation

### Best for Quality

**Mistral 7B**
```bash
docker exec -it biowerk-ollama ollama pull mistral
```
- Size: ~4.1GB
- RAM: 16GB recommended
- Speed: Fast
- Quality: Excellent
- **Best for**: Complex reasoning, detailed content

**Qwen2.5 7B**
```bash
docker exec -it biowerk-ollama ollama pull qwen2.5:7b
```
- Size: ~4.7GB
- RAM: 16GB recommended
- Speed: Fast
- Quality: Excellent for structured outputs
- **Best for**: JSON generation, data analysis

### For High-End Hardware

**Llama 3.1 8B**
```bash
docker exec -it biowerk-ollama ollama pull llama3.1:8b
```
- Size: ~4.7GB
- RAM: 16GB+ recommended
- Speed: Medium-fast
- Quality: Very high
- **Best for**: Production workloads with quality requirements

## Quick Start

### 1. Start the System
```bash
docker compose up -d
```

This will:
- Start Ollama service automatically
- Services default to Ollama provider
- Ollama will auto-pull `phi3:mini` on first use

### 2. Verify Ollama is Running
```bash
# Check Ollama status
docker exec -it biowerk-ollama ollama list

# Test with a simple request
curl http://localhost:11434/api/tags
```

### 3. Pull Your Preferred Model
```bash
# Pull phi3:mini (default, ~2.3GB)
docker exec -it biowerk-ollama ollama pull phi3:mini

# Or pull another model
docker exec -it biowerk-ollama ollama pull llama3.2
docker exec -it biowerk-ollama ollama pull mistral
```

### 4. Configure the Model
Edit `.env`:
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=phi3:mini  # or llama3.2, mistral, etc.
```

### 5. Test the Integration
```bash
# Test content generation
curl -X POST http://localhost:8080/osteon/outline \
  -H "Content-Type: application/json" \
  -d '{"id":"test-1","input":{"topic":"AI Safety"}}'
```

## Performance Comparison

| Model | Size | RAM Required | Speed | Quality | Use Case |
|-------|------|-------------|-------|---------|----------|
| phi3:mini | 2.3GB | 8GB | ⚡⚡⚡ | ⭐⭐⭐⭐ | **Default - Best balance** |
| llama3.2 | 2GB | 8GB | ⚡⚡⚡ | ⭐⭐⭐ | Fast general tasks |
| mistral | 4.1GB | 16GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | High quality outputs |
| qwen2.5:7b | 4.7GB | 16GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | Structured data |
| llama3.1:8b | 4.7GB | 16GB+ | ⚡⚡ | ⭐⭐⭐⭐⭐ | Production quality |

## Advanced Configuration

### GPU Acceleration (NVIDIA)

For better performance with GPU:

1. **Install NVIDIA Container Toolkit**
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. **Update docker-compose.yml**
```yaml
ollama:
  image: ollama/ollama:latest
  container_name: biowerk-ollama
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

3. **Restart services**
```bash
docker compose down
docker compose up -d
```

### Model Management

**List installed models:**
```bash
docker exec -it biowerk-ollama ollama list
```

**Remove a model:**
```bash
docker exec -it biowerk-ollama ollama rm mistral
```

**Pull specific version:**
```bash
docker exec -it biowerk-ollama ollama pull phi3:3.8b-mini-instruct-4k-fp16
```

**Check model info:**
```bash
docker exec -it biowerk-ollama ollama show phi3:mini
```

### Custom Model Configuration

You can customize model parameters in `.env`:

```bash
# Ollama Configuration
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=phi3:mini
OLLAMA_MAX_TOKENS=4096
OLLAMA_TEMPERATURE=0.7      # 0.0-1.0, lower = more deterministic
OLLAMA_TIMEOUT=120          # Seconds
```

## Switching Between Providers

You can easily switch between local (Ollama) and cloud providers:

### Use Ollama (Local, Free)
```bash
LLM_PROVIDER=ollama
```

### Use OpenAI (Cloud, Paid)
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Use Anthropic Claude (Cloud, Paid)
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

### Use DeepSeek (Cloud, Cheap)
```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
```

## Troubleshooting

### Model not pulling
```bash
# Check logs
docker logs biowerk-ollama

# Manual pull
docker exec -it biowerk-ollama ollama pull phi3:mini
```

### Out of memory
- Use a smaller model (phi3:mini or llama3.2)
- Close other applications
- Increase Docker memory limit

### Slow responses
- Use GPU acceleration (see above)
- Use a smaller model
- Reduce `OLLAMA_MAX_TOKENS`

### Connection errors
```bash
# Check Ollama is running
docker ps | grep ollama

# Check health
curl http://localhost:11434/api/tags

# Restart Ollama
docker restart biowerk-ollama
```

## Cost Comparison

### Local (Ollama)
- **Setup cost**: $0 (free models)
- **Per-request cost**: $0
- **1M requests/month**: $0
- **Hardware**: Use existing servers

### OpenAI GPT-4
- **Setup cost**: API key
- **Per-request cost**: ~$0.03 per 1K tokens
- **1M requests/month**: ~$30,000+
- **Hardware**: None needed

### Anthropic Claude
- **Setup cost**: API key
- **Per-request cost**: ~$0.015 per 1K tokens
- **1M requests/month**: ~$15,000+
- **Hardware**: None needed

### DeepSeek
- **Setup cost**: API key
- **Per-request cost**: ~$0.001 per 1K tokens
- **1M requests/month**: ~$1,000+
- **Hardware**: None needed

**Ollama = Completely FREE** after initial download!

## Recommended Strategy

**Development**: Use Ollama (phi3:mini)
- Fast iteration
- No API costs
- Privacy

**Production - Low Traffic**: Use Ollama (mistral or llama3.1:8b)
- High quality
- Cost effective
- Full control

**Production - High Traffic**: Use mix of Ollama + DeepSeek fallback
- Primary: Ollama for most requests
- Fallback: DeepSeek for overflow/complex tasks
- Cost: Minimal DeepSeek usage only

**Production - Critical**: Use Anthropic Claude or OpenAI
- Best quality
- Reliability
- Support

## Next Steps

1. ✅ Pull your preferred model
2. ✅ Update `.env` with `LLM_PROVIDER=ollama`
3. ✅ Test with example requests
4. ✅ Monitor performance and adjust model as needed
5. ✅ Consider GPU acceleration for production

## Support

For issues:
- Ollama docs: https://ollama.ai/library
- Model list: https://ollama.ai/library
- BIOwerk issues: https://github.com/E-TECH-PLAYTECH/BIOwerk/issues

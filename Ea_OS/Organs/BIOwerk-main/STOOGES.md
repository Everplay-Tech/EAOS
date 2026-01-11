# The 3 Stooges Architecture

## Overview

Meet **Larry, Moe, and Harry** - the three PHI2-powered coordinators that sit above your worker services and make BIOwerk truly intelligent.

```
                         USER
                           ↕
┌────────────────── THE 3 STOOGES (PHI2) ──────────────────┐
│                                                           │
│   LARRY              MOE              HARRY               │
│   (port 8007)        (port 8008)      (port 8009)        │
│                                                           │
│   "Wise guy, eh?"    "Why I oughta…"  "Nyuk nyuk nyuk!"  │
│                                                           │
│   Conversational     Orchestrator     Monitor            │
│   Interface          Coordinator      Health Tracker     │
│                                                           │
└───────────────────────────────────────────────────────────┘
                           ↕
                    MESH GATEWAY
                      (port 8080)
                           ↕
┌─────────────── WORKER SERVICES (PHI3) ───────────────────┐
│                                                           │
│   OSTEON    SYNAPSE    MYOCYTE    NUCLEUS                │
│   (8001)    (8003)     (8002)     (8005)                 │
│                                                           │
│   CHAPERONE    CIRCADIAN                                 │
│   (8006)       (8004)                                    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## The Stooges

### 🎭 LARRY - The Conversational Stooge
**"Wise guy, eh?"**

**Role**: Translates user requests into structured service calls

**Port**: 8007

**Model**: PHI2 (2.7GB)

**What Larry does**:
- Understands natural language requests
- Translates them into structured service calls
- Acts as the conversational interface
- Helps users figure out what they want

**Example**:
```bash
curl -X POST http://localhost:8007/translate \
  -d '{"text": "Generate a blog post about AI safety"}'

# Returns:
{
  "service": "osteon",
  "intent": "outline",
  "parameters": {"topic": "AI safety"},
  "confidence": 0.95
}
```

**Endpoints**:
- `GET /health` - Check if Larry is alive
- `POST /translate` - Translate natural language to service calls
- `POST /chat` - Have a conversation with Larry

---

### 🎭 MOE - The Orchestrator Stooge
**"Why I oughta..."**

**Role**: Routes and orchestrates multi-service workflows

**Port**: 8008

**Model**: PHI2 (2.7GB)

**What Moe does**:
- Creates execution plans for complex workflows
- Coordinates multiple services
- Handles dependencies and sequencing
- Calls the shots and makes services work together

**Example**:
```bash
curl -X POST http://localhost:8008/plan \
  -d '{"goal": "Create blog post, schedule it, and monitor engagement"}'

# Returns:
{
  "steps": [
    {"step": 1, "service": "osteon", "action": "generate_post"},
    {"step": 2, "service": "circadian", "action": "schedule"},
    {"step": 3, "service": "chaperone", "action": "monitor"}
  ],
  "estimated_time": 120,
  "dependencies": {"2": ["1"], "3": ["2"]}
}
```

**Endpoints**:
- `GET /health` - Check if Moe is alive
- `POST /plan` - Create a workflow orchestration plan
- `POST /execute` - Execute a workflow plan

---

### 🎭 HARRY - The Monitor Stooge
**"Nyuk nyuk nyuk!"**

**Role**: Monitors service health and system state

**Port**: 8009

**Model**: PHI2 (2.7GB)

**What Harry does**:
- Checks health of all services
- Tracks performance metrics
- Analyzes system state with AI
- Provides recommendations
- Watches everything!

**Example**:
```bash
curl http://localhost:8009/check-all

# Returns:
{
  "stooge": "harry",
  "overall_status": "healthy",
  "services": [
    {"service": "osteon", "status": "healthy", "response_time": 0.023},
    {"service": "synapse", "status": "healthy", "response_time": 0.019},
    ...
  ],
  "summary": "6/6 services healthy"
}
```

**Endpoints**:
- `GET /health` - Check if Harry is alive
- `GET /check/{service}` - Check specific service health
- `GET /check-all` - Check all services
- `POST /analyze` - AI-powered system analysis
- `GET /history/{service}` - Get health check history

---

## Installation

### 1. Download PHI2 Models

Download PHI2 for all three stooges:

```bash
# Easy way - install to all stooges at once
./scripts/download-models.sh stooges

# Or manually to each stooge
./scripts/download-models.sh phi2 larry
./scripts/download-models.sh phi2 moe
./scripts/download-models.sh phi2 harry
```

This will create:
```
services/
├── larry/models/phi2/model.gguf   (2.7GB)
├── moe/models/phi2/model.gguf     (2.7GB)
└── harry/models/phi2/model.gguf   (2.7GB)
Total: 8.1GB for the Stooges
```

### 2. Start the Stooges

```bash
# Start all services including the Stooges
docker compose up -d

# Or start just the Stooges
docker compose up -d larry moe harry
```

### 3. Verify They're Alive

```bash
# Check Larry
curl http://localhost:8007/health

# Check Moe
curl http://localhost:8008/health

# Check Harry
curl http://localhost:8009/health
```

---

## Usage Examples

### Conversational Interface (Larry)

```bash
# Translate user request
curl -X POST http://localhost:8007/translate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "I need to generate content about machine learning"
  }'

# Chat with Larry
curl -X POST http://localhost:8007/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What can I do with BIOwerk?"
  }'
```

### Workflow Orchestration (Moe)

```bash
# Create a workflow plan
curl -X POST http://localhost:8008/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Generate and publish a complete blog series",
    "context": {"topic": "AI ethics", "posts": 3}
  }'

# Execute the plan
curl -X POST http://localhost:8008/execute \
  -H "Content-Type: application/json" \
  -d '{
    "steps": [...]  # Plan from above
  }'
```

### System Monitoring (Harry)

```bash
# Check all services
curl http://localhost:8009/check-all

# Check specific service
curl http://localhost:8009/check/osteon

# Get AI-powered analysis
curl -X POST http://localhost:8009/analyze

# View health history
curl http://localhost:8009/history/osteon?limit=20
```

---

## Complete Workflow Example

**Scenario**: User wants to create and publish content

### Step 1: User talks to Larry
```bash
curl -X POST http://localhost:8007/translate \
  -d '{"text": "Create a blog post about quantum computing and publish it"}'

# Larry returns:
{
  "service": "moe",  # Larry knows this needs orchestration!
  "intent": "workflow",
  "parameters": {
    "goal": "Create and publish blog post about quantum computing"
  }
}
```

### Step 2: Larry forwards to Moe
```bash
curl -X POST http://localhost:8008/plan \
  -d '{"goal": "Create and publish blog post about quantum computing"}'

# Moe creates plan:
{
  "steps": [
    {"step": 1, "service": "osteon", "action": "outline"},
    {"step": 2, "service": "osteon", "action": "write"},
    {"step": 3, "service": "circadian", "action": "schedule"},
    {"step": 4, "service": "chaperone", "action": "monitor"}
  ]
}
```

### Step 3: Harry monitors execution
```bash
# Harry watches all services during execution
curl http://localhost:8009/check-all

# If issues arise, Harry analyzes
curl -X POST http://localhost:8009/analyze
```

---

## Architecture Benefits

### Why 3 Separate Stooges?

**Separation of Concerns**:
- **Larry** = User interaction (UX layer)
- **Moe** = Business logic (orchestration)
- **Harry** = Operations (monitoring)

**Independent Scaling**:
- Need more conversational capacity? Scale Larry
- Complex workflows? Scale Moe
- Heavy monitoring? Scale Harry

**Specialized Models**:
- Each stooge uses PHI2 (2.7GB, fast, efficient)
- Optimized for their specific role
- Worker services use PHI3-mini (3.8GB, more capable)

**Resilience**:
- If one stooge fails, others continue
- Clear failure boundaries
- Easy debugging

---

## Storage Requirements

### Stooges (PHI2)
- Larry: 2.7GB
- Moe: 2.7GB
- Harry: 2.7GB
- **Total**: 8.1GB

### Workers (PHI3-mini)
- Osteon: 2.3GB
- Synapse: 2.3GB
- Myocyte: 2.3GB
- Nucleus: 2.3GB
- Chaperone: 2.3GB
- Circadian: 2.3GB
- **Total**: 13.8GB

### Grand Total
**21.9GB** for complete standalone deployment

---

## Why "The 3 Stooges"?

**Larry**: The talker - always interacting with people
**Moe**: The boss - tells everyone what to do
**Harry**: The watcher - observes and reacts

Together they create chaos... but in a good way! 🎭

---

## Configuration

### Environment Variables

Each stooge uses these settings (from `.env`):

```bash
# Stooges use local PHI2 models
LLM_PROVIDER=local
LOCAL_MODEL_PATH=./models
LOCAL_MODEL_NAME=phi2
LOCAL_MODEL_FILE=model.gguf
LOCAL_MAX_TOKENS=2048
LOCAL_TEMPERATURE=0.7
LOCAL_GPU_LAYERS=0  # Set >0 for GPU acceleration
```

### Port Mapping

- Larry: `8007`
- Moe: `8008`
- Harry: `8009`
- Mesh: `8080` (entry point)
- Workers: `8001-8006`

---

## Troubleshooting

### Stooges not responding

```bash
# Check logs
docker logs biowerk-larry
docker logs biowerk-moe
docker logs biowerk-harry

# Verify models are downloaded
ls -lh services/larry/models/phi2/
ls -lh services/moe/models/phi2/
ls -lh services/harry/models/phi2/
```

### Models not loaded

```bash
# Download PHI2 models
./scripts/download-models.sh stooges

# Restart services
docker compose restart larry moe harry
```

### Out of memory

PHI2 requires ~4GB RAM per instance (3 × 4GB = 12GB total)

**Solutions**:
- Close other applications
- Increase Docker memory limit
- Use GPU offloading (`LOCAL_GPU_LAYERS=32`)
- Run fewer stooges at once

---

## Advanced Usage

### Custom Workflows

Create complex multi-stooge workflows:

```bash
# User → Larry → Moe → Workers → Harry

# 1. User talks to Larry
USER_REQUEST="Build a complete content pipeline"

# 2. Larry translates
TRANSLATION=$(curl -X POST http://localhost:8007/translate \
  -d "{\"text\": \"$USER_REQUEST\"}")

# 3. Moe orchestrates
PLAN=$(curl -X POST http://localhost:8008/plan \
  -d "$TRANSLATION")

# 4. Execute workflow
RESULTS=$(curl -X POST http://localhost:8008/execute \
  -d "$PLAN")

# 5. Harry monitors and reports
curl -X POST http://localhost:8009/analyze
```

### Integration with Mesh

The Mesh gateway can route through the Stooges:

```
User Request
    ↓
Mesh (/api/smart)
    ↓
Larry (translate)
    ↓
Moe (orchestrate)
    ↓
Workers (execute)
    ↓
Harry (monitor)
    ↓
Response to User
```

---

## Future Enhancements

- **Memory**: Persistent conversation history
- **Learning**: Adapt based on usage patterns
- **Optimization**: Dynamic model swapping
- **Scaling**: Kubernetes-ready deployment
- **UI**: Dashboard for the 3 Stooges

---

## Support

- **Issues**: https://github.com/E-TECH-PLAYTECH/BIOwerk/issues
- **Models**: See [MODELS_SETUP.md](./MODELS_SETUP.md)
- **General**: See [README.md](./README.md)

---

**"Nyuk nyuk nyuk!"** - The 3 Stooges are ready to work! 🎭

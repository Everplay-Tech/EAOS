# BIOwerk Cross-Platform Setup Guide

BIOwerk works on **Windows, Mac, and Linux**. This guide covers platform-specific setup.

## Quick Platform Detection

**What platform am I on?**
- **Windows**: You have `C:\` drives and PowerShell
- **Mac**: You have `/Users/` and Terminal.app
- **Linux**: You have `/home/` and various terminals

---

## Prerequisites (All Platforms)

### Required Software

1. **Docker Desktop**
   - **Windows**: [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
   - **Mac**: [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
   - **Linux**: [Docker Engine](https://docs.docker.com/engine/install/) + Docker Compose

2. **Python 3.11+** (for model downloads)
   - **Windows**: [python.org](https://www.python.org/downloads/)
   - **Mac**: `brew install python@3.11` or [python.org](https://www.python.org/downloads/)
   - **Linux**: `sudo apt install python3.11` or your package manager

3. **Git**
   - **Windows**: [Git for Windows](https://git-scm.com/download/win) (includes Git Bash)
   - **Mac**: Pre-installed or `brew install git`
   - **Linux**: `sudo apt install git` or your package manager

---

## Installation by Platform

### 🪟 Windows Setup

#### Option 1: PowerShell (Recommended)

```powershell
# Clone repository
git clone https://github.com/E-TECH-PLAYTECH/BIOwerk.git
cd BIOwerk

# Install Python dependencies
pip install huggingface_hub

# Download models for the 3 Stooges
.\scripts\download-models.ps1 stooges

# Download models for worker services
.\scripts\download-models.ps1 workers

# Start services
docker compose up -d
```

#### Option 2: Git Bash (Unix-style)

```bash
# Clone repository
git clone https://github.com/E-TECH-PLAYTECH/BIOwerk.git
cd BIOwerk

# Install Python dependencies
pip install huggingface_hub

# Download models (use bash script)
./scripts/download-models.sh stooges
./scripts/download-models.sh workers

# Start services
docker compose up -d
```

#### Option 3: WSL2 (Windows Subsystem for Linux)

Follow the **Linux Setup** instructions inside WSL2.

**Accessing services from Windows:**
- Services run on `localhost` (Docker Desktop handles networking)
- Access at `http://localhost:8007`, `http://localhost:8008`, etc.

---

### 🍎 Mac Setup

#### Intel Mac or Apple Silicon (M1/M2/M3)

```bash
# Clone repository
git clone https://github.com/E-TECH-PLAYTECH/BIOwerk.git
cd BIOwerk

# Install Python dependencies
pip3 install huggingface_hub

# Download models for the 3 Stooges
./scripts/download-models.sh stooges

# Download models for worker services
./scripts/download-models.sh workers

# Start services
docker compose up -d
```

#### Apple Silicon Specific Notes

Docker Desktop for Mac handles ARM64 → x86_64 translation automatically.

**For better performance** on M1/M2/M3, you can use native ARM builds:
```dockerfile
# In Dockerfile, change FROM line:
FROM --platform=linux/arm64 python:3.11-slim
```

---

### 🐧 Linux Setup

#### Ubuntu/Debian

```bash
# Install Docker and Docker Compose
sudo apt update
sudo apt install docker.io docker-compose python3-pip

# Add user to docker group (avoid sudo)
sudo usermod -aG docker $USER
newgrp docker

# Clone repository
git clone https://github.com/E-TECH-PLAYTECH/BIOwerk.git
cd BIOwerk

# Install Python dependencies
pip3 install huggingface_hub

# Download models
./scripts/download-models.sh stooges
./scripts/download-models.sh workers

# Start services
docker compose up -d
```

#### Other Linux Distributions

- **Fedora/RHEL**: `sudo dnf install docker docker-compose`
- **Arch**: `sudo pacman -S docker docker-compose`
- **openSUSE**: `sudo zypper install docker docker-compose`

---

## Platform-Specific Model Downloads

### Script Usage

**Windows PowerShell:**
```powershell
# Download PHI2 for all 3 Stooges
.\scripts\download-models.ps1 stooges

# Download PHI3-mini for all workers
.\scripts\download-models.ps1 workers

# Download specific model to specific services
.\scripts\download-models.ps1 phi2 larry moe harry
.\scripts\download-models.ps1 mistral osteon synapse
```

**Mac/Linux Bash:**
```bash
# Download PHI2 for all 3 Stooges
./scripts/download-models.sh stooges

# Download PHI3-mini for all workers
./scripts/download-models.sh workers

# Download specific model to specific services
./scripts/download-models.sh phi2 larry moe harry
./scripts/download-models.sh mistral osteon synapse
```

---

## Docker Networking by Platform

### Windows

**Docker Desktop for Windows:**
- Services accessible at `localhost`
- Example: `http://localhost:8007` (Larry)
- Works from Windows native apps, WSL2, and browsers

**Port conflicts:**
```powershell
# Check what's using a port
netstat -ano | findstr :8007

# Stop process
taskkill /PID <process_id> /F
```

### Mac

**Docker Desktop for Mac:**
- Services accessible at `localhost`
- Example: `http://localhost:8007` (Larry)

**Port conflicts:**
```bash
# Check what's using a port
lsof -i :8007

# Stop process
kill -9 <process_id>
```

### Linux

**Native Docker:**
- Services accessible at `localhost` or `127.0.0.1`
- Example: `http://localhost:8007` (Larry)

**Port conflicts:**
```bash
# Check what's using a port
sudo lsof -i :8007

# Or use netstat
sudo netstat -tulpn | grep :8007

# Stop process
sudo kill -9 <process_id>
```

---

## File Paths by Platform

### Windows

**Two styles (both work):**
```powershell
# PowerShell style (backslashes)
.\services\larry\models\phi2\

# Git Bash / WSL style (forward slashes)
./services/larry/models/phi2/
```

**Inside Docker containers:** Always use Linux-style paths (`/app/models/phi2/`)

### Mac/Linux

**Unix style:**
```bash
./services/larry/models/phi2/
```

---

## Storage Locations by Platform

### Windows

**Models stored in:**
```
C:\Users\<YourName>\BIOwerk\services\larry\models\
C:\Users\<YourName>\BIOwerk\services\moe\models\
C:\Users\<YourName>\BIOwerk\services\harry\models\
```

**Docker volumes:**
```powershell
# List Docker volumes
docker volume ls

# Inspect volume location
docker volume inspect biowerk_postgres_data
```

Typically in: `\\wsl$\docker-desktop-data\...` (WSL2 backend)

### Mac

**Models stored in:**
```
/Users/<YourName>/BIOwerk/services/larry/models/
/Users/<YourName>/BIOwerk/services/moe/models/
/Users/<YourName>/BIOwerk/services/harry/models/
```

**Docker volumes:**
```bash
# List volumes
docker volume ls

# Inspect location
docker volume inspect biowerk_postgres_data
```

Typically in: `~/Library/Containers/com.docker.docker/Data/...`

### Linux

**Models stored in:**
```
/home/<username>/BIOwerk/services/larry/models/
/home/<username>/BIOwerk/services/moe/models/
/home/<username>/BIOwerk/services/harry/models/
```

**Docker volumes:**
```bash
# List volumes
docker volume ls

# Inspect location
docker volume inspect biowerk_postgres_data
```

Typically in: `/var/lib/docker/volumes/...`

---

## Storage Requirements by Platform

All platforms need the same storage:

**The 3 Stooges (PHI2):**
- Larry: 2.7GB
- Moe: 2.7GB
- Harry: 2.7GB
- **Total**: 8.1GB

**Worker Services (PHI3-mini):**
- 6 services × 2.3GB each
- **Total**: 13.8GB

**Grand Total**: ~22GB free space needed

**Plus Docker images**: ~5GB

**Total recommended**: **30GB free space**

---

## Platform-Specific Issues & Solutions

### Windows

#### Issue: "Permission denied" errors
```powershell
# Run PowerShell as Administrator
# Or in Git Bash:
chmod +x scripts/download-models.sh
```

#### Issue: Line ending errors (CRLF vs LF)
```bash
# Git automatically handles this with .gitattributes
# If needed, configure Git:
git config --global core.autocrlf true
```

#### Issue: Docker not starting
- Ensure WSL2 is installed and enabled
- Enable "Use WSL 2 based engine" in Docker Desktop settings
- Restart Docker Desktop

### Mac

#### Issue: "Cannot execute binary file"
```bash
# Rosetta 2 may be needed on Apple Silicon
softwareupdate --install-rosetta

# Or ensure Docker is using correct architecture
docker buildx build --platform linux/arm64 ...
```

#### Issue: Slow model downloads
```bash
# Mac may throttle background downloads
# Keep laptop plugged in and screen on during downloads
```

### Linux

#### Issue: Permission denied on Docker
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

#### Issue: Out of space
```bash
# Clean up Docker
docker system prune -a --volumes

# Remove unused models
rm -rf services/*/models/old-model-name
```

---

## Testing Your Setup

### Test on All Platforms

```bash
# Check Docker
docker --version
docker compose version

# Check Python
python --version
python -m pip --version

# Start services
docker compose up -d

# Wait 30 seconds, then test Larry
curl http://localhost:8007/health

# Or in PowerShell:
Invoke-WebRequest http://localhost:8007/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "stooge": "larry",
  "catchphrase": "Wise guy, eh?"
}
```

---

## Environment Variables by Platform

### Windows PowerShell

```powershell
# Set environment variable
$env:LLM_PROVIDER = "local"

# Or edit .env file
notepad .env
```

### Mac/Linux

```bash
# Set environment variable
export LLM_PROVIDER=local

# Or edit .env file
nano .env
# or
vim .env
```

**All platforms:** `.env` file is the recommended approach

---

## Accessing Services

All platforms use the same URLs:

- **Larry** (Conversational): http://localhost:8007
- **Moe** (Orchestrator): http://localhost:8008
- **Harry** (Monitor): http://localhost:8009
- **Mesh Gateway**: http://localhost:8080
- **Osteon**: http://localhost:8001
- **Synapse**: http://localhost:8003
- **Myocyte**: http://localhost:8002

---

## Performance Tips by Platform

### Windows
- Use WSL2 backend for Docker (faster than Hyper-V)
- Store repository in WSL2 filesystem for better I/O
- Allocate sufficient RAM to Docker Desktop (8GB minimum)

### Mac
- Apple Silicon: Significantly faster than Intel
- Allocate RAM in Docker Desktop settings (8GB minimum)
- Use native ARM builds when possible

### Linux
- Native performance (fastest option)
- Use SSD for model storage
- Consider GPU acceleration with NVIDIA Docker

---

## GPU Acceleration (Optional)

### Windows (NVIDIA)

Requires WSL2 + NVIDIA Container Toolkit:

```powershell
# In WSL2 Ubuntu terminal
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

Update `.env`:
```
LOCAL_GPU_LAYERS=32  # Offload layers to GPU
```

### Mac

Apple Silicon has built-in GPU but llama-cpp-python uses Metal backend:

```bash
# Install Metal-enabled version
pip install llama-cpp-python --force-reinstall --no-cache-dir
```

Update `.env`:
```
LOCAL_GPU_LAYERS=32  # Use Metal GPU
```

### Linux (NVIDIA)

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

Update docker-compose.yml to add GPU support.

---

## Quick Reference

| Task | Windows PowerShell | Mac/Linux Bash |
|------|-------------------|----------------|
| Download models | `.\scripts\download-models.ps1 stooges` | `./scripts/download-models.sh stooges` |
| Start services | `docker compose up -d` | `docker compose up -d` |
| Stop services | `docker compose down` | `docker compose down` |
| View logs | `docker compose logs -f larry` | `docker compose logs -f larry` |
| Check ports | `netstat -ano \| findstr :8007` | `lsof -i :8007` |
| Edit config | `notepad .env` | `nano .env` |

---

## Support

- **Documentation**: See [README.md](./README.md)
- **3 Stooges**: See [STOOGES.md](./STOOGES.md)
- **Models**: See [MODELS_SETUP.md](./MODELS_SETUP.md)
- **Issues**: https://github.com/E-TECH-PLAYTECH/BIOwerk/issues

---

**BIOwerk runs everywhere!** 🪟 🍎 🐧

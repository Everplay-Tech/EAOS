# Model Download Script for BIOwerk (PowerShell - Windows)
# Downloads LLM models and installs them into each service's local models directory
# Usage: .\scripts\download-models.ps1 [model_name] [services...]

param(
    [string]$ModelName = "phi3-mini",
    [string[]]$Services = @()
)

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Service groups
$WORKER_SERVICES = @("osteon", "synapse", "myocyte", "nucleus", "chaperone", "circadian")
$STOOGE_SERVICES = @("larry", "moe", "harry")
$ALL_SERVICES = $WORKER_SERVICES + $STOOGE_SERVICES

# Model registry
$MODEL_REGISTRY = @{
    "phi2" = "microsoft/phi-2:phi-2.Q4_K_M.gguf"
    "phi3-mini" = "microsoft/Phi-3-mini-4k-instruct-gguf:Phi-3-mini-4k-instruct-q4.gguf"
    "phi3" = "microsoft/Phi-3-mini-4k-instruct-gguf:Phi-3-mini-4k-instruct-q4.gguf"
    "llama3.2" = "hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF:llama-3.2-3b-instruct-q4_k_m.gguf"
    "mistral" = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF:mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    "qwen2.5" = "Qwen/Qwen2.5-7B-Instruct-GGUF:qwen2.5-7b-instruct-q4_k_m.gguf"
}

Write-ColorOutput Cyan "================================================"
Write-ColorOutput Cyan "  BIOwerk Model Download & Installation"
Write-ColorOutput Cyan "================================================"
Write-Output ""

# Handle special shortcuts
if ($ModelName -eq "stooges") {
    $ModelName = "phi2"
    if ($Services.Length -eq 0) {
        $Services = $STOOGE_SERVICES
    }
} elseif ($ModelName -eq "workers") {
    $ModelName = "phi3-mini"
    if ($Services.Length -eq 0) {
        $Services = $WORKER_SERVICES
    }
} else {
    if ($Services.Length -eq 0) {
        $Services = $ALL_SERVICES
    }
}

# Validate model name
if (-not $MODEL_REGISTRY.ContainsKey($ModelName)) {
    Write-ColorOutput Red "Error: Unknown model '$ModelName'"
    Write-ColorOutput Yellow "Available models:"
    foreach ($model in $MODEL_REGISTRY.Keys) {
        Write-ColorOutput Green "  - $model"
    }
    exit 1
}

# Get model info
$ModelInfo = $MODEL_REGISTRY[$ModelName]
$RepoId, $FileName = $ModelInfo -split ":"

Write-ColorOutput Green "Model: $ModelName"
Write-ColorOutput Green "Repository: $RepoId"
Write-ColorOutput Green "File: $FileName"
Write-ColorOutput Green "Services: $($Services -join ', ')"
Write-Output ""

# Check if huggingface-cli is available
$huggingface_cli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
if (-not $huggingface_cli) {
    Write-ColorOutput Yellow "huggingface-cli not found. Installing..."
    pip install -q huggingface_hub
}

# Create temp directory
$TEMP_DIR = "$env:TEMP\biowerk-models"
if (Test-Path $TEMP_DIR) {
    Remove-Item -Recurse -Force $TEMP_DIR
}
New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null

Write-ColorOutput Blue "Downloading model from HuggingFace..."
Write-ColorOutput Yellow "This may take several minutes depending on model size"
Write-Output ""

# Download model
huggingface-cli download $RepoId $FileName --local-dir $TEMP_DIR --local-dir-use-symlinks False

$DOWNLOADED_FILE = Join-Path $TEMP_DIR $FileName

if (-not (Test-Path $DOWNLOADED_FILE)) {
    Write-ColorOutput Red "Error: Model file not found after download"
    exit 1
}

# Get file size
$FileSize = (Get-Item $DOWNLOADED_FILE).Length / 1GB
$FileSizeStr = "{0:N2} GB" -f $FileSize

Write-Output ""
Write-ColorOutput Green "Download complete! Size: $FileSizeStr"
Write-Output ""

# Copy to each service
Write-ColorOutput Blue "Installing model to services..."
foreach ($service in $Services) {
    $SERVICE_DIR = "services\$service\models"

    if (-not (Test-Path $SERVICE_DIR)) {
        Write-ColorOutput Yellow "Warning: Service directory not found: $SERVICE_DIR"
        continue
    }

    # Create model-specific subdirectory
    $MODEL_DIR = Join-Path $SERVICE_DIR $ModelName
    if (-not (Test-Path $MODEL_DIR)) {
        New-Item -ItemType Directory -Path $MODEL_DIR | Out-Null
    }

    # Copy model file
    Write-ColorOutput Green "Installing to $service..."
    Copy-Item $DOWNLOADED_FILE (Join-Path $MODEL_DIR $FileName)

    # Create metadata file
    $metadata = @{
        name = $ModelName
        file = $FileName
        repo = $RepoId
        size = $FileSizeStr
        installed = (Get-Date -Format "o")
    } | ConvertTo-Json

    $metadata | Out-File -FilePath (Join-Path $MODEL_DIR "model.json") -Encoding UTF8

    Write-ColorOutput Green "  ✓ $service`: $MODEL_DIR\$FileName"
}

# Cleanup
Remove-Item -Recurse -Force $TEMP_DIR

Write-Output ""
Write-ColorOutput Green "================================================"
Write-ColorOutput Green "  Installation Complete!"
Write-ColorOutput Green "================================================"
Write-Output ""
Write-ColorOutput Blue "Model installed to:"
foreach ($service in $Services) {
    $MODEL_DIR = "services\$service\models\$ModelName"
    if (Test-Path $MODEL_DIR) {
        Write-ColorOutput Green "  ✓ $MODEL_DIR"
    }
}
Write-Output ""
Write-ColorOutput Yellow "Next steps:"
Write-Output "  1. Update your .env file to use local models"
Write-Output "  2. Set LLM_PROVIDER=local"
Write-Output "  3. Restart services to load the new models"
Write-Output ""
Write-ColorOutput Blue "To install additional models:"
Write-ColorOutput Green "  .\scripts\download-models.ps1 llama3.2"
Write-ColorOutput Green "  .\scripts\download-models.ps1 mistral osteon synapse"
Write-Output ""

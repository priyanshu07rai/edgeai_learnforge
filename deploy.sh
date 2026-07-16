#!/bin/bash

# LearnForge AI — Automated Deployment Script for NVIDIA Jetson Orin Nano / ARM64 Linux
# This script prepares the Python virtual environment, installs dependencies,
# sets up Ollama, downloads spaCy language models, and builds the frontend.

set -e # Exit immediately if a command exits with a non-zero status

# Color formatting for status messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${GREEN}                LearnForge AI — Jetson Orin Deployment                ${NC}"
echo -e "${BLUE}======================================================================${NC}"

# ── 1. PREREQUISITE CHECKS ────────────────────────────────────────────────────
echo -e "\n${YELLOW}[Step 1/6] Checking system prerequisites...${NC}"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed. Please install python3 first.${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "✓ Found Python 3 (v${PYTHON_VERSION})"

# Check for Node.js and npm
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed. Please install node (v18+) first.${NC}"
    exit 1
fi
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is not installed. Please install npm first.${NC}"
    exit 1
fi
echo -e "✓ Found Node.js ($(node -v)) and npm ($(npm -v))"

# Check for FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}Warning: FFmpeg is not installed on PATH. Standard system ffmpeg will be required for audio preprocessing.${NC}"
    echo -e "You can install it on Jetson via: ${GREEN}sudo apt-get install ffmpeg${NC}"
else
    echo -e "✓ Found FFmpeg ($(ffmpeg -version | head -n 1))"
fi

# Detect if we are running on NVIDIA Tegra/Jetson platform
IS_JETSON=false
if [ -f /etc/nv_tegra_release ] || grep -q -i "tegra" /proc/device-tree/model 2>/dev/null; then
    IS_JETSON=true
    echo -e "${GREEN}✓ NVIDIA Jetson Hardware platform detected!${NC}"
fi

# ── 2. PYTHON VIRTUAL ENVIRONMENT & PIP ───────────────────────────────────────
echo -e "\n${YELLOW}[Step 2/6] Setting up Python virtual environment...${NC}"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment '.venv'..."
    # Try standard venv first, fallback to user virtualenv if venv fails (e.g. read-only filesystem)
    if ! python3 -m venv .venv 2>/dev/null; then
        echo -e "${YELLOW}Warning: python3-venv is not available. Attempting fallback to virtualenv...${NC}"
        pip3 install --user virtualenv --no-warn-script-location
        # Add local pip bin path to PATH just in case
        export PATH=$HOME/.local/bin:$PATH
        python3 -m virtualenv .venv
    fi
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel

# ── 3. INSTALL PYTHON DEPENDENCIES ────────────────────────────────────────────
echo -e "\n${YELLOW}[Step 3/6] Installing Python packages...${NC}"

if [ "$IS_JETSON" = true ]; then
    echo -e "${BLUE}Configuring PyTorch for Jetpack/Jetson platform...${NC}"
    echo "Tip: For full GPU acceleration, it is recommended to install NVIDIA's official PyTorch wheel."
    
    # Attempt to install base requirements
    echo -e "Installing base dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    pip install -r requirements.txt
fi

# Download spaCy English model
echo "Downloading spaCy NLP model ('en_core_web_sm')..."
python3 -m spacy download en_core_web_sm || {
    echo -e "${YELLOW}Warning: spaCy model download failed. App will fall back to regex pre-cleaning.${NC}"
}

# ── 4. OLLAMA CONFIGURATION & MODEL PULL ──────────────────────────────────────
echo -e "\n${YELLOW}[Step 4/6] Setting up local LLM (Ollama)...${NC}"

if ! command -v ollama &> /dev/null; then
    echo "Ollama is not installed. Installing Ollama natively for Linux ARM64..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo -e "${GREEN}✓ Ollama installed successfully.${NC}"
else
    echo -e "✓ Ollama is already installed."
fi

# Ensure Ollama service is running, and pull the model
echo "Pulling llama3.2:1b model... (this may take a minute if not cached)"
# We start/ensure the service runs, then pull
if systemctl is-active --quiet ollama 2>/dev/null || service ollama status &>/dev/null; then
    echo "Ollama service is active."
else
    echo "Starting Ollama service (sudo systemctl start ollama)..."
    sudo systemctl start ollama || echo "Note: Unable to start systemd service. Make sure 'ollama serve' is running."
fi

# Pull the lightweight 1B model
ollama pull llama3.2:1b || {
    echo -e "${YELLOW}Warning: Failed to auto-pull llama3.2:1b. Make sure to pull it manually using 'ollama pull llama3.2:1b'${NC}"
}

# ── 5. FRONTEND INSTALLATION AND BUILD ────────────────────────────────────────
echo -e "\n${YELLOW}[Step 5/6] Building frontend assets...${NC}"

echo "Installing npm dependencies..."
npm install

echo "Building production assets (Vite + Tailwind)..."
npm run build

# ── 6. COMPLETED ──────────────────────────────────────────────────────────────
echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}              Deployment Setup Completed Successfully!                ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "\nTo run the application:"
echo -e "1. Activate virtual environment: ${GREEN}source .venv/bin/activate${NC}"
echo -e "2. Run the application helper script: ${GREEN}./run_app.sh${NC}"
echo -e "   This will start both backend FastAPI (port 8000) and host the built frontend."
echo -e "${BLUE}======================================================================${NC}"

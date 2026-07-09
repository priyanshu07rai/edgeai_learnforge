# Deployment Guide — NVIDIA Jetson Orin Nano

This guide explains how to deploy and run **LearnForge AI** on the **NVIDIA Jetson Orin Nano** platform (ARM64 architecture running Linux / JetPack).

---

## 📋 System Prerequisites

Ensure the following tools are installed on your Jetson board before running the setup scripts:

1. **JetPack SDK (5.x or 6.x)** (pre-installed on the cloud lab instance)
2. **Node.js (v18+) & npm**
   ```bash
   sudo apt-get update
   sudo apt-get install -y nodejs npm
   ```
3. **Python 3, pip, and venv**
   ```bash
   sudo apt-get install -y python3-pip python3-venv python3-dev build-essential
   ```
4. **FFmpeg** (necessary for audio preprocessing)
   ```bash
   sudo apt-get install -y ffmpeg
   ```

---

## ⚡ Step 1: Export CUDA Environment Variables

To ensure `faster-whisper` and `PyTorch` can access the Jetson's CUDA cores, make sure the CUDA toolkit paths are added to your environment.

Run the following commands or add them to your `~/.bashrc`:

```bash
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

---

## 🛠️ Step 2: Automated Deployment Setup

We have provided a unified script `deploy.sh` to automate the setup process. It will:
- Initialize the Python virtual environment (`.venv`).
- Install Python and Node.js dependencies.
- Pre-download the spaCy `en_core_web_sm` model.
- Automatically check for, install, and start **Ollama** on Linux ARM64.
- Pull the lightweight `llama3.2:1b` model.
- Compile and build the frontend assets (`npm run build`).

Run the deployment script from the project root:

```bash
# Make the scripts executable
chmod +x deploy.sh run_app.sh

# Run the setup script
./deploy.sh
```

---

## 🚀 Step 3: PyTorch GPU Acceleration (Optional but Recommended)

`deploy.sh` installs the base Python requirements. If you want full CUDA acceleration for the SentenceTransformers embeddings on the Jetson Orin Nano, you should install the official NVIDIA PyTorch wheel built specifically for JetPack.

### For JetPack 6.0 (Ubuntu 22.04):
```bash
source .venv/bin/activate
pip install --no-cache-dir --extra-index-url https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch torch
```

### For JetPack 5.1 (Ubuntu 20.04):
```bash
source .venv/bin/activate
pip install --no-cache-dir --extra-index-url https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch torch
```

---

## 🏃 Step 4: Running the Application

To boot up both the FastAPI backend and serve the built React frontend simultaneously, run the helper runner script:

```bash
./run_app.sh
```

Once running:
* **Frontend Web App:** accessible at `http://localhost:5173` (or `http://<your-jetson-ip>:5173`)
* **Backend FastAPI Server:** running on `http://localhost:8000`

Press `Ctrl+C` to cleanly shut down both servers.

---

## 🧹 Wiping Local Cache / Uploads (Fresh Start)

To delete all locally uploaded videos and session data (which are git-ignored and won't be pushed to GitHub), you can run:

```bash
rm -rf storage/* uploads/*
```

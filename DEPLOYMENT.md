# Deployment Guide — NVIDIA Jetson & Linux Boards

This guide explains how to deploy and run **LearnForge AI** on any remote **NVIDIA Jetson** or Linux platform via SSH using a single command: `./start.sh`.

---

## ⚡ Quick Start (Single Command)

To deploy LearnForge AI from a fresh clone:

```bash
git clone https://github.com/priyanshu07rai/edgeai_learnforge.git ~/edgeai_learnforge
cd ~/edgeai_learnforge
chmod +x start.sh
./start.sh
```

`./start.sh` handles **100% of the deployment workflow** automatically:
1. **Auto-Detects Environment**: Identifies ARM64 / Jetson vs x86 Linux.
2. **Auto-Provisions Tools**: Downloads Node.js 20 & Python `.venv` into user-local space without `sudo`.
3. **Storage Optimized**: Installs CPU-only PyTorch and purges `node_modules` after building to stay under **4 GB disk space**.
4. **Offline AI Services**: Provisions Ollama (`llama3.2:1b`), faster-whisper, and spaCy.
5. **Reverse Proxy & Tunnel**: Launches a Python SPA reverse proxy and exposes a global HTTPS URL via **Cloudflare Tunnel**.

---

## 📋 System Requirements

- **OS**: Ubuntu 20.04 / 22.04 LTS (ARM64 or x86_64)
- **RAM**: 4 GB minimum (8 GB recommended)
- **Disk Space**: ~3.5–4.0 GB free

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

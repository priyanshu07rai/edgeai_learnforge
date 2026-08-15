#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║        LearnForge AI — Universal Start Script                    ║
# ║  Works on: NVIDIA Jetson (ARM64) · Generic Linux (x86_64)        ║
# ║  Features: Auto-setup · Cloudflare Tunnel · Jetson-optimized     ║
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${BLUE}[LearnForge]${NC} $*"; }
ok()     { echo -e "${GREEN}  ✓${NC} $*"; }
warn()   { echo -e "${YELLOW}  ⚠${NC} $*"; }
err()    { echo -e "${RED}  ✗${NC} $*"; }
banner() { echo -e "\n${CYAN}${BOLD}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── Config ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_MIN_VERSION=20
NODE_INSTALL_DIR="$HOME/.local/learnforge-node20"
CLOUDFLARED_DIR="$HOME/.local/learnforge-tools"
BACKEND_PORT=8000
FRONTEND_PORT=5173
LOG_DIR="$SCRIPT_DIR/.logs"
PIDS_FILE="$SCRIPT_DIR/.logs/pids"

# Parse flags
SETUP_ONLY=false; RUN_ONLY=false
for arg in "$@"; do
  [[ "$arg" == "--setup-only" ]] && SETUP_ONLY=true
  [[ "$arg" == "--run-only"   ]] && RUN_ONLY=true
done

mkdir -p "$LOG_DIR" "$CLOUDFLARED_DIR"

echo -e "${BOLD}${CYAN}"
echo "  ██╗     ███████╗ █████╗ ██████╗ ███╗   ██╗███████╗ ██████╗ ██████╗  ██████╗ ███████╗"
echo "  ██║     ██╔════╝██╔══██╗██╔══██╗████╗  ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝"
echo "  ██║     █████╗  ███████║██████╔╝██╔██╗ ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  "
echo "  ██║     ██╔══╝  ██╔══██║██╔══██╗██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  "
echo "  ███████╗███████╗██║  ██║██║  ██║██║ ╚████║██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗"
echo "  ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo -e "${NC}"
echo -e "  ${GREEN}Production AI Learning Platform${NC} — Single-command deployment"
echo -e "  ─────────────────────────────────────────────────────────────────\n"

cd "$SCRIPT_DIR"

# ════════════════════════════════════════════════════════════════════
# ── PHASE 1: SYSTEM DETECTION ───────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 1: System Detection"

ARCH=$(uname -m)
IS_JETSON=false
IS_ARM=false
HAS_INTERNET=false

[[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]] && IS_ARM=true

if [ -f /etc/nv_tegra_release ] || grep -qi "tegra" /proc/device-tree/model 2>/dev/null; then
    IS_JETSON=true
    ok "NVIDIA Jetson platform detected (ARM64)"
elif $IS_ARM; then
    ok "ARM64 platform detected"
else
    ok "x86_64 platform detected"
fi

TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null || echo "4096")
ok "Available RAM: ${TOTAL_RAM_MB} MB"

# Check internet (fast, 3s timeout)
if curl -sf --max-time 3 --head https://cloudflare.com > /dev/null 2>&1; then
    HAS_INTERNET=true
    ok "Internet connectivity: available"
else
    warn "Internet connectivity: offline — Cloudflare Tunnel will be skipped"
fi

# ════════════════════════════════════════════════════════════════════
# ── PHASE 2: NODE.JS DETECTION & AUTO-INSTALL ───────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 2: Node.js"

NODE_BIN=""
NODE_CANDIDATES=(
    "$(command -v node 2>/dev/null || true)"
    "$NODE_INSTALL_DIR/bin/node"
    "$HOME/.local/node-v20.18.0-linux-arm64/bin/node"
    "$HOME/node-v20.18.0-linux-arm64/bin/node"
    "/usr/local/bin/node"
    "/usr/bin/node"
)
for candidate in "${NODE_CANDIDATES[@]}"; do
    if [[ -x "$candidate" ]]; then
        ver=$("$candidate" --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
        if [[ "$ver" -ge "$NODE_MIN_VERSION" ]] 2>/dev/null; then
            NODE_BIN="$candidate"
            ok "Found Node.js $("${NODE_BIN}" --version) at $NODE_BIN"
            break
        fi
    fi
done

if [[ -z "$NODE_BIN" ]]; then
    if ! $HAS_INTERNET; then
        err "Node.js v${NODE_MIN_VERSION}+ not found and no internet to download it."
        exit 1
    fi
    NODE_VERSION="20.18.0"
    if $IS_ARM; then
        NODE_TARBALL="node-v${NODE_VERSION}-linux-arm64.tar.xz"
    else
        NODE_TARBALL="node-v${NODE_VERSION}-linux-x64.tar.xz"
    fi
    log "Downloading Node.js v${NODE_VERSION} (~30MB)..."
    mkdir -p "$NODE_INSTALL_DIR"
    curl -L --progress-bar "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}" -o "/tmp/${NODE_TARBALL}"
    tar -xf "/tmp/${NODE_TARBALL}" --strip-components=1 -C "$NODE_INSTALL_DIR"
    rm -f "/tmp/${NODE_TARBALL}"
    NODE_BIN="$NODE_INSTALL_DIR/bin/node"
    ok "Node.js v${NODE_VERSION} installed"
fi

NODE_DIR="$(dirname "$(dirname "$NODE_BIN")")/bin"
export PATH="$NODE_DIR:$PATH"
NPM_BIN="$NODE_DIR/npm"

# Persist to .bashrc
if ! grep -q "learnforge-node20" "$HOME/.bashrc" 2>/dev/null; then
    echo "export PATH=\"$NODE_DIR:\$PATH\"  # learnforge-node20" >> "$HOME/.bashrc"
fi

# ════════════════════════════════════════════════════════════════════
# ── PHASE 3: PYTHON ENVIRONMENT ─────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 3: Python Environment"

if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Install with: sudo apt-get install python3 python3-venv"
    exit 1
fi
ok "Python $(python3 --version) found"

if [[ ! -f ".venv/bin/activate" ]]; then
    log "Creating Python virtual environment..."
    if ! python3 -m venv .venv 2>/dev/null; then
        warn "python3-venv unavailable, trying virtualenv..."
        pip3 install --user virtualenv --quiet
        export PATH="$HOME/.local/bin:$PATH"
        python3 -m virtualenv .venv
    fi
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

source .venv/bin/activate

CURRENT_PIP=$(pip --version | awk '{print $2}' | cut -d. -f1)
if [[ "$CURRENT_PIP" -lt 23 ]]; then
    log "Upgrading pip..."
    pip install --upgrade pip setuptools wheel --quiet
fi

# Skip reinstall if requirements unchanged (hash check)
REQS_HASH=$(md5sum requirements.txt 2>/dev/null | awk '{print $1}')
MARKER_FILE=".venv/.installed_hash"
INSTALLED_HASH=$(cat "$MARKER_FILE" 2>/dev/null || echo "none")

if [[ "$REQS_HASH" != "$INSTALLED_HASH" ]]; then
    log "Installing Python dependencies..."
    export PIP_NO_CACHE_DIR=1

    if $IS_JETSON; then
        log "Jetson: installing CPU-only PyTorch to save ~2GB disk..."
        pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet 2>&1 | tail -3
    fi

    pip install -r requirements.txt --quiet 2>&1 | tail -5

    # Download spaCy model only if not already present
    if ! python3 -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null; then
        log "Downloading spaCy model (~12MB)..."
        python3 -m spacy download en_core_web_sm --quiet || warn "spaCy model download failed — using fallback"
    else
        ok "spaCy model already installed"
    fi

    echo "$REQS_HASH" > "$MARKER_FILE"
    ok "Python dependencies installed"
else
    ok "Python dependencies up-to-date (skipping reinstall)"
fi

# ════════════════════════════════════════════════════════════════════
# ── PHASE 4: FRONTEND BUILD ──────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 4: Frontend Build"

# Hash all relevant frontend sources
BUILD_SOURCES_HASH=$(find src/ -name "*.jsx" -o -name "*.js" -o -name "*.css" -o -name "*.html" 2>/dev/null | \
    sort | xargs md5sum 2>/dev/null | md5sum | awk '{print $1}')
BUILD_SOURCES_HASH="${BUILD_SOURCES_HASH}$(md5sum package.json vite.config.js 2>/dev/null | md5sum | awk '{print $1}')"
BUILD_HASH_FILE="dist/.build_hash"
PREV_BUILD_HASH=$(cat "$BUILD_HASH_FILE" 2>/dev/null || echo "none")

if [[ "$BUILD_SOURCES_HASH" == "$PREV_BUILD_HASH" ]] && [[ -f "dist/index.html" ]]; then
    ok "Frontend build is up-to-date (skipping rebuild)"
else
    log "Building frontend..."
    if [[ -d "node_modules" ]]; then
        $NPM_BIN install --prefer-offline --no-fund --no-audit --quiet 2>&1 | tail -3
    else
        $NPM_BIN install --no-fund --no-audit --quiet 2>&1 | tail -5
    fi

    $NPM_BIN run build 2>&1 | grep -E "(built in|error|warning|✓)" || true
    mkdir -p dist
    echo "$BUILD_SOURCES_HASH" > "$BUILD_HASH_FILE"
    ok "Frontend built successfully"
fi

[[ "$SETUP_ONLY" == "true" ]] && { ok "Setup complete."; exit 0; }

# ════════════════════════════════════════════════════════════════════
# ── PHASE 5: ENVIRONMENT CONFIG ──────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 5: Environment"

if [[ ! -f ".env" ]]; then
    cat > .env << 'EOF'
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=5173
EOF
    ok ".env created"
else
    ok ".env already exists"
fi

# ════════════════════════════════════════════════════════════════════
# ── PHASE 6: KILL STALE PROCESSES ────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
banner "Phase 6: Cleanup"

kill_port() {
    local pids
    pids=$(lsof -ti :"$1" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        warn "Killing stale process(es) on port $1"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 0.5
    fi
}
kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT
pkill -f "cloudflared tunnel" 2>/dev/null || true
ok "Port cleanup done"

# ════════════════════════════════════════════════════════════════════
# ── PHASE 7: LAUNCH SERVICES ─────────────────────────════════════════
# ════════════════════════════════════════════════════════════════════
banner "Phase 7: Launching Services"

BACKEND_PID=""
FRONTEND_PID=""
TUNNEL_PID=""

cleanup() {
    echo -e "\n${YELLOW}Shutting down LearnForge AI...${NC}"
    [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    [[ -n "$TUNNEL_PID"   ]] && kill "$TUNNEL_PID"   2>/dev/null || true
    rm -f "$PIDS_FILE"
    echo -e "${GREEN}Goodbye!${NC}"
}
trap cleanup EXIT INT TERM

# Backend
log "Starting FastAPI backend..."
export PYTHONPATH="$SCRIPT_DIR/src/backend"
UVICORN_WORKERS=1
[[ "$TOTAL_RAM_MB" -gt 12000 ]] && UVICORN_WORKERS=2

python3 -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --workers "$UVICORN_WORKERS" \
    --limit-concurrency 20 \
    --timeout-keep-alive 30 \
    --log-level warning \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

# Wait for backend (15s)
for i in {1..15}; do
    if curl -sf "http://localhost:${BACKEND_PORT}/health" > /dev/null 2>&1 || \
       curl -sf "http://localhost:${BACKEND_PORT}/"      > /dev/null 2>&1; then
        ok "Backend running (PID $BACKEND_PID)"
        break
    fi
    sleep 1
    [[ "$i" == "15" ]] && warn "Backend slow to start — check: $LOG_DIR/backend.log"
done

# Frontend
log "Starting Vite preview server..."
$NPM_BIN run preview -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

for i in {1..10}; do
    if curl -sf "http://localhost:${FRONTEND_PORT}/" > /dev/null 2>&1; then
        ok "Frontend running (PID $FRONTEND_PID)"
        break
    fi
    sleep 1
    [[ "$i" == "10" ]] && warn "Frontend slow to start — check: $LOG_DIR/frontend.log"
done

echo "BACKEND_PID=$BACKEND_PID" > "$PIDS_FILE"
echo "FRONTEND_PID=$FRONTEND_PID" >> "$PIDS_FILE"

# Cloudflare Tunnel
PUBLIC_URL=""
if $HAS_INTERNET; then
    CLOUDFLARED_BIN=""
    CF_CANDIDATES=(
        "$(command -v cloudflared 2>/dev/null || true)"
        "$CLOUDFLARED_DIR/cloudflared"
        "/usr/local/bin/cloudflared"
        "/usr/bin/cloudflared"
    )
    for candidate in "${CF_CANDIDATES[@]}"; do
        if [[ -x "$candidate" ]]; then
            CLOUDFLARED_BIN="$candidate"
            ok "Found cloudflared at $CLOUDFLARED_BIN"
            break
        fi
    done

    if [[ -z "$CLOUDFLARED_BIN" ]]; then
        log "Downloading cloudflared (~40MB)..."
        if $IS_ARM; then
            CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        else
            CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        fi
        CLOUDFLARED_BIN="$CLOUDFLARED_DIR/cloudflared"
        if curl -L --progress-bar "$CF_URL" -o "$CLOUDFLARED_BIN" 2>&1; then
            chmod +x "$CLOUDFLARED_BIN"
            ok "cloudflared downloaded"
        else
            warn "cloudflared download failed — skipping public URL"
            CLOUDFLARED_BIN=""
        fi
    fi

    if [[ -n "$CLOUDFLARED_BIN" ]]; then
        TUNNEL_LOG="$LOG_DIR/tunnel.log"
        "$CLOUDFLARED_BIN" tunnel --url "http://localhost:${FRONTEND_PORT}" \
            --no-autoupdate \
            > "$TUNNEL_LOG" 2>&1 &
        TUNNEL_PID=$!
        echo "TUNNEL_PID=$TUNNEL_PID" >> "$PIDS_FILE"

        log "Waiting for Cloudflare tunnel..."
        for i in {1..20}; do
            PUBLIC_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1 || true)
            [[ -n "$PUBLIC_URL" ]] && break
            sleep 1
        done
        [[ -z "$PUBLIC_URL" ]] && warn "Could not extract public URL — check: $TUNNEL_LOG"
    fi
else
    warn "Offline — Cloudflare Tunnel skipped"
fi

# ════════════════════════════════════════════════════════════════════
# ── PHASE 8: PRINT ACCESS URLS ───────────────────────────────────────
# ════════════════════════════════════════════════════════════════════
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo -e "\n${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✅ LearnForge AI is up and running!${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e ""
echo -e "  ${BOLD}Local access:${NC}"
echo -e "    Frontend  →  ${CYAN}http://localhost:${FRONTEND_PORT}/${NC}"
echo -e "    Backend   →  ${CYAN}http://localhost:${BACKEND_PORT}/${NC}"
echo -e "    Network   →  ${CYAN}http://${LOCAL_IP}:${FRONTEND_PORT}/${NC}"
if [[ -n "$PUBLIC_URL" ]]; then
echo -e ""
echo -e "  ${BOLD}${GREEN}🌍 Public URL (share this with anyone!):${NC}"
echo -e "    ${BOLD}${GREEN}${PUBLIC_URL}${NC}"
fi
echo -e ""
echo -e "  ${BOLD}Logs:${NC}  ${LOG_DIR}/"
echo -e "  ${YELLOW}Press Ctrl+C to stop all services.${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

wait

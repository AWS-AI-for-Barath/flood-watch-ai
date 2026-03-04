#!/usr/bin/env bash
# ============================================================
# FloodWatch Phase 4 — OSRM EC2 Bootstrap Script
#
# Installs and configures the OSRM backend on an Ubuntu EC2
# instance (t3.small or larger).
#
# Usage:
#   chmod +x ec2_setup.sh
#   sudo ./ec2_setup.sh
# ============================================================

set -euo pipefail

REGION="india"
PBF_URL="https://download.geofabrik.de/asia/india-latest.osm.pbf"
OSRM_PORT=5000
DATA_DIR="/opt/osrm"
PROFILE_DIR="$(dirname "$0")"

echo "======================================="
echo "  FloodWatch — OSRM EC2 Setup"
echo "======================================="

# ── 1. System dependencies ──────────────────────────────────
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    build-essential cmake pkg-config \
    libbz2-dev libstxxl-dev libstxxl1v5 \
    libxml2-dev libzip-dev libboost-all-dev \
    lua5.4 liblua5.4-dev libluabind-dev \
    libtbb-dev wget curl git

# ── 2. Install OSRM backend ─────────────────────────────────
echo "[2/6] Building OSRM backend..."
if [ ! -d "/opt/osrm-backend" ]; then
    cd /opt
    git clone --depth 1 https://github.com/Project-OSRM/osrm-backend.git
    cd osrm-backend
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    cmake --build . -- -j$(nproc)
    cmake --build . --target install
else
    echo "  OSRM backend already installed, skipping."
fi

# ── 3. Download OSM data ────────────────────────────────────
echo "[3/6] Downloading OSM data for ${REGION}..."
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

if [ ! -f "${REGION}-latest.osm.pbf" ]; then
    wget -q --show-progress "$PBF_URL" -O "${REGION}-latest.osm.pbf"
else
    echo "  PBF file already exists, skipping download."
fi

# ── 4. Copy custom Lua profile ──────────────────────────────
echo "[4/6] Installing custom flood-aware routing profile..."
cp "${PROFILE_DIR}/flood_profile.lua" "$DATA_DIR/" 2>/dev/null || \
    cp /opt/osrm-backend/profiles/car.lua "$DATA_DIR/flood_profile.lua"

# ── 5. Extract and contract ─────────────────────────────────
echo "[5/6] Processing OSM data (extract + contract)..."
cd "$DATA_DIR"
osrm-extract -p flood_profile.lua "${REGION}-latest.osm.pbf"
osrm-contract "${REGION}-latest.osrm"
echo "  Extraction and contraction complete."

# ── 6. Start OSRM backend ──────────────────────────────────
echo "[6/6] Starting OSRM backend on port ${OSRM_PORT}..."

# Create systemd service
cat > /etc/systemd/system/osrm.service << EOF
[Unit]
Description=OSRM Routing Engine
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/osrm-routed \
    --algorithm=CH \
    --port=${OSRM_PORT} \
    ${DATA_DIR}/${REGION}-latest.osrm
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable osrm
systemctl start osrm

echo ""
echo "======================================="
echo "  OSRM Setup Complete"
echo "======================================="
echo "  Endpoint: http://localhost:${OSRM_PORT}"
echo "  Test:     curl 'http://localhost:${OSRM_PORT}/route/v1/driving/80.27,13.08;80.22,12.95?overview=false'"
echo ""

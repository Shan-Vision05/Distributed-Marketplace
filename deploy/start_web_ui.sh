#!/bin/bash
# Start Marketplace Web UI

cd "$(dirname "$0")"/.. || exit

echo "Starting Marketplace Web UI on port 7010..."
python3 -m webui.app

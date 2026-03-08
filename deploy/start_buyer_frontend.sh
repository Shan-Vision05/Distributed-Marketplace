#!/bin/bash
# Start Buyer Frontend Service

cd "$(dirname "$0")"/.. || exit

echo "Starting Buyer Frontend on port 7003..."
python3 -m frontend.buyer_frontend

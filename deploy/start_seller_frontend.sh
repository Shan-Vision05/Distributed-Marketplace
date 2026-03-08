#!/bin/bash
# Start Seller Frontend Service

cd "$(dirname "$0")"/.. || exit

echo "Starting Seller Frontend on port 7004..."
python3 -m frontend.seller_frontend

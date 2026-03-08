#!/bin/bash
# Start Financial Transaction Service

cd "$(dirname "$0")"/.. || exit

echo "Starting Financial Service on port 7005..."
python3 -m services.financial_service

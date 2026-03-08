#!/bin/bash
# Start Product Database Service

cd "$(dirname "$0")"/.. || exit

rm -f backend/product.db

echo "Starting Product Database on port 7002..."
python3 -m backend.product_db

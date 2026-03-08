#!/bin/bash
# Start Customer Database Service

cd "$(dirname "$0")"/.. || exit

rm -f backend/customer.db

echo "Starting Customer Database on port 7001..."
python3 -m backend.customer_db

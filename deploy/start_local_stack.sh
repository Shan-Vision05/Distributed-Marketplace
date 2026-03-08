#!/bin/bash
# Start the full marketplace stack locally, each service in a separate process.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
LOG_DIR="$ROOT_DIR/deploy/logs"
mkdir -p "$LOG_DIR"

cd "$ROOT_DIR"

declare -a PIDS=()

cleanup() {
    if [[ ${#PIDS[@]} -gt 0 ]]; then
        echo
        echo "Stopping local marketplace stack..."
        kill "${PIDS[@]}" 2>/dev/null || true
        wait "${PIDS[@]}" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

start_service() {
    local name="$1"
    local script_path="$2"
    local log_path="$LOG_DIR/${name}.log"

    echo "Starting ${name}..."
    bash "$script_path" >"$log_path" 2>&1 &
    local pid=$!
    PIDS+=("$pid")
    echo "  PID ${pid} | log: $log_path"
    sleep 1
}

start_service "customer_db" "$ROOT_DIR/deploy/start_customer_db.sh"
start_service "product_db" "$ROOT_DIR/deploy/start_product_db.sh"
start_service "financial_service" "$ROOT_DIR/deploy/start_financial_service.sh"
start_service "seller_frontend" "$ROOT_DIR/deploy/start_seller_frontend.sh"
start_service "buyer_frontend" "$ROOT_DIR/deploy/start_buyer_frontend.sh"
start_service "web_ui" "$ROOT_DIR/deploy/start_web_ui.sh"

echo
echo "Local marketplace stack is running."
echo "Buyer frontend:   http://127.0.0.1:7003"
echo "Seller frontend:  http://127.0.0.1:7004"
echo "Financial svc:    http://127.0.0.1:7005/?wsdl"
echo "Web UI:           http://127.0.0.1:7010"
echo
echo "Press Ctrl+C to stop all processes."

wait
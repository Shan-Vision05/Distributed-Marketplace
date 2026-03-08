# Deployment Scripts

This directory contains shell scripts to start each server component.

## Prerequisites

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure you're in the project root directory when running these scripts.

## Starting Services

Run each script in a separate terminal or VM:

### Backend Services
```bash
./deploy/start_customer_db.sh 
./deploy/start_product_db.sh 
```

### Frontend Services
```bash
./deploy/start_seller_frontend.sh
./deploy/start_buyer_frontend.sh
./deploy/start_web_ui.sh
```

### Financial Service
```bash
./deploy/start_financial_service.sh
```

## Web UI

The web UI runs separately from the buyer and seller REST frontends and proxies browser requests to them.

Default UI URL:

```text
http://127.0.0.1:7010
```

Optional environment variables:

```bash
export BUYER_FRONTEND_URL=http://127.0.0.1:7003
export SELLER_FRONTEND_URL=http://127.0.0.1:7004
export WEBUI_PORT=7010
```

## Start everything locally

To run the full stack on `127.0.0.1` with each service in its own process:

```bash
./deploy/start_local_stack.sh
```

This launcher starts all backend, frontend, financial, and UI services and writes logs to `deploy/logs/`.

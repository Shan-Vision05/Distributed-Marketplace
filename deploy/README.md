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
```

### Financial Service
```bash
./deploy/start_financial_service.sh
```

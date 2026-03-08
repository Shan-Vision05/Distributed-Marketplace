# Programming Assignment 2

## System Design

This is an online marketplace system with seven components: Buyer CLI, Seller CLI, Buyer Frontend Server, Seller Frontend Server, Customer DB, Product DB, and Financial Transaction Service. Each component runs independently as a separate process on different VMs in the cloud(except Financial Transaction, which runs on buyer VM). The system uses anarchitecture with RESTful HTTP for client-frontend communication (using FastAPI and `requests`), gRPC for frontend-backend database communication (using Protocol Buffers defined in `marketplace.proto`), and SOAP/WSDL for financial service integration (using `spyne` server and `zeep` client). 

Frontend servers are stateless all persistent state is stored in backend SQLite databases with WAL mode for concurrent access. Sessions are validated on every request via gRPC calls to the Customer DB. The Financial Transaction Service does payment processing with 90% approval and 10% decline rate for valid requests.

## Assumptions and Limitations

- Financial Transaction Service uses a simple SOAP prototype that randomly approves 90% and declines 10% of valid payment requests
- Sessions expire after 5 minutes of inactivity
- Keywords are normalized to lowercase, truncated to 8 characters, and limited to 5 per item
- The system is designed for separate VM deployment and cannot run a single machine without changing the IP addresses to local host
- Financial Service runs on the same VM as Buyer Frontend (allowed sa per requirements)
- Database files are recreated on each service restart for fresh testing

## Current State

**What Works:**
- All RESTful APIs for buyers and sellers (create account, login, logout, item management, cart operations, search, purchase, feedback)
- Complete MakePurchase implementation with credit card validation and SOAP-based financial service integration
- gRPC communication between all frontend and backend servers
- Stateless frontend design with session management via backend
- Concurrent request handling with proper connection pooling and thread management
- Search functionality with keyword matching and ranking
- Performance evaluation across three scenarios (1+1, 10+10, 100+100 concurrent clients)

**Limitations:**
- System saturates at ~200 concurrent clients (Scenario 3) with significant latency increase


## Deployment

Automated deployment scripts are provided in the `deploy/` folder. These scripts automatically navigate to the project root and can be run from any directory:

```bash
./deploy/start_customer_db.sh       # Starts Customer DB (port 7001) - removes old DB first
./deploy/start_product_db.sh        # Starts Product DB (port 7002) - removes old DB first
./deploy/start_financial_service.sh # Starts Financial Service (port 7005)
./deploy/start_seller_frontend.sh   # Starts Seller Frontend (port 7004)
./deploy/start_buyer_frontend.sh    # Starts Buyer Frontend (port 7003)
```

See `deploy/README.md` for detailed deployment instructions.

## Installation

Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the System

Note: you will have to update the IP addresses if you are running on your own VMs.

### Using Deployment Scripts

Run each script in a separate VM in this order:

1. Start backend databases:
   ```bash
   ./deploy/start_customer_db.sh
   ./deploy/start_product_db.sh
   ```

2. Start frontend services:
   ```bash
   ./deploy/start_seller_frontend.sh
   ./deploy/start_buyer_frontend.sh
   ./deploy/start_financial_service.sh  # on buyer frontend VM
   ```

3. Run clients:
   ```bash
   python -m client.seller_cli
   python -m client.buyer_cli
   ```

## Performance Evaluation

Run the evaluation script to measure system performance:

```bash
python -m evaluate
```

This runs three scenarios (1+1, 10+10, 100+100 concurrent clients) with 1000 operations per client across 3 runs. Results are documented in `PerformanceReport.md`.

## API Overview

**Seller APIs**: CreateAccount, Login, Logout, RegisterItemForSale, ChangeItemPrice, UpdateUnitsForSale, DisplayItemsForSale, GetSellerRating

**Buyer APIs**: CreateAccount, Login, Logout, SearchItems, GetItem, AddItemToCart, RemoveFromCart, GetCart, ClearCart, SaveCart, MakePurchase, GetBuyerPurchases, ProvideFeedback, GetSellerRating

**MakePurchase** validates credit card information (16-digit card number, 3-digit CVV, valid expiration, cardholder name) via SOAP Financial Service, then processes the cart by deducting inventory, recording purchase history, and clearing the cart.

## Search Functionality

Item search filters by category and matches keywords. Results are ranked by:
1. Number of matching keywords
2. Item feedback score (upvotes minus downvotes)
3. Lower price

## Documentation

- `PerformanceReport.md` - Complete performance analysis with metrics for all three scenarios and PA1 vs PA2 comparison
- `deploy/README.md` - Deployment script documentation
- `common/marketplace.proto` - gRPC service definitions

# Performance Report

## Experimental Setup
All seven components (Customer DB, Product DB, Seller Frontend, Buyer Frontend, Financial Transaction Service, and two CLI clients) were executed as independent processes. Cutomer and Product DB, Seller adn Buyer Frontend was executed on different VMs. Financial Transaction was executed on the same VM as buyer VM as it was allowed in the requirements.



The communication architecture for PA2:
- **Client ↔ Frontend**: RESTful HTTP (using FastAPI and `requests` library)
- **Frontend ↔ Backend DBs**: gRPC
- **Frontend ↔ Financial Service**: SOAP/WSDL (using `spyne` server and `zeep` client)
- **Backend Databases**: SQLite with WAL mode for concurrent access

Each experiment consisted of 3 runs. In each run, every client executed 1000 API calls.

The following API calls were used:
- Buyers: GetCart (REST GET → gRPC to Customer DB)
- Sellers: DisplayItemsForSale (REST GET → gRPC to Product DB)

## Metrics
- **Average Response Time**: the time between when the client sends a REST request and when the HTTP response is received.
- **Average Throughput**: total completed operations divided by total execution time.
- **Wall**: Total time it took for an entire run

## Scenarios

### Scenario 1: 1 Buyer + 1 Seller

| Run | Response Time (ms) | Throughput (ops/s) | Wall Time (s) |
|-----|-------------------|--------------------|---------------|
| 1   | 7.52              | 249.56             | 8.0           |
| 2   | 7.45              | 258.57             | 7.7           |
| 3   | 7.36              | 263.33             | 7.6           |

**Average response time: 7.44 ms**
**Average throughput: 257.15 ops/s**

**Observation**: With minimal concurrency, latency is low and we see a stable throughput. Each request goes through the full pipeline( REST -> gRPC), i.e, the client sends an HTTP request to the FastAPI frontend, which then makes a gRPC call to the backend database, and return it. The latency increased compared to PA1 which shows the overhead od HTTP request/response parsing, JSON serialization, gRPC and SQLite queries.

### Scenario 2: 10 Buyers + 10 Sellers

| Run | Response Time (ms) | Throughput (ops/s) | Wall Time (s) |
|-----|-------------------|--------------------|---------------|
| 1   | 29.70             | 643.48             | 31.1          |
| 2   | 29.57             | 643.90             | 31.1          |
| 3   | 29.46             | 665.31             | 30.1          |

**Average response time: 29.58 ms**
**Average throughput: 650.90 ops/s**

**Observation**: With 10 buyer and seller clients, response time increased 4x compared to the 1st scenario, while throughtput increased significantly by about 2.5x. The increase is due to the parallelism of the requests by uvicorn ASGI and gRPC servers. The increase in responce can be accounted with a queuing delays, each request waits longer.

### Scenario 3: 100 Buyers + 100 Sellers

| Run | Response Time (ms) | Throughput (ops/s) | Wall Time (s) |
|-----|-------------------|--------------------|---------------|
| 1   | 1150.69           | 169.78             | 1178.0        |
| 2   | 1145.87           | 163.38             | 1224.2        |
| 3   | 1215.68           | 159.86             | 1251.1        |

**Average response time: 1170.75 ms**
**Average throughput: 164.34 ops/s**

**Observation**: With 100 buyers and sellers, response time becomes very high ( about 157x higher than single client) and throughput decreases compared to Scenario 1 by about about 75%. This is due to severe system saturation. Large number of concurrent HTTp connections overwhelms the uvicorn server, and each request has to wait hoe a very long time in the queue. gRPC server also suffers with 200 clinets.

## Observations Across Scenarios

| Scenario | Clients | Avg Response Time (ms) | Avg Throughput (ops/s) |
|----------|---------|----------------------|----------------------|
| 1        | 1+1     | 7.44                 | 257.15               |
| 2        | 10+10   | 29.57                | 650.90               |
| 3        | 100+100 | 1170.75              | 164.34               |

The system works well from 1 to 10 concurrent clients, throughput increases by ~2.5x as parallelism improves CPU utilization. Response time increases by 4x at this concurrency level, it could be due the overhead of the 20x increase in total operations. However at 100 concurrent clients, the system reaches saturated. Throughput drops by 75% compared to Scenario 2 and falls below even the single-client level, while response times grow by ~157x compared to Scenario 1. 

This indicates that the system goes from underutilization (Scenario 1) to parallelism (Scenario 2) to over-contention (Scenario 3).

## Comparison: PA1 vs PA2

| Metric | PA1 (TCP/JSON) | PA2 (REST/gRPC) | Change |
|--------|----------------|-----------------|--------|
| **Scenario 1 Avg RT** | 0.59 ms | 7.44 ms | 12.6x slower |
| **Scenario 1 Avg TP** | 3,364 ops/s | 257.15 ops/s | 13.1x lower |
| **Scenario 2 Avg RT** | 4.49 ms | 29.57 ms | 6.6x slower |
| **Scenario 2 Avg TP** | 4,428 ops/s | 650.90 ops/s | 6.8x lower |
| **Scenario 3 Avg RT** | 50.65 ms | 1170.75 ms | 23.1x slower |
| **Scenario 3 Avg TP** | 3,919 ops/s | 164.34 ops/s | 23.8x lower |

**Explanation of differences**:

PA2 performance changes significantly in different scenarios compared to PA1. At low concurrency (Scenario 1), PA2 is ~13x slower. In Scenario 2, the gap reduces to ~7x slower. However, at high concurrency (Scenario 3), PA2 degrades severely and is ~23x slower, indicating way earlier saturation than PA1's simpler architecture.

These differences are expected given the following changes:

1. **Protocol overhead**: PA1 used raw TCP sockets with a simple protocol (4-byte header + JSON body). PA2 uses HTTP/REST for client-frontend communication, which adds HTTP headers, URL parsing, and the full HTTP request/response cycle. Each REST call involves significantly more bytes and parsing compared to the raw TCP protocol.

2. **Additional serialization layers**: In PA2, every request goes through multiple serialization steps: JSON (REST) → Protobuf (gRPC) → SQLite → Protobuf → JSON. In PA1, it was just JSON → in-memory dict → JSON over a single TCP connection.

3. **Framework overhead**: FastAPI/uvicorn adds routing, request validation, and async event loop overhead that raw TCP socket handling in PA1 did not have. Similarly, gRPC adds its own connection management and protobuf serialization overhead.

4. **Persistence**: PA1 stored all data in-memory Python dictionaries. PA2 uses SQLite databases with WAL mode, which adds disk I/O and locking overhead.

Despite the raw performance cost, the PA2 architecture provides significant advantages, RESTful APIs, gRPC contracts and persistent storage which works well in a production distributed system.

## Evaluation Results

![Evaluation Results](image.png)
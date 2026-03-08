import time
import threading
import concurrent.futures
import requests
from common.rest_client import RESTClient

CALLS_PER_CLIENT = 1000
NUM_RUNS = 3
BUYER_HOST = '34.71.160.216'
BUYER_PORT = 7003
SELLER_HOST = '136.115.93.27'
SELLER_PORT = 7004


def _create_account(role, idx):
    host = BUYER_HOST if role == "buyer" else SELLER_HOST
    port = BUYER_PORT if role == "buyer" else SELLER_PORT
    username = f"perf_{role}_{idx}"
    try:
        requests.post(
            f"http://{host}:{port}/{role}/account",
            json={"username": username, "password": "pass"}, timeout=30,
        )
    except Exception:
        pass


def _create_accounts_parallel(role, count):
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 50)) as pool:
        list(pool.map(lambda i: _create_account(role, i), range(count)))


def _login(role, idx):
    host = BUYER_HOST if role == "buyer" else SELLER_HOST
    port = BUYER_PORT if role == "buyer" else SELLER_PORT
    username = f"perf_{role}_{idx}"
    resp = requests.post(
        f"http://{host}:{port}/{role}/login",
        json={"username": username, "password": "pass"}, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Login failed for {username}: {data}")
    return data["session_id"]


def _login_parallel(role, count):
    results = [None] * count
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 50)) as pool:
        futures = {pool.submit(_login, role, i): i for i in range(count)}
        for f in concurrent.futures.as_completed(futures):
            i = futures[f]
            results[i] = f.result()
    return results


def buyer_op(client, session_id):
    return client.get("buyer/cart", params={"session_id": session_id})


def seller_op(client, session_id):
    return client.get("seller/items", params={"session_id": session_id})


def client_worker(role, session_id, latencies):
    host = BUYER_HOST if role == "buyer" else SELLER_HOST
    port = BUYER_PORT if role == "buyer" else SELLER_PORT
    op = buyer_op if role == "buyer" else seller_op

    client = RESTClient(host, port, timeout=60, pool_connections=1, pool_maxsize=1)

    for _ in range(CALLS_PER_CLIENT):
        start = time.perf_counter()
        resp = op(client, session_id)
        end = time.perf_counter()

        if resp is not None:
            latencies.append(end - start)

    client.close()


def run_once(num_buyers, num_sellers, buyer_sessions, seller_sessions):
    latencies = []
    threads = []

    start_time = time.perf_counter()

    for i in range(num_buyers):
        t = threading.Thread(
            target=client_worker,
            args=("buyer", buyer_sessions[i], latencies)
        )
        t.start()
        threads.append(t)

    for i in range(num_sellers):
        t = threading.Thread(
            target=client_worker,
            args=("seller", seller_sessions[i], latencies)
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    end_time = time.perf_counter()

    total_ops = len(latencies)
    avg_latency = sum(latencies) / total_ops if total_ops else 0
    throughput = total_ops / (end_time - start_time)
    wall_time = end_time - start_time

    return avg_latency, throughput, wall_time


def run_scenario(num_buyers, num_sellers):
    print(f"\n{'='*60}")
    print(f"Scenario: {num_buyers} buyer(s) + {num_sellers} seller(s)")
    print(f"  {CALLS_PER_CLIENT} calls/client × {num_buyers + num_sellers} clients "
          f"= {CALLS_PER_CLIENT * (num_buyers + num_sellers)} total ops per run")
    print(f"  {NUM_RUNS} runs")
    print(f"{'='*60}")

    print("Creating accounts...", end=" ", flush=True)
    t0 = time.perf_counter()
    _create_accounts_parallel("buyer", num_buyers)
    _create_accounts_parallel("seller", num_sellers)
    print(f"done ({time.perf_counter()-t0:.1f}s)")

    rts, tps = [], []

    for i in range(NUM_RUNS):
        buyer_sessions = _login_parallel("buyer", num_buyers)
        seller_sessions = _login_parallel("seller", num_sellers)

        rt, tp, wall = run_once(num_buyers, num_sellers,
                                buyer_sessions, seller_sessions)
        rts.append(rt)
        tps.append(tp)
        print(f"  Run {i+1:2d}/{NUM_RUNS}: "
              f"avg_rt={rt*1000:8.2f} ms  "
              f"throughput={tp:8.2f} ops/s  "
              f"wall={wall:6.1f}s")

    avg_rt = sum(rts) / len(rts)
    avg_tp = sum(tps) / len(tps)
    print(f"\n  >>> Average response time : {avg_rt*1000:.2f} ms")
    print(f"  >>> Average throughput    : {avg_tp:.2f} ops/s")

    return avg_rt, avg_tp


def main():
    scenarios = [
        (1, 1),
        (10, 10),
        (100, 100),
    ]

    results = []
    for b, s in scenarios:
        avg_rt, avg_tp = run_scenario(b, s)
        results.append((b, s, avg_rt, avg_tp))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'Scenario':<20} {'Avg RT (ms)':>12} {'Avg Throughput (ops/s)':>22}")
    print("-" * 56)
    for b, s, rt, tp in results:
        label = f"{b}B + {s}S"
        print(f"{label:<20} {rt*1000:>12.2f} {tp:>22.2f}")


if __name__ == "__main__":
    main()
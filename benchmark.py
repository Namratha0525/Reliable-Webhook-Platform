"""Measure delivery throughput and latency with a healthy demo receiver."""
import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx

from smoke import API


def benchmark(count, concurrency):
    latencies = []
    run_id = uuid4()
    with httpx.Client(timeout=10, trust_env=False) as client:
        def submit(index):
            start = time.monotonic()
            response = client.post(
                f"{API}/events",
                headers={"Idempotency-Key": f"{run_id}-{index}"},
                json={"event_type": "benchmark.event", "payload": {"index": index}},
            )
            return response.raise_for_status().json()["delivery_id"], start

        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            pending = dict(pool.map(submit, range(count)))
        deadline = time.monotonic() + 60
        while pending and time.monotonic() < deadline:
            for delivery_id, submitted_at in list(pending.items()):
                delivery = client.get(
                    f"{API}/deliveries/{delivery_id}"
                ).raise_for_status().json()
                if delivery["status"] == "delivered":
                    latencies.append(time.monotonic() - submitted_at)
                    del pending[delivery_id]
                elif delivery["status"] == "failed":
                    del pending[delivery_id]
            if pending:
                time.sleep(0.1)

    elapsed = time.monotonic() - start
    print(f"Delivered {len(latencies)}/{count} ({len(latencies) / count:.1%})")
    print(f"Observed throughput: {len(latencies) / elapsed:.2f} deliveries/s")
    if latencies:
        p95 = sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1]
        print(f"Observed p95 delivery latency: {p95 * 1000:.0f} ms")
    return len(latencies) == count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    if args.events < 1 or args.concurrency < 1:
        parser.error("events and concurrency must be positive")
    raise SystemExit(0 if benchmark(args.events, args.concurrency) else 1)

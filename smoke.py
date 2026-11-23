"""Run with Docker Compose exec api python smoke.py."""
import time
from uuid import uuid4

import httpx

API = "http://localhost:8000"
RECEIVER = "http://receiver:8001"


def wait_for(client, delivery_url, status):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        delivery = client.get(delivery_url).raise_for_status().json()
        if delivery["status"] == status:
            return delivery
        time.sleep(0.25)
    raise AssertionError(f"Expected {status}; last state was {delivery}")


def main():
    with httpx.Client(trust_env=False) as client:
        client.put(f"{RECEIVER}/mode", json={"unavailable": True}).raise_for_status()
        try:
            headers = {"Idempotency-Key": str(uuid4())}
            payload = {"event_type": "order.created", "payload": {"order_id": 42}}
            response = client.post(f"{API}/events", headers=headers, json=payload)
            assert response.status_code == 202, response.text
            event = response.json()
            repeated = client.post(f"{API}/events", headers=headers, json=payload)
            assert repeated.raise_for_status().json() == event
            changed = client.post(
                f"{API}/events", headers=headers, json={**payload, "payload": {}}
            )
            assert changed.status_code == 409
            url = f"{API}/deliveries/{event['delivery_id']}"
            failed = wait_for(client, url, "failed")
            assert [row["http_status"] for row in failed["history"]] == [503] * 4
        finally:
            client.put(f"{RECEIVER}/mode", json={"unavailable": False}).raise_for_status()

        client.post(f"{url}/replay").raise_for_status()
        recovered = wait_for(client, url, "delivered")
        assert recovered["attempts"] == 5
        assert recovered["history"][-1]["http_status"] == 204
        assert event["event_id"] in client.get(f"{RECEIVER}/received").json()["event_ids"]
        print("Idempotency, conflicting payloads, retries, history and replay passed.")


if __name__ == "__main__":
    main()

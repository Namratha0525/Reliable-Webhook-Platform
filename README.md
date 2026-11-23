# Reliable Webhook Delivery Platform

A FastAPI service accepts and persists events that a PostgreSQL-backed worker delivers to a configured HTTP receiver. The included receiver can simulate an outage.

## Run the demo

From this directory, with Docker and Docker Compose installed:

```sh
docker compose up --build -d
docker compose exec api python smoke.py
docker compose exec api python benchmark.py --events 50 --concurrency 5
docker compose down
```

Open http://localhost:8000/docs to send an event or inspect a delivery interactively. For `POST /events`, supply an `Idempotency-Key` and a body such as `{"event_type":"order.created","payload":{"order_id":42}}`. Copy the returned `delivery_id` into `GET /deliveries/{delivery_id}`.

The smoke test configures the receiver to return HTTP 503, submits the same event twice, checks that a changed payload with the same key returns 409, waits for four failed attempts, restores the receiver, and replays the delivery. The benchmark reports delivery success rate, throughput, and p95 latency observed by a polling client. Its latency includes polling overhead.

To see restart recovery, run `docker compose stop worker`, submit a fresh event, and inspect its queued state. Run `docker compose start worker` and check the same delivery again.

## Reliability decisions

- Event and delivery creation happen in one transaction. A unique request key deduplicates concurrent submissions.
- Workers lock a due delivery with `FOR UPDATE SKIP LOCKED`. The transaction commits the attempt history and delivery state together. Retries wait 2, 4, and 8 seconds.
- The sender provides **at-least-once delivery**. If it crashes after the receiver processes an event and before the database commits, the receiver can get the same event again. The demo receiver deduplicates by event ID while its process is running. A production receiver can store processed IDs durably.
- The worker holds one database row lock during the HTTP request. This keeps job recovery simple for the demo and limits how much work one worker can do at once.
- The local demo uses one configured receiver and development credentials. The API and receiver control port bind to localhost in Compose.

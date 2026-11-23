import os
import time

import httpx
import psycopg

from db import connect

RETRY_DELAYS = (2, 4, 8)


def deliver_one(client, receiver_url):
    with connect() as db:
        job = db.execute(
            """
            SELECT d.id, d.attempts, d.replay_start, e.id AS event_id,
                   e.event_type, e.payload
            FROM deliveries d JOIN events e ON e.id = d.event_id
            WHERE d.status = 'queued' AND d.next_at <= now()
            ORDER BY d.next_at, d.id
            LIMIT 1 FOR UPDATE OF d SKIP LOCKED
            """
        ).fetchone()
        if job is None:
            return False

        status_code, error = None, None
        try:
            with client.stream(
                "POST",
                receiver_url,
                json={
                    "id": str(job["event_id"]),
                    "type": job["event_type"],
                    "data": job["payload"],
                },
                headers={"X-Delivery-ID": str(job["id"])},
            ) as response:
                status_code = response.status_code
        except httpx.RequestError as exc:
            error = type(exc).__name__

        number = job["attempts"] + 1
        retry_index = number - job["replay_start"] - 1
        status, delay = "delivered", 0
        if status_code is None or not 200 <= status_code < 300:
            if retry_index < len(RETRY_DELAYS):
                status, delay = "queued", RETRY_DELAYS[retry_index]
            else:
                status = "failed"

        db.execute(
            """
            INSERT INTO attempts (delivery_id, number, http_status, error)
            VALUES (%s, %s, %s, %s)
            """,
            (job["id"], number, status_code, error),
        )
        db.execute(
            """
            UPDATE deliveries SET status = %s, attempts = %s,
                next_at = clock_timestamp() + make_interval(secs => %s),
                finished_at = CASE WHEN %s = 'queued' THEN NULL ELSE clock_timestamp() END
            WHERE id = %s
            """,
            (status, number, delay, status, job["id"]),
        )
        return True


def main():
    receiver_url = os.environ["RECEIVER_URL"]
    with httpx.Client(timeout=3.0, follow_redirects=False, trust_env=False) as client:
        while True:
            try:
                if not deliver_one(client, receiver_url):
                    time.sleep(0.5)
            except psycopg.OperationalError:
                time.sleep(2)


if __name__ == "__main__":
    main()

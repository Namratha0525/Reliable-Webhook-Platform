from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from db import connect

app = FastAPI(title="Webhook Delivery Platform")


class Event(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    payload: dict


@app.post("/events", status_code=202)
def submit(
    event: Event,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=200)],
):
    with connect() as db:
        row = db.execute(
            """
            INSERT INTO events (id, request_key, event_type, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (request_key) DO NOTHING RETURNING id
            """,
            (uuid4(), idempotency_key, event.event_type, Jsonb(event.payload)),
        ).fetchone()
        if row is None:
            original = db.execute(
                """
                SELECT e.id, d.id AS delivery_id,
                       e.event_type = %s AND e.payload = %s AS matches
                FROM events e JOIN deliveries d ON d.event_id = e.id
                WHERE e.request_key = %s
                ORDER BY d.id LIMIT 1
                """,
                (event.event_type, Jsonb(event.payload), idempotency_key),
            ).fetchone()
            if not original["matches"]:
                raise HTTPException(409, "Key already used for a different event")
            return {"event_id": original["id"], "delivery_id": original["delivery_id"]}

        delivery_id = uuid4()
        db.execute(
            "INSERT INTO deliveries (id, event_id) VALUES (%s, %s)",
            (delivery_id, row["id"]),
        )
        return {"event_id": row["id"], "delivery_id": delivery_id}


@app.get("/deliveries/{delivery_id}")
def inspect(delivery_id: UUID):
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        delivery = db.execute(
            "SELECT * FROM deliveries WHERE id = %s", (delivery_id,)
        ).fetchone()
        if delivery is None:
            raise HTTPException(404, "Delivery not found")
        delivery["history"] = db.execute(
            "SELECT * FROM attempts WHERE delivery_id = %s ORDER BY number",
            (delivery_id,),
        ).fetchall()
        return delivery


@app.post("/deliveries/{delivery_id}/replay", status_code=202)
def replay(delivery_id: UUID):
    with connect() as db:
        delivery = db.execute(
            "SELECT status FROM deliveries WHERE id = %s FOR UPDATE",
            (delivery_id,),
        ).fetchone()
        if delivery is None:
            raise HTTPException(404, "Delivery not found")
        if delivery["status"] != "failed":
            raise HTTPException(409, "Only failed deliveries can be replayed")
        db.execute(
            """
            UPDATE deliveries
            SET status = 'queued', finished_at = NULL, next_at = now(),
                replay_start = attempts
            WHERE id = %s
            """,
            (delivery_id,),
        )
        return {"delivery_id": delivery_id}

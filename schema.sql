CREATE TABLE events (
    id uuid PRIMARY KEY,
    request_key text UNIQUE NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE deliveries (
    id uuid PRIMARY KEY,
    event_id uuid NOT NULL REFERENCES events(id),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'delivered', 'failed')),
    next_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    replay_start integer NOT NULL DEFAULT 0
);
CREATE INDEX ready_deliveries ON deliveries (next_at, id) WHERE status = 'queued';
CREATE TABLE attempts (
    delivery_id uuid NOT NULL REFERENCES deliveries(id),
    number integer NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    http_status integer,
    error text,
    PRIMARY KEY (delivery_id, number)
);

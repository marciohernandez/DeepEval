CREATE TABLE evaluation_results (
    id          UUID PRIMARY KEY,
    bot_id      TEXT NOT NULL,
    trace_id    TEXT,
    metric_name TEXT NOT NULL,
    score       FLOAT NOT NULL,
    passed      BOOLEAN NOT NULL,
    threshold   FLOAT NOT NULL,
    reason      TEXT,
    metadata    JSONB DEFAULT '{}',
    org_id      UUID,
    created_at  TIMESTAMPTZ NOT NULL
);

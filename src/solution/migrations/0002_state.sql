-- Durable key-value state for the Playground, C5 checkpoints, and C8 events. Cases live in 0001.
CREATE TABLE solution_state (
    scope text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key)
);

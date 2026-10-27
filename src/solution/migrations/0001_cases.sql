-- C1-3, C5-1: one row for each case and an append-only history of every field write.
CREATE TABLE cases (
    case_id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE case_field_history (
    id bigserial PRIMARY KEY,
    case_id text NOT NULL REFERENCES cases (case_id),
    field text NOT NULL,
    value jsonb,
    version integer NOT NULL,
    author text NOT NULL,
    source text NOT NULL,
    written_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (case_id, field, version)
);

CREATE INDEX case_field_history_case ON case_field_history (case_id, field, version);

-- The current value of each field is its latest version.
CREATE VIEW case_fields AS
    SELECT DISTINCT ON (case_id, field) case_id, field, value, version, author, source, written_at
    FROM case_field_history
    ORDER BY case_id, field, version DESC;

-- A history row is never changed or removed.
CREATE FUNCTION case_field_history_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'case_field_history is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER case_field_history_no_change
    BEFORE UPDATE OR DELETE ON case_field_history
    FOR EACH ROW EXECUTE FUNCTION case_field_history_is_append_only();

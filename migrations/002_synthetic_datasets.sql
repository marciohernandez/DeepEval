-- M4.1 Synthetic Dataset Generator schema: aggregate root + two child tables.
-- org_id remains nullable on every table for constitution multi-tenant readiness
-- (day-one column, RLS denies null-org rows rather than granting anonymous access).

CREATE TABLE synthetic_datasets (
    id UUID PRIMARY KEY,
    bot_id TEXT NOT NULL,
    org_id UUID,
    personas JSONB NOT NULL DEFAULT '[]',
    source_documents JSONB NOT NULL DEFAULT '[]',
    document_failures JSONB NOT NULL DEFAULT '[]',
    indexing_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE synthetic_goldens (
    id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES synthetic_datasets(id) ON DELETE CASCADE,
    org_id UUID,
    persona_name TEXT NOT NULL,
    input TEXT NOT NULL,
    expected_output TEXT,
    context JSONB NOT NULL DEFAULT '[]',
    source_file TEXT NOT NULL
);

CREATE TABLE synthetic_conversations (
    id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES synthetic_datasets(id) ON DELETE CASCADE,
    org_id UUID,
    persona_name TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    turns JSONB NOT NULL DEFAULT '[]',
    ending_status TEXT NOT NULL,
    bot_error JSONB
);

-- Indexes -------------------------------------------------------------------

CREATE INDEX idx_synthetic_datasets_org_id ON synthetic_datasets (org_id);
CREATE INDEX idx_synthetic_datasets_bot_id ON synthetic_datasets (bot_id);
CREATE INDEX idx_synthetic_datasets_indexing_status ON synthetic_datasets (indexing_status);

CREATE INDEX idx_synthetic_goldens_org_id ON synthetic_goldens (org_id);
CREATE INDEX idx_synthetic_goldens_dataset_id ON synthetic_goldens (dataset_id);

CREATE INDEX idx_synthetic_conversations_org_id ON synthetic_conversations (org_id);
CREATE INDEX idx_synthetic_conversations_dataset_id ON synthetic_conversations (dataset_id);

-- Child org-id inheritance ----------------------------------------------------
-- Child rows must copy the parent dataset's org_id. An explicitly different
-- caller-supplied value is rejected rather than silently overwritten.

CREATE OR REPLACE FUNCTION synthetic_child_inherit_org_id()
RETURNS TRIGGER AS $$
DECLARE
    parent_org_id UUID;
BEGIN
    SELECT org_id INTO parent_org_id
    FROM synthetic_datasets
    WHERE id = NEW.dataset_id;

    IF NEW.org_id IS NOT NULL AND NEW.org_id IS DISTINCT FROM parent_org_id THEN
        RAISE EXCEPTION
            'org_id mismatch: child org_id % does not match parent dataset org_id %',
            NEW.org_id, parent_org_id;
    END IF;

    NEW.org_id := parent_org_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER synthetic_goldens_org_inherit
    BEFORE INSERT ON synthetic_goldens
    FOR EACH ROW EXECUTE FUNCTION synthetic_child_inherit_org_id();

CREATE TRIGGER synthetic_conversations_org_inherit
    BEFORE INSERT ON synthetic_conversations
    FOR EACH ROW EXECUTE FUNCTION synthetic_child_inherit_org_id();

-- Row Level Security ----------------------------------------------------------
-- No DELETE policy is added: the repository exposes no delete method, so
-- child-row cleanup relies solely on ON DELETE CASCADE from a parent
-- synthetic_datasets deletion performed outside application scope.

ALTER TABLE synthetic_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE synthetic_goldens ENABLE ROW LEVEL SECURITY;
ALTER TABLE synthetic_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY synthetic_datasets_select ON synthetic_datasets
    FOR SELECT
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_datasets_insert ON synthetic_datasets
    FOR INSERT
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_datasets_update ON synthetic_datasets
    FOR UPDATE
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id)
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_goldens_select ON synthetic_goldens
    FOR SELECT
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_goldens_insert ON synthetic_goldens
    FOR INSERT
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_goldens_update ON synthetic_goldens
    FOR UPDATE
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id)
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_conversations_select ON synthetic_conversations
    FOR SELECT
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_conversations_insert ON synthetic_conversations
    FOR INSERT
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

CREATE POLICY synthetic_conversations_update ON synthetic_conversations
    FOR UPDATE
    USING ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id)
    WITH CHECK ((auth.jwt() -> 'app_metadata' ->> 'org_id')::uuid = org_id);

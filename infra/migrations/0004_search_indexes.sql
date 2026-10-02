-- Migration: 0004_search_indexes.sql
-- Creates full-text and ACL indexes for search operations

-- Update chunk text search vector
CREATE OR REPLACE FUNCTION chunk_tsvector_trigger()
RETURNS trigger AS $$
BEGIN
    NEW.tsvector := to_tsvector('english', NEW.text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add tsvector column to chunk table
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS tsvector tsvector;

-- Trigger to keep tsvector in sync
CREATE TRIGGER chunk_tsvector_update
BEFORE INSERT OR UPDATE ON chunk
FOR EACH ROW EXECUTE FUNCTION chunk_tsvector_trigger();

-- Full-text search index on tsvector
CREATE INDEX IF NOT EXISTS idx_chunk_tsvector_gist
ON chunk USING gist (tsvector);

-- ACL predicate function for RLS
CREATE OR REPLACE FUNCTION rsacl(acl_tags text[], policy text[])
RETURNS boolean AS $$
BEGIN
    -- Return true if any of the user's ACL tags match the document's ACL tags
    IF acl_tags IS NULL OR policy IS NULL THEN
        RETURN TRUE;
    END IF;
    RETURN EXISTS(
        SELECT 1
        FROM unnest(policy) AS tag
        WHERE tag = ANY(acl_tags)
    );
END;
$$ LANGUAGE plpgsql;

-- Grant execution of rsacl to public/roles
GRANT EXECUTE ON FUNCTION rsacl TO PUBLIC;
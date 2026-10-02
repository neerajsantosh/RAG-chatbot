-- 0001_baseline
--
-- Phase 1 baseline: infrastructure only. No corpus tables yet -- those arrive in phase 2
-- (`0002_documents_and_chunks.sql`) and the vector indexes in phase 3
-- (`0004_search_indexes.sql`).
--
-- What does exist here is the part that is cheap now and expensive later:
--   * `schema_migration`, so migrations are idempotent and ordered.
--   * RLS policies against tables that do not exist yet are impossible, so instead the
--     policy *functions* are defined here and attached in the phase-2 migration. Defining
--     them once, in one file, is what prevents phase 2 and phase 3 from each inventing
--     their own notion of who may read a document.

CREATE TABLE IF NOT EXISTS schema_migration (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE schema_migration IS
    'Applied migration versions. Managed by storage.db.migrate; do not edit by hand.';


-- ---------------------------------------------------------------------------
-- Access-control predicates
--
-- Read the caller's groups from the session variable set by
-- storage.db.session.bind_principal. A transaction that never bound a principal sees an
-- empty array, so `&&` is false and every restricted row is invisible. Deny by default.
--
-- `current_setting(..., true)` returns NULL when unset rather than raising, which is what
-- keeps a missing binding from turning into a connection error mid-query.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION current_principal_groups()
RETURNS text[]
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        NULLIF(current_setting('app.user_groups', true), ''),
        '{}'
    )::text[];
$$;

COMMENT ON FUNCTION current_principal_groups() IS
    'Groups bound to the current transaction by storage.db.session.bind_principal.';


CREATE OR REPLACE FUNCTION principal_may_read(p_acl_tags text[], p_visibility text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT p_visibility = 'org'
        OR COALESCE(p_acl_tags, '{}') && current_principal_groups();
$$;

COMMENT ON FUNCTION principal_may_read(text[], text) IS
    'True when the bound principal may read a document with these ACL tags. '
    'Org-visible documents are readable by any authenticated principal; restricted ones '
    'require a matching group.';


-- ---------------------------------------------------------------------------
-- Tenancy placeholder
--
-- Excluded from v1 (PRD §3, assumption A3) but reserved now: adding a tenant column after
-- documents exist means migrating every table and auditing every query, whereas adding it
-- while tables are empty costs one column.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION current_tenant()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '');
$$;
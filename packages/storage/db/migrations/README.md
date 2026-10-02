# Migrations

One SQL file per version, applied in filename order inside a transaction, recorded in
`schema_migration`. Run with:

```bash
python -m storage.db.migrate            # apply everything outstanding
python -m storage.db.migrate --status   # show applied and pending versions
```

## Rules

1. **Never edit an applied file.** Add a new one. An applied migration that changes meaning
   makes environments diverge silently, and the divergence is only discovered when two
   environments return different answers to the same query.
2. **Forward only.** No down migrations. Rolling an application back is a supported operation
   (`docs/runbooks/` phase 5); rolling the schema back is not, and a down migration that
   discards data is worse than a manual restore.
3. **Backward compatible with the previous application release.** The pipeline applies
   migrations before rolling out new code, so a rollback must not meet a schema it cannot
   read.
4. **No data migrations without a dry run.** State-changing migrations of existing rows need
   a count of affected rows printed first, so the operator can see the blast radius before
   it happens.

## Current versions

| Version | Phase | Contents |
| --- | --- | --- |
| `0001_baseline` | 1 | `schema_migration`, access-control predicate functions, tenancy placeholder |
| `0002_documents_and_chunks` | 2 | `source`, `document`, `chunk` (phase 2) |
| `0003_vector_extension` | 3 | Vector extension and column type (phase 3) |
| `0004_search_indexes` | 3 | HNSW, full-text and ACL indexes (phase 3) |
| `0005_row_level_security` | 4 | RLS policies attached to `document` and `chunk` (phase 4) |
| `0006_trace_tables` | 4 | `conversation`, `message`, `trace` (phase 4) |

## Note on the split

RLS policies land in phase 4 rather than alongside the tables in phase 2. That is a
deliberate sequencing choice, not an oversight: it means phase 2 can build and test
ingestion with a simple ACL predicate in the query, and phase 4 then adds the safety net
*underneath* that predicate and proves, with a test that omits the predicate, that the net
holds. Attaching RLS from the start would make every phase-2 query fail confusingly while
the session-binding mechanism was still settling.

The predicate functions are defined in `0001` so that both phases agree on what "may read"
means.
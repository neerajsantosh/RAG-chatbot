# Implementation Plan — RAG Chatbot

| Field | Value |
| --- | --- |
| Document status | Draft (v0.1) |
| Owner | TBD |
| Last updated | 2026-10-02 |
| Derived from | [`architecture.md`](./architecture.md) v0.1, [`PRD.md`](./PRD.md) v0.1 |
| Method | Six sequential phases. Each phase ends with a verification gate that must pass before work starts on the next. |

> **No code in this document.** This is a plan: what gets built, in what order, and — most
> importantly — how you prove each phase works *before* you build on top of it. No source,
> SQL, or configuration contents appear here. Files are listed by path and responsibility only.
>
> **Inherited uncertainty.** `docs/problemstatement.txt` was empty, so the PRD was reconstructed.
> Assumptions `A1`–`A12`, open questions `OQ-1`–`OQ-12` (PRD §12/§14) and architecture
> questions `AQ-1`–`AQ-10` (architecture.md §22) still stand. See [§9](#9-open-questions-that-block-phases)
> for which of them block which phase — several must be answered *before* the phase that needs
> them starts.

---

## Table of contents

1. [How to use this plan](#1-how-to-use-this-plan)
2. [Phase overview](#2-phase-overview)
3. [Phase 1 — Project setup](#3-phase-1--project-setup)
4. [Phase 2 — Loading & chunking](#4-phase-2--loading--chunking)
5. [Phase 3 — Embedding & vector store](#5-phase-3--embedding--vector-store)
6. [Phase 4 — Guardrails](#6-phase-4--guardrails)
7. [Phase 5 — Retrieval + LLM answer](#7-phase-5--retrieval--llm-answer)
8. [Phase 6 — UI](#8-phase-6--ui)
9. [Open questions that block phases](#9-open-questions-that-block-phases)
10. [Cross-cutting concerns](#10-cross-cutting-concerns)
11. [Requirement coverage by phase](#11-requirement-coverage-by-phase)
12. [Deliberately not built in these six phases](#12-deliberately-not-built-in-these-six-phases)
13. [Verification tooling summary](#13-verification-tooling-summary)

---

## 1. How to use this plan

### 1.1 The gate discipline

Each phase ends with a **gate**: a short list of checks that must pass before the next phase
starts. The gate is the point of the plan.

The failure this prevents: a system that is 90% built, answers questions with ungrounded
results, has no way to tell whether a change helped, and has leaked a document that a user
should not have seen. Every hard-won insight in RAG comes from measuring retrieval quality on
a labelled set *before* building generation on top of it — which is why phases 2 and 3 come
before phase 5, and why phase 4 comes before phase 5.

### 1.2 Rules for every phase

1. **No source code in this document.** Implement from the architecture, not from a plan that
   guesses at implementation.
2. **A phase is not done until its gate passes on a clean checkout and a fresh database.**
   Not on your laptop with leftover state.
3. **Measure, then optimise.** No tuning decision without an eval number behind it.
4. **If a gate cannot be verified, it is not implemented.** Say so; do not mark it done.
5. **Keep the ports stable.** The interfaces from architecture.md §12 and §21 are contracts
   across phases. Changing one mid-plan invalidates work in later phases.

### 1.3 What "verify" means here

Each phase's verification section is written to be executable by someone who did not write the
code. Prefer, in order: automated check → repeatable script → printed report → manual
inspection of raw data. Manual inspection is acceptable in phases 2 and 3 (where you are
establishing what is even true about your corpus) and inadequate in phase 5 (where quality
must be regression-guarded).

---

## 2. Phase overview

| Phase | Delivers | Primary requirement families | Gate headline |
| --- | --- | --- | --- |
| **1. Project setup** | Running skeleton: services wired, ports defined, CI green, eval harness runs on an empty index | FR-29, FR-32, NFR-18, NFR-20 | `healthz` returns 200 from a fresh clone; eval harness runs and reports zeros without crashing |
| **2. Loading & chunking** | Corpus ingested into parsed, chunked, versioned, ACL-tagged text with a small labelled question set | FR-1, FR-2, FR-3, FR-4, FR-5 | Re-running ingestion changes nothing; 20 sampled chunks are coherent and citable |
| **3. Embedding & vector store** | Chunks embedded and indexed; dense + lexical search with ACL filtering; per-retriever Recall@k measured | FR-7, FR-8, NFR-5/6 | Dense and lexical Recall@5 reported separately; no cross-group leakage via SQL or RLS |
| **4. Guardrails** | Access control hardened, content treated as untrusted, secrets/logging/rate limits/config versioning/red-team harness | FR-29, FR-38, FR-39, FR-40, FR-41, FR-42, FR-43, NFR-14–17 | Unauthorized retrieval fails closed on every path tried; deliberate log of a question fails CI |
| **5. Retrieval + LLM answer** | End-to-end grounded answers with verified citations, refusal path, streaming, traces, cost, release gates | FR-9–FR-19, FR-24, FR-31, FR-33, NFR-1–3, NFR-10, NFR-12 | Golden set ≥90% grounded, ≤5% unsupported; red-team ≤2%; TTFT within budget; regression gate blocks a bad prompt |
| **6. UI** | Chat surface with citation→passage provenance, refusal UX, feedback, admin console, accessibility | FR-20–FR-28, FR-30, FR-34, FR-36 | Keyboard-only path completes a question and opens a cited passage; E2E suite green |

### 2.1 Dependency map

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
  setup      parse      embed      safety      answer        surface
             chunk      index      controls    pipeline      + admin
               │           │            │            │
               └─ labelled ─┴─ Recall@k ─┘            └─ release gates
                  question set (grows across phases, ≥200 by phase 5)

Parallelisable once Phase 1 lands (with a reviewer, not alone):
  • Phase 6 chat shell + admin scaffolding  (no backend dependency for layout/a11y)
  • Phase 4 red-team corpus authoring       (content, not code)
  • Golden question-set labelling          (needs a human who knows the corpus)
```

> **De-risking note.** Because the UI is last, phases 2–5 must each be demonstrable **without**
> it. Phase 5 therefore ships a CLI smoke path first; the UI in phase 6 consumes a stable API
> contract and cannot be the thing that reveals a broken pipeline.

### 2.2 Phase-to-milestone mapping

| Phase | PRD milestone | Exit criterion source |
| --- | --- | --- |
| 1 | M0 — Foundation | PRD §11 M0 |
| 2 | M1 — Corpus (part 1) | PRD §11 M1 |
| 3 | M1 — Corpus (part 2) | PRD §11 M1 |
| 4 | M3 — Safe & trustworthy (part 1) | PRD §11 M3 |
| 5 | M2 + M3 (part 2) | PRD §11 M2, M3 |
| 6 | M4 — Pilot-ready UX | PRD §11 M4 |

PRD M5 (hardening, load, runbooks, cost tuning) is distributed across phases 3, 5, and 6 and
is completed by the §10 exit checklist rather than by a separate phase.

---

## 3. Phase 1 — Project setup

### 3.1 Goal

A running skeleton in which every external dependency is already behind a port, the eval
harness executes against an empty index, and CI is green — so that no later phase has to
retrofit a test or an abstraction.

### 3.2 Why this phase exists

Architecture drivers D7 (swappable dependencies) and D9 (every answer explainable) are only
real if they hold from the first commit. Setting up the interfaces, a fake provider, and the
eval harness now costs a day; adding them after three phases of inline provider calls costs a
rewrite.

### 3.3 Files to create

**Repository root**

| Path | Responsibility |
| --- | --- |
| `Makefile` | Single entry point for the verbs used in every phase: bootstrap, run, test, lint, typecheck, eval, migrate, seed, clean. Documented targets |
| `.env.example` | Every configuration key with a placeholder value and a comment. The contract for configuration |
| `.gitignore` | Secrets, local database volumes, build output, `.env` |
| `.editorconfig` | Indentation, trailing whitespace, final newline |
| `.pre-commit-config.yaml` | Format, lint, secret scan, large-file guard |
| `README.md` | Bootstrap instructions, phase-status table, links to PRD/architecture/this plan |

**Local development environment**

| Path | Responsibility |
| --- | --- |
| `docker-compose.yml` | Local stack: Postgres with the vector extension, object store emulator, one API, one worker, one web |
| `docker-compose.override.yml.example` | Pattern for local model-provider configuration without committing keys |
| `infra/containers/Dockerfile.api` | Image build for the API service |
| `infra/containers/Dockerfile.worker` | Image build for the async worker |
| `infra/containers/Dockerfile.web` | Image build for the web app |

**`packages/core`** — no dependencies on any other package

| Path | Responsibility |
| --- | --- |
| `packages/core/__init__.py` | Package marker |
| `packages/core/config/__init__.py` | Settings surface |
| `packages/core/config/settings.py` | Typed, validated settings; reads environment once; fails fast with a clear message on a missing or invalid key |
| `packages/core/config/secrets.py` | Access to the managed secret store; refuses to construct a secret from a literal in source |
| `packages/core/logging/__init__.py` | Logging surface |
| `packages/core/logging/logger.py` | Structured JSON logger |
| `packages/core/logging/redaction.py` | Field allow-list filter enforcing NFR-16 — the mechanism that makes "no content in logs" a code property |
| `packages/core/ids.py` | Correlated ID generation for request, trace, job |
| `packages/core/errors.py` | Typed error taxonomy; retryable vs terminal |
| `packages/core/clock.py` | Injectable time source, so freshness and latency are testable |
| `packages/core/retry.py` | One retry/timeout/backoff decorator reused by every provider call |
| `packages/core/telemetry/__init__.py` | Telemetry surface |
| `packages/core/telemetry/spans.py` | Span creation; required attributes (config version, prompt version, model, tokens, cost) |

**`packages/llm`** — the only place a provider SDK may ever be imported

| Path | Responsibility |
| --- | --- |
| `packages/llm/ports/__init__.py` | Port definitions: `ChatModel`, `Embedder`, `Reranker`, plus capability declarations |
| `packages/llm/ports/capabilities.py` | Capability descriptor: streaming, tool calling, JSON mode, context size — so a weaker model cannot silently change behaviour |
| `packages/llm/adapters/__init__.py` | Adapter surface |
| `packages/llm/adapters/fake_chat.py` | Deterministic offline model: echoes markers, returns fixed shape, records its calls |
| `packages/llm/adapters/fake_embedder.py` | Deterministic embeddings of fixed dimension, so the index and search work with no provider and no cost |
| `packages/llm/adapters/fake_reranker.py` | Deterministic reranker returning a stable ordering |
| `packages/llm/adapters/registry.py` | Resolves a model name from config to an adapter; rejects a name with no adapter rather than falling back silently |
| `packages/llm/pricing.py` | Token-to-cost mapping; cost is computed from actual token counts (D10) |

**`packages/storage`**

| Path | Responsibility |
| --- | --- |
| `packages/storage/db/engine.py` | Connection pool, transaction context, `app.user_groups` session variable setting |
| `packages/storage/db/session.py` | Session lifecycle and retry-on-conflict |
| `packages/storage/db/migrations/` | Versioned migration directory with a `0001_baseline` entry |
| `packages/storage/ports/` | Port definitions: `DocumentRepository`, `ChunkRepository`, `TraceStore`, `ConfigStore`, `ObjectStore` |
| `packages/storage/repositories/` | Implementations; empty or minimal in this phase, schema-driven |
| `packages/storage/rls.py` | Row-level-security enablement and policy management (landed fully in phase 4) |

**`packages/eval`**

| Path | Responsibility |
| --- | --- |
| `packages/eval/harness.py` | Runner: dataset in, metrics out, comparable to a stored baseline |
| `packages/eval/datasets.py` | Dataset loader and schema validation for the labelled question format |
| `packages/eval/metrics/retrieval.py` | Deterministic metrics: Recall@k, hit rate, MRR, nDCG |
| `packages/eval/metrics/generation.py` | Stub for groundedness/citation metrics; raises "not implemented" until phase 5 rather than returning a fake number |
| `packages/eval/judge.py` | Pinned LLM-as-judge stub with a fixed rubric; disabled by default |
| `packages/eval/report.py` | Machine-readable report plus a readable summary table |
| `packages/eval/gate.py` | Regression comparison against `evals/baselines/`; the NFR-12 enforcement point |

**`apps/api`**

| Path | Responsibility |
| --- | --- |
| `apps/api/main.py` | Application assembly, middleware order, router registration |
| `apps/api/health.py` | Liveness and readiness endpoints, including dependency checks |
| `apps/api/middleware/auth.py` | JWT verification; builds the immutable `Principal`; deny by default. IdP is stubbed locally with a fixed dev principal |
| `apps/api/middleware/ratelimit.py` | Skeleton with the hook in place; enforcement lands in phase 4 |
| `apps/api/middleware/request_id.py` | Request correlation |
| `apps/api/deps.py` | Dependency wiring: settings, repositories, ports |
| `apps/api/routes/health.py` | `healthz`, `readyz` |
| `apps/api/routes/conversations.py` | Conversation CRUD, stubs returning empty collections |
| `apps/api/routes/chat.py` | Chat route with the SSE response class in place, emitting only `start` and `done` |
| `apps/api/routes/sources.py` | Source routes, stubs |
| `apps/api/routes/admin.py` | Admin routes, stubs, authz stubbed to deny non-operators |
| `apps/api/routes/traces.py` | Trace routes, stubs |
| `apps/api/routes/feedback.py` | Feedback route, stub |
| `apps/api/tests/` | Test package root |

**`apps/worker`**

| Path | Responsibility |
| --- | --- |
| `apps/worker/main.py` | Worker entrypoint |
| `apps/worker/consumer.py` | Queue consumer skeleton: poll, acknowledge, retry, dead-letter |
| `apps/worker/jobs/` | Empty job module for each job type the architecture defines |

**`apps/web`**

| Path | Responsibility |
| --- | --- |
| `apps/web/package.json`, `tsconfig.json`, `next.config.js` | Web scaffold |
| `apps/web/app/layout.tsx` | Root layout, global styles |
| `apps/web/app/page.tsx` | Placeholder page proving the build and API connectivity |
| `apps/web/lib/api.ts` | Typed API client with a stub for the streaming endpoint |

**Tests and fixtures**

| Path | Responsibility |
| --- | --- |
| `tests/conftest.py` | Shared fixtures: database, migration, settings, fake ports |
| `tests/unit/` | Unit test root |
| `tests/integration/` | Integration test root |
| `tests/fixtures/corpus/` | Two or three tiny documents for wiring tests |
| `tests/fixtures/golden/mini.jsonl` | Five questions with expected document references, enough to prove the dataset schema and harness work |
| `tests/test_dependency_rules.py` | Enforces architecture §21: `apps → packages` only, and no provider SDK outside `packages/llm/adapters` |

**CI and infrastructure**

| Path | Responsibility |
| --- | --- |
| `.github/workflows/ci.yml` | Lint, typecheck, unit and integration tests, dependency-rule check, eval against the mini dataset |
| `.github/workflows/security.yml` | Secret scan, dependency audit, redaction guard |
| `infra/terraform/` | Skeleton modules for the local/prod split; no resources created yet |

**Documentation**

| Path | Responsibility |
| --- | |
| `docs/adr/0001-record-architecture-decisions.md` | ADR convention |
| `docs/adr/0002-postgres-for-vector-and-lexical.md` | Records architecture §20.1 |
| `docs/adr/0003-own-the-rag-pipeline.md` | Records architecture §20.3 (no RAG framework in v1) |
| `docs/adr/0004-stream-with-provisional-citations.md` | Records the FR-14/FR-12 resolution in architecture §6.1 |
| `docs/adr/0005-rls-as-acl-safety-net.md` | Records architecture §10.3 |

### 3.4 What this phase does

1. Creates the monorepo skeleton, container builds, and local stack; a developer reaches a
   running API and web app from a clean clone with one bootstrap command.
2. Defines settings, structured logging with the content-redaction filter, typed errors, the
   retry decorator, and span helpers — the cross-cutting plumbing every later phase uses.
3. Defines the three model ports, their capability descriptors, and deterministic fake
   implementations, so the whole system runs and tests offline with no provider account and
   no cost.
4. Creates the database baseline migration, the repository ports, and the RLS module.
5. Assembles the API with real middleware order (auth → request ID → rate-limit hook) and
   routes whose responses are typed but currently empty.
6. Builds the eval harness and runs it against the empty index, proving it reports zeros
   rather than crashing — the PRD M0 exit criterion.
7. Wires CI to fail on a dependency-rule violation, so the package boundaries are enforced
   from the first commit rather than reviewed by hand.

### 3.5 How to verify it works

**Automated, all must pass on a clean clone:**

| Check | How | Expected |
| --- | --- | --- |
| Bootstrap | Fresh clone, run the bootstrap target, then start the stack | All containers healthy; no manual steps |
| Liveness | Call `healthz` | 200 with a non-empty service identifier |
| Readiness | Call `readyz` | 200 only when the database answers; 503 otherwise (test by stopping the database) |
| Test suite | Run the test target | Green; includes the dependency-rule test |
| Types and lint | Run typecheck and lint targets | Green |
| Eval harness on empty index | Run the eval target against `mini.jsonl` | Exits 0 and reports Recall@k of 0/5 **without** raising — this is the specific M0 criterion |
| Determinism | Run the suite twice | Identical results; no reliance on wall-clock or network |
| Secrets hygiene | Scan the repo for credential patterns | No findings; a deliberately planted fake credential fails the scan |
| Log hygiene | Run a test that logs a field named `question` | The redaction filter strips it; a deliberately unfiltered logger fails the security workflow |
| Boundary enforcement | Add a temporary import of a provider SDK outside `packages/llm/adapters` | Dependency-rule test fails (proves the guard actually guards) |

**Manual:**

- A new developer follows the README from a clean clone to a running app with no verbal help.
  If they get stuck, the README is a phase-1 defect.
- `readyz` returning 503 when the database is down confirms the check is real and not a
  constant `200`.

**Explicitly not verified here:** anything about retrieval or answer quality. There is no
corpus and no model yet. Resisting the urge to "just try a question" now is what keeps phases
2–3 honest.

### 3.6 Gate — all must pass

- [ ] Clean clone reaches a running API and web app via documented commands only
- [ ] `healthz` and `readyz` behave correctly, including the failure case
- [ ] Whole system runs end-to-end on fake adapters with no provider account
- [ ] Eval harness exits 0 against the empty index and the mini dataset
- [ ] Dependency-rule and log-redaction guards demonstrably fail when violated
- [ ] CI green on a branch push
- [ ] ADR records exist for the five architecture decisions in §20 and §8
- [ ] All three ports have at least one fake and one real-adapter slot; no provider SDK imported anywhere else

### 3.7 Risks specific to this phase

| Risk | Response |
| --- | --- |
| Abstracting too early, or too many abstractions | Build exactly three model ports plus five storage ports. Every port must have a second reason to exist beyond "might swap later" |
| Fake adapters leak into production | `registry.py` resolves by explicit config name; a `fake` name is rejected when an environment flag marks the deployment non-local |
| Settings sprawl | One settings object, validated once at startup, with `.env.example` as the contract |
| Skipping the fake adapters to save a day | Then every test from phase 2 onward needs a network call, and CI becomes slow and flaky. This is the one shortcut that costs the most |

---

## 4. Phase 2 — Loading & chunking

### 4.1 Goal

The corpus exists as parsed, structured, versioned, ACL-tagged chunks in storage, ingestion is
idempotent and incremental, and a first small labelled question set exists.

### 4.2 Why this phase exists

Architecture driver D3: retrieval quality dominates perceived quality. Chunking is the
earliest decision that determines retrieval quality, and it must be inspectable and versioned
before embeddings exist. If you cannot read a chunk and judge it, you cannot debug anything
downstream.

### 4.3 Files to create

**`packages/ingest`**

| Path | Responsibility |
| --- | --- |
| `packages/ingest/models.py` | `ParsedDocument`, `DocumentSection`, `Chunk`, `SourceRef` types — the contract between parsing, chunking, and indexing |
| `packages/ingest/pipeline.py` | Orchestration: fetch → parse → ACL extract → chunk → hand off to indexer; per-document error isolation |
| `packages/ingest/connectors/__init__.py` | `Connector` port: enumerate sources, fetch by id, fetch raw bytes |
| `packages/ingest/connectors/local_filesystem.py` | First real connector: a directory of documents |
| `packages/ingest/connectors/http_fetch.py` | Fetch a URL's content; honours size and type limits |
| `packages/ingest/connectors/registry.py` | Resolves a source type from config to a connector |
| `packages/ingest/parsers/__init__.py` | Parser port |
| `packages/ingest/parsers/markdown.py` | Headings, lists, code blocks, links |
| `packages/ingest/parsers/plaintext.py` | Encoding detection, paragraph boundaries |
| `packages/ingest/parsers/html.py` | Strip active content; preserve structure |
| `packages/ingest/parsers/pdf.py` | Text extraction with page references for citation |
| `packages/ingest/parsers/normalizer.py` | Unicode normalisation, whitespace and control-character cleanup, boilerplate removal |
| `packages/ingest/parsers/language.py` | Language detection stored on the document |
| `packages/ingest/chunkers/__init__.py` | `Chunker` port with a `version` attribute |
| `packages/ingest/chunkers/structure_aware.py` | Split on heading hierarchy; carry `heading_path` |
| `packages/ingest/chunkers/fixed_window.py` | Overlapping fixed-size windows for flat text |
| `packages/ingest/chunkers/table_aware.py` | Text rendering of tables plus a link back to the original region |
| `packages/ingest/chunkers/faq.py` | One chunk per question-answer pair |
| `packages/ingest/chunkers/registry.py` | Resolves the strategy from config; exposes the current `chunker_version` |
| `packages/ingest/acl.py` | Derives `acl_tags` from source permissions or per-document config; **fails closed** when permissions cannot be determined |
| `packages/ingest/content_hash.py` | `content_hash` over normalised text + `chunker_version` + embedding-model version string |
| `packages/ingest/injection_scan.py` | Flags instruction-like patterns in chunk text; sets `is_suspicious` |
| `packages/ingest/stats.py` | Chunk statistics report: counts, token distribution, over-budget percentage, per-document breakdown |

**Storage**

| Path | Responsibility |
| --- | --- |
| `packages/storage/repositories/document_repository.py` | Upsert documents; status transitions; tombstone |
| `packages/storage/repositories/chunk_repository.py` | Write chunk sets, flip the active set atomically, tombstone old rows |
| `packages/storage/object_store.py` | Store raw and parsed bytes, versioned and immutable |
| `infra/migrations/0002_documents_and_chunks.sql` | `document`, `chunk` (embedding column nullable until phase 3), `source` tables and indexes |

**Fixtures and tests**

| Path | Responsibility |
| --- | --- |
| `tests/fixtures/corpus/` | Expanded sample corpus: a heading-structured document, a long flat document, a table-heavy document, a duplicate of an earlier document, a near-duplicate, an empty document, a very large document, an HTML document, and one document with no headings at all |
| `tests/fixtures/corpus/restricted/` | Two documents with restrictive ACL tags, used from phase 3 onward |
| `tests/fixtures/golden/seed-v1.jsonl` | First labelled question set: 20–30 questions covering answerable, unanswerable, multi-document, exact-term, and synonym queries, each with the expected document id and, where possible, an expected passage hint |
| `tests/unit/ingest/test_normalizer.py` | Normalisation correctness, including hostile input (null bytes, mixed encodings, control characters) |
| `tests/unit/ingest/test_parsers.py` | Per-format parsing, structure preservation, and no content loss for the sample corpus |
| `tests/unit/ingest/test_chunkers.py` | Chunk boundaries, token budgets, `heading_path` correctness, no truncated-looking chunks without a marker |
| `tests/unit/ingest/test_content_hash.py` | Hash stability; a change to chunker version or normalised text changes the hash |
| `tests/unit/ingest/test_acl.py` | ACL tag derivation and fail-closed behaviour |
| `tests/unit/ingest/test_injection_scan.py` | Injection patterns flagged; benign imperative text not flagged excessively |
| `tests/integration/ingest/test_pipeline_idempotency.py` | Re-running ingestion produces no duplicate chunks |
| `tests/integration/ingest/test_incremental_update.py` | Modify → reindex → only changed chunks rewritten; delete → tombstoned |
| `apps/worker/jobs/ingest_job.py` | The ingestion job consumed from the queue |
| `apps/worker/jobs/reindex_job.py` | Full vs incremental reindex modes |

**Developer tooling**

| Path | Responsibility |
| --- | --- |
| `tools/ingest.py` | CLI: ingest a source, reindex, dump chunks for inspection, print chunk statistics, tombstone a document |
| `tools/inspect_chunks.py` | Reads a document or corpus and prints its chunks with headings and token counts for human review |

**Documentation**

| Path | Responsibility |
| --- | --- |
| `docs/corpus-inventory.md` | What is in the corpus, who owns it, how fresh it is, known gaps |
| `docs/adr/0006-chunking-strategy.md` | Records the chosen strategy and why, with the statistics that informed it |

### 4.4 What this phase does

1. Implements the `Connector` port and two real connectors (local filesystem, HTTP fetch),
   with read-only credentials and explicit size and content-type limits.
2. Implements parsers for the formats actually present in the corpus, normalising text while
   preserving structure, and stripping active content.
3. Extracts document metadata including timestamps and ACL tags, failing closed when
   permissions cannot be determined.
4. Implements two chunking strategies behind a versioned `Chunker` port, emitting chunks with
   `heading_path`, `anchor`, and `token_count`.
5. Computes `content_hash` so ingestion is idempotent and configuration changes invalidate
   precisely the chunks they affect.
6. Writes chunks to storage with atomic active-set flips and tombstones, so retrieval can
   never observe a half-ingested document.
7. Flags instruction-like content at ingestion, pre-positioning the injection defence from
   architecture §8.3.
8. Builds the ingestion CLI and the chunk-inspection tool, so chunk quality can be reviewed by
   a human rather than inferred from metrics.
9. Authors `seed-v1`: the first 20–30 labelled questions, which become the seed of the
   ≥200-question golden set required in phase 5.

### 4.5 How to verify it works

**Automated:**

| Check | How | Expected |
| --- | --- | --- |
| Parser completeness | Parse each fixture document | All non-empty content accounted for; structure preserved; no content dropped |
| Chunk boundaries | Run chunker tests across all strategies | Chunks within budget; no chunk begins or ends mid-sentence without an explicit marker; `heading_path` matches the document outline |
| **Idempotency** | Ingest the corpus twice | Second run writes zero chunks; total chunk count identical |
| Duplicate handling | Ingest the fixture duplicate and near-duplicate | Duplicate collapses to one document; near-duplicate stored separately but detectable |
| Incremental update | Change one document, reindex | Only that document's chunks change; other documents untouched |
| **Deletion** | Delete a document, reindex | Document tombstoned and immediately absent from retrieval inputs |
| Config invalidation | Change chunker version, reindex | Chunks re-chunked; `content_hash` changes for affected documents |
| Empty and hostile input | Ingest empty, binary, and malformed files | Handled without crashing the run; errors recorded per document |
| ACL derivation | Ingest the restricted fixture directory | Correct `acl_tags` on restricted documents; fail-closed when source permissions are absent |
| Hash determinism | Compute the hash twice | Identical; sensitive to both text and version changes |
| Injection flagging | Run against `adversarial-corpus` fixtures | Payloads flagged; false-positive rate on ordinary documents reported and reviewed |

**Reported, then read by a human (this is the real verification of phase 2):**

- Chunk statistics: document count, chunk count, mean and median token count, distribution,
  percentage of chunks over budget, and the worst offenders by document.
- A dump of 20 randomly sampled chunks with their headings, read end to end.

**Manual inspection — do not skip:**

1. Open 20 sampled chunks and judge for each: is it self-contained, does it begin and end at a
   sensible boundary, does it carry enough context to be citable, and would a person pointed at
   it know which document and section it came from?
2. Confirm every chunk in the restricted fixture carries ACL tags, and that the fail-closed
   path is exercised by removing the permission source.
3. Confirm the tables document produces chunks a reader can interpret without the original
   table.
4. Confirm the injected fixture is flagged and that benign imperative sentences in ordinary
   documents are not flagged so aggressively that most of the corpus is marked suspicious.
   An unusable flag rate is a tuning bug, not a feature.

**Read `seed-v1` aloud with a subject-matter expert.** If they cannot answer a question from
the cited chunk without seeing the source document, that chunk is not good enough. Catching
this now is far cheaper than catching it in phase 5.

### 4.6 Gate — all must pass

- [ ] Corpus ingested twice with zero duplicate chunks
- [ ] Change and delete propagate correctly, and a deleted document is absent immediately
- [ ] Chunk statistics printed and reviewed; over-budget chunks either fixed or accepted explicitly
- [ ] 20 sampled chunks judged self-contained and citable by a human, recorded as such
- [ ] Restricted documents carry ACL tags; fail-closed verified by removing the permission source
- [ ] Injected fixtures flagged with an acceptable false-positive rate
- [ ] `seed-v1` authored, with ≥20 questions, and reviewed by someone who knows the corpus
- [ ] Corpus inventory documented, including known gaps and stale documents
- [ ] Chunker ADR written with the statistics that justified the strategy

### 4.7 Risks specific to this phase

| Risk | Response |
| --- | --- |
| Tuning chunking before anything can measure quality | Treat this phase's output as a *hypothesis*. Version the chunker, keep the statistics, and settle it with Recall@k in phase 3 |
| `content_hash` defined before the embedding model exists | Define the hash over normalised text, chunker version, and an embedding-model version **string from config from day one** — even if the value is a placeholder. Retrofitting this field later means re-ingesting the entire corpus |
| Silently dropping unparseable documents | Error isolation must be loud: a document that failed to ingest appears in a failure report, never quietly missing |
| The labelled question set slips | This is the single biggest schedule risk to any quality claim (AQ-4). Start in this phase, grow it every phase, and never defer the authoring |
| Fixture corpus too easy | Real documents are messier. Include at least one genuinely awkward document; if the sample corpus is tidy, phase 3's Recall@k will be misleadingly good |
| Over-eager injection flagging | Report the flag rate on ordinary documents. A heuristic that flags 30% of a normal corpus will be switched off within a week |

---

## 5. Phase 3 — Embedding & vector store

### 5.1 Goal

Chunks are embedded and indexed, dense and lexical search both work with access control applied
inside the query, and per-retriever retrieval quality is measured and published as a baseline.

### 5.2 Why this phase exists

This is where assumption `A5` (~1 M chunks, PostgreSQL is sufficient) is either validated or
disproved — and it must be disproved early, because the answer changes the retrieval
architecture (architecture §18, §20.1). It is also the first phase that produces a quality
number, which every later tuning decision depends on.

### 5.3 Files to create

**`packages/retrieval`**

| Path | Responsibility |
| --- | --- |
| `packages/retrieval/models.py` | `Hit`, `RankedList`, `RetrievedContext` types shared across retrieval stages |
| `packages/retrieval/embed.py` | Embedding orchestration: batching, caching, dimension assertion |
| `packages/retrieval/vector_search.py` | Dense search through the `VectorStore` port, with the ACL predicate inside the query |
| `packages/retrieval/lexical_search.py` | BM25/full-text search through the `LexicalStore` port, with the same ACL predicate |
| `packages/retrieval/filters.py` | Single place where the ACL predicate and metadata predicates are constructed — reused by both retrievers so they cannot diverge |
| `packages/retrieval/parallel.py` | Concurrent execution of both retrievers with per-retriever timeouts and partial-failure handling |
| `packages/retrieval/index_writer.py` | Persists embeddings for new and changed chunks; drives the phase-2 indexer with vectors attached |
| `packages/retrieval/index_stats.py` | Index health: coverage, null embeddings, orphans, stale documents, dimension mismatches |

**Real model adapters**

| Path | Responsibility |
| --- | --- |
| `packages/llm/adapters/hosted_chat.py` | Real chat adapter behind `ChatModel`, with streaming, timeout, bounded retry |
| `packages/llm/adapters/hosted_embedder.py` | Real embedder behind `Embedder`, with batch size, rate-limit handling, and reported dimensions |
| `packages/llm/adapters/hosted_reranker.py` | Real reranker behind `Reranker` |

**Storage and migrations**

| Path | Responsibility |
| --- | --- |
| `packages/storage/repositories/vector_store.py` | `VectorStore` implementation: approximate nearest-neighbour search, ACL-filtered, over-fetching so permitted users always get a full k |
| `packages/storage/repositories/lexical_store.py` | `LexicalStore` implementation: full-text ranking, same ACL predicate, over-fetching |
| `infra/migrations/0003_vector_extension.sql` | Vector extension and column type; the settled answer to `AQ-1` recorded here |
| `infra/migrations/0004_search_indexes.sql` | HNSW vector index, full-text index, ACL and status indexes |
| `tools/reembed.py` | Full re-embed: new model → new column or table → eval compare → cut over → purge (architecture §6.5) |
| `tools/index_stats.py` | Prints the index health report |

**Worker**

| Path | Responsibility |
| --- | --- |
| `apps/worker/jobs/embed_job.py` | Batched embedding of pending chunks with rate-limit awareness and throughput reporting (NFR-6) |
| `apps/worker/jobs/purge_job.py` | Async purge of tombstoned rows |
| `apps/worker/throughput.py` | Chunks-per-minute measurement per worker |

**Evaluation**

| Path | Responsibility |
| --- | --- |
| `evals/golden-v1.jsonl` | The golden set, grown from `seed-v1` to ≥200 labelled questions across document types and query shapes |
| `packages/eval/metrics/retrieval.py` (extend) | Recall@1/5/10, hit rate, MRR, nDCG, plus **per-retriever** and **oracle-union** reporting |
| `packages/eval/sweep.py` | Parameter sweep over chunk size, overlap, and top-k; reports the resulting metric surface |
| `packages/eval/baseline.py` | Publishes a run to `evals/baselines/<config_version>.json` and diffs against it |
| `evals/baselines/` | Committed baseline metrics per configuration version |

**Tests**

| Path | Responsibility |
| --- | --- |
| `tests/unit/retrieval/test_filters.py` | The ACL predicate is constructed once and reused; both retrievers receive it |
| `tests/integration/retrieval/test_vector_search.py` | Correctness, ranking, top-k, dimension handling |
| `tests/integration/retrieval/test_lexical_search.py` | Correctness, exact-term behaviour, ranking |
| `tests/integration/retrieval/test_acl_isolation.py` | A user in group A can never retrieve a document restricted to group B, by search, by count, or by direct id lookup |
| `tests/integration/retrieval/test_idempotent_indexing.py` | Re-indexing does not duplicate vectors |
| `tests/integration/retrieval/test_degradation.py` | With the vector store unavailable, the lexical path still returns results (NFR-9) |
| `tests/integration/eval/test_recall_gate.py` | The NFR-12 recall regression gate fails a deliberately degraded configuration |
| `tests/performance/test_retrieval_latency.py` | Retrieval stage p95 against NFR-3 |

**Documentation**

| Path | Responsibility |
| --- | --- |
| `docs/adr/0007-embedding-dimension-strategy.md` | The `AQ-1` decision, with the migration cost of each option |
| `docs/eval-baseline.md` | The published baseline: per-retriever and union recall, and what it implies for hybrid retrieval |

### 5.4 What this phase does

1. Wires a real embedding provider behind the existing port, asserting dimension consistency
   between the embedder and the stored column, and failing loudly on mismatch.
2. Implements the vector store adapter with the ACL predicate inside the query, over-fetching
   so that users with narrow permissions still receive a full result set.
3. Implements the lexical store adapter with the identical predicate, extracted into a single
   shared filter module so the two cannot drift apart.
4. Runs dense and lexical retrieval concurrently with independent timeouts, so one store being
   unavailable degrades rather than fails (NFR-9).
5. Backfills embeddings for the phase-2 corpus through the worker, reporting throughput and
   cost.
6. Reports retrieval quality **per retriever and as an oracle union**, which reveals whether
   hybrid fusion is worth the extra complexity and by how much headroom it buys.
7. Sweeps chunking and top-k parameters and publishes the metric surface rather than a single
   tuned number.
8. Establishes the regression gate that later phases will run on every change.

### 5.5 How to verify it works

**Automated:**

| Check | How | Expected |
| --- | --- | --- |
| Index completeness | Index health report | Every active chunk has an embedding of the configured dimension; no nulls, no orphans, no duplicate vectors |
| Dense correctness | Search for a phrase known verbatim in a fixture document | That document ranks first |
| **Lexical exactness** | Search for an error code, product name, and version string | Those documents rank first; the lexical path handles exact terms the dense path can miss |
| **Per-retriever Recall@k** | Eval `golden-v1` | Recall@5 reported for dense alone and lexical alone |
| **Oracle union** | Eval | Union recall reported; the gap between the better single retriever and the union quantifies the value of fusion |
| **ACL isolation** | Run the isolation suite as a group-A user against restricted documents | Zero restricted results across search, count, and direct-id paths |
| **Permission-scoped top-k** | Query as a narrowly-permissioned user | A full result set returned, not a truncated one — confirms over-fetch works |
| Idempotent indexing | Re-run embedding for the corpus | No duplicate vectors; counts unchanged |
| Degradation | Make the vector store unavailable | Lexical-only results returned; the answer path is flagged as degraded; no request fails |
| Dimension guard | Change the configured dimension without migrating | Startup or indexing fails loudly, rather than silently writing wrong-width vectors |
| Latency | Performance test | Retrieval p95 within NFR-3 at the current index size |
| Throughput | Measure embedding throughput | At or above the NFR-6 estimate, or the shortfall recorded with its consequence |
| Regression gate | Deliberately degrade the configuration | The gate fails the build |

**Reported and read by a human:**

- Baseline table: dense-only, lexical-only, and union Recall@1/5/10 and MRR on `golden-v1`,
  committed to `evals/baselines/`.
- The chunk-size and top-k sweep surface, with the chosen operating point marked and the
  trade-off stated in words.
- Index health and cost figures.

**Manual:**

1. Search the corpus for the questions you personally know the answer to, and read the top
   results. Does the right document appear in the top five? Do the *snippets* contain the
   answer, or only the document?
2. Confirm a user outside the restricted group sees no hint that the restricted documents exist
   — not in results, counts, timing differences that suggest a different corpus size, or error
   messages.
3. Inspect the actual SQL executed for both retrievers and confirm the ACL predicate is present
   in each. This is a five-minute check that prevents the worst incident in the product.

### 5.6 Gate — all must pass

- [ ] Index health clean: full coverage, correct dimension, no duplicates or orphans
- [ ] Dense and lexical Recall@5 both reported, with union recall and the hybrid headroom quantified
- [ ] ACL isolation suite green; restricted documents invisible to unauthorised users by every path tried
- [ ] Permitted users receive a full result set, not a truncated one
- [ ] Graceful degradation to lexical-only confirmed
- [ ] `golden-v1` at ≥200 labelled questions
- [ ] Baseline metrics committed; parameter sweep published; operating point chosen with a written rationale
- [ ] Retrieval p95 within NFR-3; embedding throughput measured against NFR-6
- [ ] Regression gate demonstrated to fail a deliberately degraded configuration
- [ ] Embedding-dimension decision recorded as an ADR; assumption `A5` explicitly confirmed or flagged as at risk

### 5.7 Risks specific to this phase

| Risk | Response |
| --- | --- |
| The corpus is much larger or messier than `A5` assumes | Measure index build time, index memory footprint, and recall degradation early. If pgvector is inadequate, this is the cheapest moment to migrate — only the two store adapters change |
| Query embeddings and chunk embeddings computed by different models | Dimension assertion plus a stored `embedding_model` on every chunk; search refuses on mismatch rather than returning noise |
| ACL predicate present in one retriever and missing in the other | One shared filter module, plus a test asserting both retrievers received it |
| Recall looks good only because the golden set is easy | Stratify `golden-v1` by document type and query shape and report recall per stratum, not only in aggregate. Also report on real production traces once any exist |
| `AQ-1` left undecided | Decide it here. The migration later is far more expensive than the decision now |
| Sweeping parameters and overfitting to 200 questions | Treat the sweep as a surface, not an optimum. Hold out a slice of the golden set that is never used for tuning |

---

## 6. Phase 4 — Guardrails

### 6.1 Goal

Every safety control that does not require answer generation is in place and adversarially
tested: access control, untrusted-content handling, secrets, log hygiene, rate limits,
configuration versioning, retention, and the red-team harness.

### 6.2 Why this phase exists, and its honest limitation

Architecture driver D5 makes an ACL bug the most serious plausible incident in this product:
one missed filter exposes documents, whereas one successful jailbreak produces some bad text.

The phase ordering has a real consequence that must be stated plainly rather than papered
over: **guardrails that depend on generation cannot be finished here**, because there is no
generation until phase 5. Phase 4 closes everything else and *builds the harness* for the
rest; phase 5 closes the remainder. The split is explicit in §6.4.

### 6.3 Files to create

**Access control hardening**

| Path | Responsibility |
| --- | --- |
| `packages/core/auth/principal.py` | The immutable `Principal` type: user id, groups, roles; constructed only from a verified token |
| `packages/core/auth/claims.py` | Group/role claim extraction from the verified token; unknown claim shape fails closed |
| `packages/core/auth/authorization.py` | Role checks for operator and admin endpoints; deny by default |
| `infra/migrations/0005_row_level_security.sql` | RLS policies on `document` and `chunk`, driven by the session variable set from `Principal` |
| `packages/storage/session_principal.py` | Sets `app.user_groups` at transaction start from `Principal` |
| `tests/security/test_acl_leak_matrix.py` | The systematic matrix: every read path × every role × every document visibility |
| `tests/security/test_acl_bypass_attempts.py` | Direct ids, count queries, joins, export and trace paths, timing and error-message differences |

**Untrusted content handling**

| Path | Responsibility |
| --- | --- |
| `packages/safety/redaction.py` | PII and secret detection and redaction on model output, with an allow-listed set of detectors |
| `packages/safety/patterns.py` | Detection patterns, versioned, so a false positive can be traced to a version |
| `packages/safety/output_filter.py` | Applies redaction to any text that will be shown to a user or written to a trace |
| `packages/safety/injection_defences.py` | Prompt-side defence primitives: delimiter isolation, instruction-neutralisation, suspicious-fragment annotation — consumed by phase 5's prompt assembly |
| `tests/security/test_redaction.py` | Detectors fire on fixtures; permitted patterns preserved |
| `tests/security/test_injection_primitives.py` | Defence primitives neutralise direct, indirect, encoded, and role-play payloads at the prompt-construction layer |

**Secrets, logging, and configuration hygiene**

| Path | Responsibility |
| --- | --- |
| `packages/core/logging/redaction.py` (extend) | Hardened allow-list; covers request bodies as well as log fields |
| `tools/check_log_hygiene.py` | CI guard: fails if any code path can log content-bearing fields |
| `tools/check_secrets.py` | Repository secret scan, plus a startup assertion that no secret was supplied as a literal |
| `infra/terraform/secret_store.tf` | Managed secret store resources |
| `.github/workflows/security.yml` (extend) | Runs the log-hygiene and secret checks on every push |
| `tests/security/test_provider_retention_policy.py` | Asserts the configured provider retention/no-training setting (FR-43) |

**Rate limiting and quotas**

| Path | Responsibility |
| --- | --- |
| `apps/api/middleware/ratelimit.py` (implement) | Per-user and per-IP quotas, concurrency caps, standard rate-limit headers |
| `apps/api/middleware/cost_guard.py` | Per-user spend cap, as a backstop against cost exhaustion |
| `tests/integration/api/test_rate_limit.py` | Burst produces 429s with a clear user-facing message; limits recover |

**Configuration versioning and audit**

| Path | Responsibility |
| --- | --- |
| `packages/storage/repositories/config_store.py` | Versioned prompt and retrieval configuration: stage, activate, roll back |
| `packages/storage/repositories/audit_repository.py` | Append-only audit records for admin mutations |
| `apps/api/routes/admin.py` (implement config routes) | Config staging, activation, rollback; activation audited |
| `tests/integration/api/test_config_rollback.py` | Activation changes behaviour; rollback restores the previous version exactly |

**Retention**

| Path | Responsibility |
| --- | --- |
| `apps/worker/jobs/retention_job.py` | Enforces conversation, message, trace, and tombstone retention per policy |
| `tests/integration/worker/test_retention.py` | Expired records removed; tombstones purged; active data untouched |

**Trace writes** — needed so guardrail behaviour is auditable

| Path | Responsibility |
| --- | --- |
| `packages/storage/repositories/trace_store.py` | Append trace records; buffered so analytics never block a user response |
| `infra/migrations/0006_trace_tables.sql` | `trace`, `message`, `conversation` tables with retrieval detail and version fields |
| `apps/api/routes/traces.py` (implement read paths) | Trace search and detail, access-controlled and audited |
| `tests/integration/test_trace_content.py` | Traces contain what they must; logs contain none of it |

**Red-team harness**

| Path | Responsibility |
| --- | --- |
| `evals/adversarial-corpus/` | Documents seeded with injection payloads: direct instruction override, role-play, encoded payloads, attempts to exfiltrate context, attempts to trigger tool use, and a benign document to measure false positives |
| `evals/redteam/prompts.jsonl` | Adversarial user queries across those categories |
| `evals/redteam/suite.py` | Runner producing a pass-rate per category |
| `evals/redteam/report.py` | Report with per-category rates and newly-broken regressions |
| `tests/security/test_redteam_baseline.py` | Records the baseline pass rate so later changes cannot silently weaken defences |

**Documentation**

| Path | Responsibility |
| --- | --- |
| `docs/security/threat-model.md` | Living threat model; updated in phase 5 when generation arrives |
| `docs/security/guardrail-status.md` | Table of every guardrail, its status, and which test enforces it |
| `docs/adr/0008-guardrail-ordering.md` | Records why guardrails precede generation, and which guardrails necessarily land in phase 5 |
| `docs/runbooks/access-breach-response.md` | What to do if an ACL bug is suspected |

### 6.4 What this phase does

1. Locks the trust model into code: `Principal` is constructible only from a verified token,
   and every downstream call receives it.
2. Enables row-level security as the safety net beneath the ACL predicate, so a future query
   that forgets the filter still cannot return restricted rows.
3. Runs a systematic ACL leak matrix across every read path and role, plus explicit bypass
   attempts — direct ids, counts, joins, exports, traces, and error messages.
4. Builds the prompt-side injection defence primitives and tests them directly against
   adversarial payloads, even though no prompt is assembled yet.
5. Implements PII and secret redaction on the output path, with versioned detectors.
6. Enforces the log-content prohibition in code and in CI, so it cannot regress silently.
7. Implements rate limits, per-user quotas, and a cost guard.
8. Implements versioned configuration with staging, activation, audit, and one-call rollback.
9. Implements retention, and verifies expired data is actually removed.
10. Makes trace writes real, access-controlled, and auditable, so everything above can be
    investigated after the fact.
11. Builds the adversarial corpus and the red-team harness, and records a baseline pass rate.

### 6.5 Guardrails closed in this phase versus deferred

| Guardrail | Phase | Enforced by |
| --- | --- | --- |
| Authentication and identity propagation | 4 | Auth middleware, `Principal` |
| Document-level ACL in queries | 3, hardened in 4 | Shared filter module |
| RLS safety net | 4 | Migration plus session setting |
| Secret management | 4 | Secret store plus CI scan |
| No content in logs | 4 | Redaction filter plus CI guard |
| Provider retention / no-training | 4 | Config assertion test |
| Rate limits, quotas, cost guard | 4 | Middleware tests |
| Configuration versioning and rollback | 4 | Config store tests |
| Retention and deletion | 4 | Retention job tests |
| Output PII/secret redaction | 4 | Detector tests |
| Ingestion injection flagging | 2 | Scan tests |
| Prompt-side injection defence primitives | 4 | Primitive tests |
| Red-team harness and baseline | 4 | Red-team suite |
| **Confidence gate and refusal** | **5** | Gate calibration plus eval |
| **Citation verification and repair** | **5** | Verification tests plus groundedness eval |
| **Prompt assembly with strict grounding** | **5** | Groundedness eval plus red-team |
| **Answer-path output filtering in situ** | **5** | End-to-end tests |
| **Tool-free guarantee** | **5** | Capability assertion that no tool surface is exposed |

The last six are deliberately deferred: they are only observable once generation exists. This
table is the phase-4/phase-5 contract, and `docs/security/guardrail-status.md` tracks it.

### 6.6 How to verify it works

**This phase's verification is adversarial by definition.** Passing the happy path proves
nothing; every check below is an attempt to break something.

**Automated:**

| Check | How | Expected |
| --- | --- | --- |
| **ACL leak matrix** | Full matrix of read paths × roles × visibility | Only permitted combinations return data; every other combination returns nothing |
| **Bypass attempts** | Direct id, count, join, export, trace, error-message, timing | No restricted content, no existence disclosure, no count oracle |
| **RLS safety net** | Deliberately issue a query with the ACL predicate omitted | Row-level security still refuses restricted rows — the proof that D5 is structural |
| **Tampered token** | Forged, expired, wrong-audience, and wrong-issuer tokens | Rejected; no partial acceptance |
| **Missing claims** | Valid token with no group claims | Deny, not default-allow |
| **Injection primitives** | Adversarial payloads through the defence layer | Neutralised at the construction layer; benign payloads unaffected |
| **Red-team baseline** | Full suite | Pass rate recorded as the baseline for phase 5 |
| **False-positive rate** | Red-team suite against benign queries and documents | Reported; an implausible false-positive rate means the defences are too blunt and will get disabled |
| **Redaction** | Fixture answers containing emails, phone numbers, card-like numbers, and credential patterns | Redacted before display; permitted patterns preserved |
| **Log hygiene** | Attempt to log a question, a chunk, or a completion | Blocked; the CI guard fails the build |
| **Secret handling** | Plant a credential literal in source | Caught by scan; startup refuses to run with a literal secret |
| **Provider retention** | Assert configuration | No-training setting present (FR-43) |
| **Rate limiting** | Burst beyond the quota | 429 with a user-legible message; recovery after the window |
| **Cost guard** | Simulated spend above the cap | Further requests shed with a clear message |
| **Config rollback** | Activate a new version, then roll back | Behaviour returns exactly to the prior version |
| **Retention** | Advance past the retention horizon | Expired traces, conversations, and tombstones purged; active data intact |
| **Trace auditability** | Inspect a trace after a restricted-access attempt | The attempt is recorded with the actor and outcome; content absent from logs |

**Manual — a real person tries to break it:**

1. Using an operator account, ask each other user to try, in good faith, to retrieve a
   document they should not see: by name, by guessing an id, by asking a question whose answer
   only that document contains, and by asking for a count. Document every outcome.
2. Read the red-team report and confirm each category's failure mode is one you would accept.
3. Read `guardrail-status.md` end to end and confirm no row claims a control without naming the
   test that enforces it. Any row without a test is not a control.

### 6.7 Gate — all must pass

- [ ] ACL leak matrix and bypass suite green across all roles and paths
- [ ] RLS demonstrated to refuse restricted rows even when the ACL predicate is omitted
- [ ] Forged, expired, and claim-less tokens all denied
- [ ] Injection primitives neutralise the adversarial corpus; false-positive rate acceptable and reported
- [ ] Red-team baseline pass rate recorded
- [ ] Output redaction verified on fixtures
- [ ] Log hygiene guard demonstrably fails when violated
- [ ] Secret scan clean; a planted secret is caught
- [ ] Provider retention setting asserted
- [ ] Rate limiting, cost guard, retention, and config rollback all verified
- [ ] Every trace is auditable; no content in logs
- [ ] `guardrail-status.md` complete, with a named test per control, and its deferred rows matching §6.5 exactly

### 6.8 Risks specific to this phase

| Risk | Response |
| --- | --- |
| A green test suite that has not been attacked | The manual adversarial pass is mandatory. Green tests only mean the cases you imagined were covered |
| Over-blocking, then someone disables the control | Report false-positive rates alongside detection rates. Controls that block legitimate use get switched off, and then they protect nothing |
| Guardrails blocking progress | Each control is behind a port or a filter module, so it can be relaxed centrally without touching the pipeline. Do not scatter bypass flags through the code |
| RLS mistaken for the primary control | RLS is the safety net *beneath* the query predicate. Both are required; a system relying on RLS alone loses performance and clarity |
| Six guardrails deferred to phase 5 being forgotten | `guardrail-status.md` is the tracking artefact, and phase 5's gate requires its deferred rows to be closed |
| Test accounts and fixtures with real permissions | Use synthetic identities and a purpose-built restricted fixture set. Never use real personnel data to test access control |

---

## 7. Phase 5 — Retrieval + LLM answer

### 7.1 Goal

End-to-end grounded answering: hybrid retrieval with fusion and reranking, a calibrated
confidence gate, streaming answers with verified citations, the refusal path, full traces and
cost accounting, and release gates that block regressions.

### 7.2 Why this phase exists

Everything built so far exists to make this phase's output trustworthy. This is also the
phase where the product can first be judged honestly, and where the streaming/verification
conflict from architecture §6.1 must actually be resolved in running code.

### 7.3 Files to create

**Orchestrator**

| Path | Responsibility |
| --- | --- |
| `packages/pipeline/orchestrator.py` | The pipeline: context load → rewrite → embed → parallel retrieve → fuse → rerank → gate → pack → generate → verify → persist |
| `packages/pipeline/stages/__init__.py` | Stage registry |
| `packages/pipeline/stages/context_load.py` | Conversation context assembly within a window |
| `packages/pipeline/stages/query_rewrite.py` | Follow-up to standalone query, with a skip condition and a cheap model |
| `packages/pipeline/stages/fuse.py` | Reciprocal Rank Fusion over the two ranked lists |
| `packages/pipeline/stages/rerank.py` | Reranking of the fused top-N |
| `packages/pipeline/stages/gate.py` | Confidence gate: thresholds, agreement signals, refusal decision, degraded-mode ceiling |
| `packages/pipeline/stages/context_pack.py` | Overlap merge, truncation with explicit markers, stable numbering, token budgeting |
| `packages/pipeline/stages/generate.py` | Streaming generation and cost capture |
| `packages/pipeline/stages/citation_verify.py` | Deterministic citation resolution and violation detection |
| `packages/pipeline/stages/persist.py` | Message, trace, and cost persistence |
| `packages/pipeline/refusal.py` | Refusal message construction with near-misses, suggestions, and sources searched |
| `packages/pipeline/degraded.py` | Degraded-mode handling and confidence ceilings (NFR-9) |
| `tools/ask.py` | CLI smoke path: ask a question without the UI, print answer, citations, and trace summary |
| `tools/calibrate_gate.py` | Threshold sweep over the golden set; publishes the groundedness-versus-refusal curve |

**Grounding and prompts**

| Path | Responsibility |
| --- | --- |
| `packages/grounding/prompts/__init__.py` | Prompt registry and versioning; every template hashed into a `prompt_version` |
| `packages/grounding/prompts/system_answer.txt` | Role, hard constraints, citation requirement, refusal instruction, untrusted-content statement |
| `packages/grounding/prompts/context_block.txt` | Delimited, numbered context block template with source metadata |
| `packages/grounding/prompts/refusal.txt` | Refusal wording that names what was searched and what to try |
| `packages/grounding/assembly.py` | Prompt assembly using the phase-4 defence primitives |
| `packages/grounding/citations.py` | Marker extraction, resolution against supplied chunks, violation classification |
| `packages/grounding/repair.py` | Bounded single repair attempt, then strip or refuse |
| `packages/grounding/prompts/index.json` | Prompt catalogue with versions and change notes |

**API**

| Path | Responsibility |
| --- | --- |
| `apps/api/routes/chat.py` (implement) | Real chat endpoint emitting the full SSE event sequence: `start`, `source_list`, `token`, `citations`, `refusal`, `feedback_prompt`, `done` |
| `apps/api/routes/feedback.py` (implement) | Feedback persistence against the exact trace |
| `apps/api/routes/sources.py` (implement read paths) | Source listing and the citation resolver endpoint, with an ACL re-check on read |
| `apps/api/routes/admin.py` (extend) | Reindex trigger, eval run trigger, config staging |
| `apps/api/sse.py` | SSE plumbing: event framing, disconnect handling, mid-stream replacement |
| `apps/api/routes/eval.py` | Evaluation run endpoints with baseline comparison |
| `apps/api/routes/metrics.py` | Dashboard metrics endpoints |

**Evaluation**

| Path | Responsibility |
| --- | --- |
| `packages/eval/metrics/generation.py` (implement) | Groundedness, citation correctness, answer relevance, refusal correctness |
| `packages/eval/metrics/unsupported_claim.py` | Unsupported-claim rate, the G3 measure |
| `packages/eval/judge.py` (implement) | Pinned judge model, fixed rubric, temperature 0, calibration tracking against human labels |
| `packages/eval/judge_calibration.py` | Measures judge-versus-human agreement and tracks drift |
| `evals/refusal-v1.jsonl` | Unanswerable questions for refusal correctness and false-refusal measurement |
| `evals/anti-golden-v1.jsonl` | A holdout slice never used for tuning, to detect overfitting |
| `packages/eval/production_sample.py` | Stratified sampling of real traces for drift detection |
| `.github/workflows/quality.yml` | Nightly full eval; per-push evaluation against the baseline with the NFR-12 gate |

**Analysis**

| Path | Responsibility |
| --- | --- |
| `apps/worker/jobs/feedback_analysis_job.py` | Clusters downvotes and refusals into retrieval failures, prompt failures, and content gaps |
| `packages/eval/content_gap_report.py` | Top unanswered questions with the near-miss chunks that failed to clear the threshold |
| `tools/feedback_report.py` | Cluster report for the operator |

**Tests**

| Path | Responsibility |
| --- | --- |
| `tests/unit/pipeline/test_fuse.py` | Fusion correctness and properties |
| `tests/unit/pipeline/test_gate.py` | Gate decisions across the calibration sweep, including refusal and degraded-mode ceilings |
| `tests/unit/pipeline/test_context_pack.py` | Budgeting, overlap merging, explicit truncation markers, stable numbering |
| `tests/unit/grounding/test_citations.py` | Marker extraction, resolution, violation classification, unsupported-claim detection |
| `tests/unit/grounding/test_repair.py` | Repair converges; unrepairable output is stripped or refused |
| `tests/unit/grounding/test_assembly.py` | Prompt contains the constraints; context is delimited and annotated; defence primitives applied |
| `tests/integration/test_end_to_end.py` | Full pipeline against fake adapters, deterministic |
| `tests/integration/test_streaming_events.py` | Event order, provisional-then-verified citations, `replace_answer` on verification failure, refusal without tokens |
| `tests/integration/test_reproducibility.py` | Same config and question reproduce the same prompt version, model, and retrieved chunk set |
| `tests/quality/test_groundedness_gate.py` | NFR-12 gate fails a deliberately ungrounded prompt |
| `tests/quality/test_refusal_gate.py` | False-refusal rate ceiling |
| `tests/security/test_redteam_generation.py` | Red-team suite against real generation; pass rate at or below the baseline |
| `tests/security/test_tool_free_assertion.py` | The generation path exposes no tool-calling surface |
| `tests/performance/test_ttft.py` | TTFT p50 and p95 against §17 budgets, with per-stage attribution |
| `tests/performance/test_cost.py` | Cost per answer computed from actual tokens, within budget |

**Documentation**

| Path | Responsibility |
| --- | --- |
| `docs/adr/0009-gate-threshold-selection.md` | The calibration method and the chosen operating point with its trade-off stated |
| `docs/eval-baseline.md` (extend) | End-to-end quality and performance baseline |
| `docs/runbooks/threshold-tuning.md` | How to change a threshold safely, with the eval gate |
| `docs/runbooks/prompt-change.md` | How to change a prompt safely, including red-team and rollback |
| `docs/content-gaps.md` | Living backlog of what the corpus cannot answer |

### 7.4 What this phase does

1. Implements the eleven-stage pipeline as independently testable, individually timed stages,
   each recording its inputs and outputs in the trace.
2. Merges the two ranked lists with Reciprocal Rank Fusion.
3. Adds reranking over the fused top-N, with `rerank_top_n` as the primary latency lever.
4. Implements the confidence gate and **calibrates its threshold by sweeping the golden set**,
   publishing the groundedness-versus-refusal trade-off curve and choosing an operating point
   with a written rationale — rather than adopting a guessed default.
5. Packs context within a token budget, merging overlaps and marking truncation explicitly so
   the model never reads a fragment as if complete.
6. Assembles the grounded prompt using the phase-4 defence primitives, and generates with
   streaming and per-call cost capture.
7. Verifies citations deterministically, attempts one bounded repair, and otherwise strips
   uncited claims or refuses.
8. Emits the full SSE event sequence, resolving the streaming-versus-verification conflict with
   provisional citations and a mid-stream replacement event.
9. Completes the six guardrails deferred from phase 4: gate, citation verification, strict
   grounding prompt, in-situ output filtering, the refusal path, and the tool-free assertion.
10. Turns the eval harness into release gates: groundedness, unsupported-claim rate, refusal
    correctness, false-refusal ceiling, and red-team pass rate, all gating releases.
11. Closes the feedback loop: downvotes and refusals are clustered into retrieval failures,
    prompt failures, and content gaps.

### 7.5 How to verify it works

**Automated:**

| Check | How | Expected |
| --- | --- | --- |
| Fusion correctness | Unit tests plus properties | Known rank orderings fuse correctly; a document appearing in both lists outranks one appearing in a single list |
| **Gate calibration** | Sweep the threshold over the golden set | A published curve of groundedness versus refusal rate; chosen point marked with rationale; a deliberately wrong threshold fails the eval |
| **Answerable questions** | Golden set, end to end | Answers grounded in the cited chunks; citations resolve to chunks actually supplied |
| **Unanswerable questions** | `refusal-v1` | Refusal fires, with sources searched and suggestions; no invented answer |
| **False refusals** | `golden-v1` with the tuned threshold | Within the agreed ceiling — a gate that refuses answerable questions has failed in the other direction |
| **Groundedness** | `golden-v1` | At or above the G1 target of 90% |
| **Unsupported claims** | Golden set plus human-labelled sample | At or below the G3 target of 5% |
| **Citation validity** | All answers | 100% of citation markers resolve to supplied chunks; zero existence of dangling citations |
| Streaming contract | Event-sequence tests | Correct event order; provisional-then-verified citation states; refusal emits no tokens; a verification failure emits `replace_answer` |
| **Reproducibility** | Same config, same question, repeated | Same prompt version, model, and retrieved chunk set recorded on the trace |
| **Latency** | Performance test | TTFT p50 within the §17 budget and p95 within G4; per-stage attribution shows where time goes |
| **Degradation** | Fail the reranker, then the vector store | Pipeline degrades as designed, flags reduced confidence, never generates without context |
| **Cost** | Cost test | Per-answer cost computed from actual tokens and within the NFR-19 budget |
| **Regression gate** | A deliberately ungrounded prompt | Build fails |
| **Red-team** | Full suite with real generation | Pass rate at or below the phase-4 baseline and the G7 target of 2% |
| **Tool-free** | Capability assertion | No tool surface exposed anywhere on the generation path |
| Trace completeness | Inspect a trace | Every stage present, including the gate decision and its inputs |

**Manual — read real answers, carefully:**

1. Ask 20 questions you already know the answer to. For each, click through every citation and
   confirm the cited passage actually supports the sentence it is attached to. This is the
   single most important check in the entire plan; it is what the product is for.
2. Ask 10 questions the corpus cannot answer. Confirm every one refuses rather than hedging into
   a fabrication.
3. Read the calibration curve and write down, in one sentence, what the chosen threshold
   trades away. If that sentence cannot be written, the threshold has not been chosen — it has
   been guessed.
4. Find the worst-performing stratum in the golden set results and understand why. A system
   whose aggregate number is good but whose weak stratum is unknown will fail in production on
   exactly the content nobody sampled.
5. Inspect traces for questions that produced bad answers and confirm you can identify the
   responsible stage from the trace alone.

### 7.6 Gate — all must pass

- [ ] Groundedness at or above the G1 target on the golden set, reported per stratum
- [ ] Unsupported-claim rate at or below the G3 target on the human-labelled sample
- [ ] 100% citation resolution; no dangling markers
- [ ] Refusal correct on `refusal-v1`; false-refusal rate within ceiling on `golden-v1`
- [ ] Calibration curve published; operating point chosen with a written trade-off
- [ ] Red-team pass rate at or below the phase-4 baseline and the G7 target
- [ ] TTFT p50 and p95 within the §17 budget, with per-stage attribution
- [ ] Cost per answer within the NFR-19 budget, computed from actual tokens
- [ ] Regression gate demonstrably blocks a bad prompt and a bad retrieval configuration
- [ ] Reproducibility verified on repeated identical queries
- [ ] Degradation paths verified: reranker down, vector store down, model down
- [ ] All six phase-4-deferred guardrails closed and `guardrail-status.md` complete
- [ ] Feedback and refusal clustering produces a usable content-gap backlog
- [ ] `CLI ask` path demonstrable end-to-end without the UI

### 7.7 Risks specific to this phase

| Risk | Response |
| --- | --- |
| Quality tuned by intuition, overfitting the golden set | Every change runs the full suite plus the untouched holdout slice. If the tuned and holdout numbers diverge, the tuning is overfitted |
| The gate becomes permissive to make the metrics look good | Track refusal rate as a first-class metric alongside groundedness. A change that improves one by wrecking the other is not a change |
| Threshold drift under corpus change | Recalibrate whenever the corpus or chunking changes materially; a threshold is a function of the corpus, not a constant |
| Rerank blowing the latency budget | Measure per-stage; reduce `rerank_top_n` before disabling reranking; revisit the latency budget only with evidence |
| Streaming and verification mismatch in practice | The event-contract tests must cover the failure path, not just the happy path. A test suite that only exercises successful citation validation will miss exactly the case this design exists for |
| Judge drift | Pin the judge model and version, track judge-versus-human agreement, and treat a drop in agreement as a release blocker |
| Context dilution at high top-k | Sweep `final_top_k` and report quality against token cost; more context is not monotonically better |
| Cost surprises | Per-answer cost on every trace from day one; alert before the budget is exceeded, not after |
| Tuning forever | Define the stopping condition in advance: ship at the gate, and treat further gains as a separate piece of work with its own justification |

---

## 8. Phase 6 — UI

### 8.1 Goal

A surface that makes groundedness and provenance legible: an answer the user can verify, a
refusal that is informative rather than confusing, feedback that works, an admin console that
makes tuning and debugging possible, and accessibility that was designed in rather than added.

### 8.2 Why this phase exists

Provenance is the product. An answer without an inspectable source is worse than no answer,
because it invites trust it has not earned. This phase's job is to make verification a
two-click action for every claim, and to make refusal a normal, well-designed outcome rather
than an error state.

### 8.3 Files to create

**Chat surface**

| Path | Responsibility |
| --- | --- |
| `apps/web/app/(chat)/layout.tsx` | Chat layout: header, source panel, freshness indicator |
| `apps/web/app/(chat)/page.tsx` | New conversation |
| `apps/web/app/(chat)/[conversationId]/page.tsx` | Existing conversation |
| `apps/web/app/(chat)/error.tsx`, `not-found.tsx`, `loading.tsx` | Route-level states |
| `apps/web/components/chat/MessageThread.tsx` | Thread container, auto-scroll that respects user scroll position |
| `apps/web/components/chat/MessageBubble.tsx` | User and assistant message rendering, distinct and non-decorative |
| `apps/web/components/chat/Composer.tsx` | Input with character and context-limit affordances (FR-28) |
| `apps/web/components/chat/StreamingText.tsx` | Incremental rendering with a live-region announcement strategy |
| `apps/web/components/chat/CitationChips.tsx` | Inline citation markers, verified and provisional states visually distinguished |
| `apps/web/components/chat/SourceList.tsx` | Sources consulted, with title and freshness timestamp (FR-22) |
| `apps/web/components/chat/RefusalCard.tsx` | Refusal presentation: what was searched, near misses, suggested refinements |
| `apps/web/components/chat/FeedbackControl.tsx` | Thumbs up/down with an optional reason (FR-24) |
| `apps/web/components/chat/CitationPopover.tsx` | Citation preview: source, snippet, freshness |
| `apps/web/components/chat/ConversationList.tsx` | History with rename and delete (FR-25) |
| `apps/web/components/chat/ExportMenu.tsx` | Copy with citations, export to Markdown and PDF (FR-23) |
| `apps/web/components/chat/DegradedNotice.tsx` | Degraded-mode and freshness notices (FR-26) |

**Source viewer**

| Path | Responsibility |
| --- | --- |
| `apps/web/app/sources/[sourceId]/page.tsx` | Document view with the cited passage highlighted (FR-21) |
| `apps/web/components/sources/PassageHighlighter.tsx` | Renders the passage, scrolls to and highlights it, preserves document structure |
| `apps/web/lib/sources.ts` | Client for the citation-resolver endpoint, which re-checks access |

**Admin console**

| Path | Responsibility |
| --- | --- |
| `apps/web/app/admin/layout.tsx` | Admin shell with role gating (FR-30) |
| `apps/web/app/admin/page.tsx` | Operational overview |
| `apps/web/app/admin/sources/page.tsx` | Source list, status, document counts |
| `apps/web/app/admin/sources/[sourceId]/page.tsx` | Source detail, reindex trigger, delete |
| `apps/web/app/admin/config/page.tsx` | Current retrieval and prompt configuration with stage/activate/rollback (FR-31, FR-35) |
| `apps/web/app/admin/eval/page.tsx` | Eval run trigger and results against baseline |
| `apps/web/app/admin/traces/page.tsx` | Trace search and filters |
| `apps/web/app/admin/traces/[traceId]/page.tsx` | Full trace detail: stages, retrieved chunks, scores, versions, latency, cost |
| `apps/web/app/admin/metrics/page.tsx` | Volume, latency, refusal rate, cost, top unanswered questions (FR-34) |
| `apps/web/app/admin/gaps/page.tsx` | Content-gap backlog from refusal and downvote clustering |

**Auth and client infrastructure**

| Path | Responsibility |
| --- | --- |
| `apps/web/lib/auth.ts` | Session handling, token attachment, 401 handling and re-auth redirect (FR-29) |
| `apps/web/lib/api.ts` | Typed client; adds `credentials`, handles errors uniformly |
| `apps/web/lib/sse.ts` | SSE consumption with reconnect, partial-event tolerance, and disconnect handling |
| `apps/web/lib/format.ts` | Citation formatting, timestamps, freshness wording |
| `apps/web/middleware.ts` | Route protection |
| `apps/web/styles/globals.css` | Design tokens, colour, spacing, typography |
| `apps/web/styles/high-contrast.css` | High-contrast and forced-colours support |

**Accessibility and tests**

| Path | Responsibility |
| --- | --- |
| `apps/web/e2e/chat.spec.ts` | Ask → stream → cite → open passage → feedback |
| `apps/web/e2e/refusal.spec.ts` | Refusal rendering and suggested refinements |
| `apps/web/e2e/history.spec.ts` | Conversation create, rename, delete, resume |
| `apps/web/e2e/admin.spec.ts` | Reindex trigger, config activation, rollback, trace inspection |
| `apps/web/e2e/accessibility.spec.ts` | Automated accessibility assertions plus a keyboard-only journey |
| `apps/web/components/**/*.test.tsx` | Component tests |
| `apps/web/playwright.config.ts` | E2E configuration |
| `apps/web/axe.config.ts` | Accessibility rule configuration |

**Deployment**

| Path | Responsibility |
| --- | --- |
| `infra/containers/Dockerfile.web` | Production web image (built in phase 1, configured here) |
| `infra/terraform/web.tf` | Web hosting, CDN, environment configuration |

### 8.4 What this phase does

1. Builds the chat thread with incremental rendering and a scroll behaviour that does not fight
   the user when they scroll up mid-stream.
2. Renders inline citations as distinguishable chips, with **provisional and verified states
   visually distinct** — the user must be able to tell that verification has not yet happened.
3. Makes every citation a two-click path to the highlighted passage in the source document,
   with a fresh access check at read time.
4. Renders refusal as a designed outcome: what was searched, the closest near misses, and
   concrete next steps.
5. Shows sources consulted with freshness timestamps, plus degraded-mode and re-indexing
   notices.
6. Implements feedback with an optional reason, stored against the exact trace.
7. Implements conversation history, rename, delete, export, and copy-with-citations.
8. Builds the admin console: source management, reindex, configuration staging with eval
   gating on activation, prompt rollback, eval runs with baseline diffs, trace inspection, and
   metrics.
9. Surfaces the content-gap backlog, so refusal data becomes a work list rather than a number.
10. Designs and verifies accessibility: keyboard-only journeys, focus management, live-region
    announcements for streaming completion, contrast, and reduced-motion support (FR-27).

### 8.5 How to verify it works

**Automated:**

| Check | How | Expected |
| --- | --- | --- |
| Chat journey | E2E | Question submitted, tokens appear progressively, answer completes, citations render |
| **Citation → passage** | E2E | Clicking a citation opens the correct source document with the correct passage highlighted |
| **Refusal journey** | E2E | Refusal renders with suggestions; no tokens or empty answer bubble shown |
| Provisional state | E2E | Citations are visually distinguished until the verification event arrives |
| Feedback persistence | E2E | Rating persists, survives reload, and appears in the admin trace view |
| History | E2E | Create, rename, delete, resume; a deleted conversation is not reachable |
| Streaming disconnect | E2E | Mid-stream disconnect shows a recoverable error rather than a silent stall |
| Expired session | E2E | 401 triggers re-auth; the draft question is preserved |
| Admin reindex | E2E | Trigger updates status, then completes |
| Config activation | E2E | A staged config requires activation; a failing eval blocks activation |
| **Rollback** | E2E | Rollback restores the previous behaviour in the live chat |
| Accessibility | Automated assertions | No serious violations on the chat and admin surfaces |
| **Keyboard-only journey** | Scripted journey | A question is asked and a cited passage opened without a mouse |
| Layout resilience | Viewport checks | 360 px, 768 px, and desktop widths remain usable |

**Manual:**

1. **Trust test.** Find one answer you believe is wrong or weakly supported. Follow its
   citations. Can you determine, quickly and without effort, whether the source supports it? If
   this takes more than a few seconds, provenance is not working and the UI needs work
   regardless of what the tests say.
2. **Refusal test.** Ask something unanswerable. Does the refusal read as informative and
   normal, or as a failure? Show it to someone unfamiliar with the product; if they report it
   as broken, it is broken.
3. **Sceptical-user test.** Ask a user who knows they should not trust the answer whether the
   product makes it easy to verify. If they say they would rather just ask a colleague, the
   citations are not earning their place.
4. **Stream interruption.** Start a long answer and navigate away and back. Nothing should be
   lost or duplicated.
5. **Keyboard and screen reader.** Complete a full question-and-citation journey with a screen
   reader. Verify streaming completion is announced, not silently appended.
6. **Admin usability.** Using only the admin console, find a bad answer from the metrics,
   locate its trace, identify the responsible stage, propose a configuration change, evaluate
   it against the baseline, and roll it back. If that loop is not smooth, operators will not
   improve the system.

### 8.6 Gate — all must pass

- [ ] Ask → stream → cite → open the correct highlighted passage works end to end
- [ ] Refusal is informative, well-designed, and free of empty answer states
- [ ] Provisional and verified citations are visually distinguishable
- [ ] Feedback persists and is visible against the exact trace in the admin console
- [ ] Admin loop complete: metrics → trace → config change → eval comparison → rollback
- [ ] Keyboard-only journey passes; automated accessibility checks report no serious violations
- [ ] All responsive viewports usable
- [ ] Trust test passed with a person unfamiliar with the product
- [ ] Streaming interruption and session expiry handled gracefully
- [ ] E2E suite green and required in CI

### 8.7 Risks specific to this phase

| Risk | Response |
| --- | --- |
| Trusting a green E2E suite over the manual trust test | The manual test is the gate. Automated checks confirm mechanics, not comprehension |
| Citation metadata rendered too faintly to be useful | Make source title and freshness prominent. Provenance that requires effort is provenance that will not be used |
| The UI implies certainty the pipeline does not have | Provisional states, freshness notices, and degraded-mode notices must be visible. Polished presentation of an uncertain answer is worse than an obviously uncertain one |
| Accessibility added at the end | Keyboard and live-region requirements are in the component specs from the start, with a scripted journey as a gate item |
| Scope creep toward agentic features | Actions such as "draft an email" or "create a ticket" are outside PRD §3. Keep the surface read-only and Q&A; if a user asks for an action, log it as a demand, not a feature |
| Admin console under-invested | It is the only path to improving quality after launch. The §8.5 manual loop is a gate, not a nice-to-have |
| Refusal frustrating users into distrust | Track refusal rate and user sentiment after pilot. A high refusal rate on answerable questions is a retrieval bug to fix, not a safety feature to defend |

---

## 9. Open questions that block phases

Answering these late forces rework. Each is marked with the phase that becomes expensive if the
answer arrives afterwards.

| # | Question | Needed by | If unanswered |
| --- | --- | --- | --- |
| OQ-1 / AQ-6 | Which systems and file types are actually in the corpus? | **Phase 2** | Build parsers speculatively and discover gaps against real documents in the worst place — mid-ingestion |
| AQ-1 | Embedding dimension and column strategy | **Phase 3** | `A5`-sized corpus: migration is a long re-embed with a dual-write exercise |
| AQ-2 / OQ-2 | Does the IdP expose group and ACL claims in the token? | **Phase 4** (already built in 3) | Fall back to corpus-wide access for v1 with the limitation signed off. This is a security-posture decision, not a default |
| AQ-3 / OQ-5 | Approved LLM and embedding providers; data-processing constraints | **Phase 3** | Hosted provider behind the ports. Choosing later means re-running the entire phase-3 baseline |
| AQ-8 / OQ-6 | Self-hosted model required for data residency? | **Phase 3** | Architecture holds, but the phase-3 schedule and cost model change substantially |
| AQ-4 / OQ-4 | Who labels the golden set; how many questions already exist? | **Phase 2** (start), **Phase 5** (200+) | Quality claims become unfalsifiable, and no release gate can be meaningful. This is the highest schedule risk in the plan |
| OQ-3 | Corpus-only grounding, or may general knowledge be used? | **Phase 5** | Assume corpus-only, fail closed. The stricter default is the safer one to start from |
| OQ-7 | Expected daily volume and per-answer cost ceiling | **Phase 5** | `A7` budget used; alert thresholds arbitrary |
| AQ-7 | Trace retention and who may read traces | **Phase 4** | 90 days, ops-only. Getting this wrong in either direction is a compliance problem |
| OQ-8 / A8 | English-only for v1? | **Phase 2** | English-only. A late language requirement changes the lexical index |
| OQ-9 | Existing search, chat, or ingestion code to build on | **Phase 1** | Duplicate effort, or an unnecessary greenfield build |
| AQ-10 | Does the corpus include structured or tabular data needing dedicated retrieval? | **Phase 2** | Text-only ingestion; tables render as text. Degrades answer quality on data-heavy content |
| OQ-10 | Is this Q&A only, or also workflow actions? | **Phase 6** | Q&A only per PRD §3. Late change re-opens the threat model in architecture §8.3 |

---

## 10. Cross-cutting concerns

Where each recurring concern lives across the six phases, so it is never accidentally
single-phase work.

| Concern | P1 | P2 | P3 | P4 | P5 | P6 |
| --- | --- | --- | --- | --- | --- | --- |
| **Ports and provider abstraction** | Define | — | Implement real adapters | — | — | — |
| **Observability** | Spans, content-free logging | Ingestion metrics | Index health | Audit records, traces | Stage spans, cost | Metrics dashboard |
| **Configuration** | Settings object | Chunker version | Embedding model | Versioned config with rollback | Prompt registry | Admin UI |
| **Evaluation** | Harness on empty index | `seed-v1` | Retrieval metrics, baseline | Red-team baseline | Generation metrics, release gates | Surfaced in admin |
| **Security** | Dependency rules, log redaction | Injection flagging, fail-closed ACL | ACL predicate in queries | RLS, secrets, rate limits, red-team | Gate, citation verification, tool-free | Route protection, role gating |
| **Testing** | Unit/integration skeletons | Parser/chunker units | Retrieval integration | Security suites | Quality and performance suites | E2E, accessibility |
| **Documentation** | ADRs | Corpus inventory | Embedding ADR, eval baseline | Threat model, guardrail status | Runbooks, content gaps | Operator docs |

**Standing rule:** a concern absent from a phase's gate will not be done. If a phase's gate
does not mention cost, traces, or documentation for that phase's work, add it.

---

## 11. Requirement coverage by phase

Every **M** and **S** requirement mapped to the phase that delivers it. Nothing is unassigned;
nothing is assigned to a phase that cannot verify it.

| Requirement | Phase | Gate verified in |
| --- | --- | --- |
| FR-1, FR-2, FR-3 | 2 | 2 |
| FR-4, FR-5 | 2 | 2 |
| FR-6 | 3 | 3 |
| FR-7 | 3 | 3 |
| FR-8 | 3 | 3 |
| FR-9, FR-16, FR-17 | 5 | 5 |
| FR-10, FR-15 | 5 | 5 |
| FR-11, FR-12, FR-13, FR-14 | 5 | 5 |
| FR-20, FR-21 | 6 | 6 |
| FR-22, FR-23, FR-26, FR-28 | 6 | 6 |
| FR-24 | 5 (write), 6 (surface) | 5, 6 |
| FR-25 | 6 | 6 |
| FR-27 | 6 | 6 |
| FR-29 | 1 (mechanism), 4 (hardening), 6 (UX) | 1, 4, 6 |
| FR-30 | 6 | 6 |
| FR-31 | 4 (mechanism), 6 (surface) | 4, 6 |
| FR-32 | 1 (harness), 3 (retrieval), 5 (generation) | 1, 3, 5 |
| FR-33 | 4 (write), 6 (view) | 4, 6 |
| FR-34 | 5 (compute), 6 (surface) | 5, 6 |
| FR-35 | 4 | 4 |
| FR-36 | 4 | 4 |
| FR-38 | 3 (predicate), 4 (hardening) | 3, 4 |
| FR-39 | 2 (flagging), 4 (primitives), 5 (in situ) | 2, 4, 5 |
| FR-40 | 4 | 4, 5 |
| FR-41 | 4 | 4 |
| FR-42 | 4 (harness), 5 (real run) | 4, 5 |
| FR-43 | 4 | 4 |
| NFR-1, NFR-2, NFR-3 | 5 | 5 |
| NFR-4, NFR-5 | 3 | 3 |
| NFR-6 | 3 | 3 |
| NFR-7 | 2 (pipeline), 5 (verified end to end) | 2, 5 |
| NFR-8 | 5 (degradation), 6 | 5 |
| NFR-9 | 3 (retrieval), 5 (reranker) | 3, 5 |
| NFR-10 | 5 | 5 |
| NFR-11, NFR-12 | 3 (retrieval gate), 5 (generation gate) | 3, 5 |
| NFR-13 | 1 (fields), 5 (populated) | 5 |
| NFR-14 – NFR-17 | 4 | 4 |
| NFR-18 | 1 | 1 |
| NFR-19 | 3 (embedding cost), 5 (per answer) | 5 |
| NFR-20 | 1 (CI), all phases | every gate |

**Requirements deliberately not covered:** FR-18 and FR-19, both priority **C** — see §12.

---

## 12. Deliberately not built in these six phases

Stating this explicitly prevents the most likely form of scope creep, since each item is
individually appealing.

| Item | Why deferred | Where it would attach |
| --- | --- | --- |
| FR-18 self-consistency verification | Adds latency and cost per answer; unproven benefit before the basics are measured | A second generation pass in `generate` |
| FR-19 multi-hop decomposition | High complexity, high failure modes; unproven necessity for this corpus | A decomposition stage before retrieval |
| Agentic tool use | PRD §3 non-goal; converts injection from bad text into bad action and invalidates the threat model | Would require a full security re-review |
| Fine-tuning | PRD §3 non-goal; changes the problem rather than solving it | Post-launch, gated on eval evidence that the remaining bottleneck is the model |
| Graph RAG | Large surface, hard to evaluate | Only if eval data shows multi-hop failures decomposition cannot fix |
| A RAG framework | Architecture §20.3; the pipeline is the product | Would live behind the orchestrator interface only |
| Multi-tenant isolation | PRD §3 non-goal, `A3` | `tenant_id` column and RLS predicate before the first second tenant — not after |
| Multilingual retrieval | `A8`, English-only for v1 | Per-language lexical config and language-aware embeddings |
| Voice, image, and file input | PRD §3 non-goal | New ingestion and input pipelines |
| Writing back to source systems | PRD §3 non-goal, `A10` | New authorization and audit surface |

Each of these is fine work. None of them is v1 work, and the gates in §3.6 through §8.6 are
the mechanism that keeps that true.

---

## 13. Verification tooling summary

Every phase depends on these. Investing in them early is what makes the gates cheap.

| Tool | Purpose | First needed |
| --- | --- | --- |
| Unit and integration test runner | The bulk of automated verification | Phase 1 |
| Dependency-rule test | Enforces package boundaries and provider-SDK isolation | Phase 1 |
| Log-hygiene CI guard | Enforces NFR-16 | Phase 1, hardened in 4 |
| Secret scanner | Credential hygiene | Phase 1 |
| Eval harness with baseline diffing | The NFR-12 release gate | Phase 1, populated in 3 and 5 |
| Chunk inspection tool | Human review of chunk quality | Phase 2 |
| Ingestion CLI | Idempotency, incremental updates, deletion | Phase 2 |
| Index health report | Coverage, dimension, orphans | Phase 3 |
| Threshold calibration tool | Gate operating-point selection | Phase 5 |
| `ask` CLI | End-to-end verification before the UI exists | Phase 5 |
| Performance harness | TTFT, stage latency, throughput, cost | Phase 3 and 5 |
| Red-team suite | Injection and jailbreak pass rates | Phase 4 |
| E2E suite | User journeys | Phase 6 |
| Automated accessibility checks | WCAG 2.1 AA baseline | Phase 6 |
| Published baselines in `evals/baselines/` | Every comparison in this plan | Phase 3 |

**Standing verification habits, in order of value per unit of effort:**

1. Every change runs the full eval suite plus the untouched holdout slice.
2. Every trace is readable enough to explain an answer without asking its author.
3. Every gate has a named command or a named artefact, not a description.
4. Manual review of raw chunks and real answers is never replaced by a metric.
5. If a check cannot be run, it does not pass.

---

## 14. Change log

| Version | Date | Change |
| --- | --- | --- |
| v0.1 | 2026-10-02 | Initial six-phase implementation plan derived from architecture.md v0.1 and PRD v0.1 |

> This plan inherits all PRD assumptions `A1`–`A12`, PRD open questions `OQ-1`–`OQ-12`, and
> architecture questions `AQ-1`–`AQ-10`. The phase boundaries above are deliberately chosen so
> that the riskiest unknowns — corpus shape, corpus size, IdP claims, and labelled evaluation
> data — are forced to surface in phases 2 and 3, before generation depends on them. Changing
> those phases is far cheaper than changing phases 5 and 6.
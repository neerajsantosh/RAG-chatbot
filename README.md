# RAG Chatbot

A Retrieval-Augmented Generation chatbot over an internal document corpus. Answers are
constrained to retrieved passages and carry citations back to the exact source text.

> **Status: Phase 1 of 6 implemented.** See [Phase status](#phase-status) below and
> [`docs/implementation.md`](docs/implementation.md) for what each phase delivers and how it is
> verified. The system currently runs end to end on deterministic fake model adapters; there is
> no corpus and no answer generation yet.

## Documentation

| Document | Purpose |
| --- | --- |
| [`docs/PRD.md`](docs/PRD.md) | Requirements, metrics, risks, assumptions register |
| [`docs/architecture.md`](docs/architecture.md) | Components, data flows, storage, security model |
| [`docs/implementation.md`](docs/implementation.md) | Six phases, files per phase, verification gates |
| [`docs/adr/`](docs/adr/) | Architecture decision records |

> The product requirements were reconstructed from an empty source document. Assumptions
> `A1`–`A12` in PRD §14 are **not yet validated**. Correct them before relying on any estimate.

## Quick start

```bash
git clone <repo> rag-chatbot
cd rag-chatbot

# Linux/macOS
make bootstrap && make up

# Windows (PowerShell)
make bootstrap; make up
```

`make bootstrap` installs dev dependencies and copies `.env.example` to `.env`.
`make up` builds images and starts Postgres, the API, the worker, and the web app.

| Service | URL |
| --- | --- |
| API | http://localhost:8000 |
| OpenAPI docs | http://localhost:8000/docs |
| Readiness (checks the database) | http://localhost:8000/readyz |
| Web | http://localhost:3000 |

### Running without Docker

The API and worker run against the fake model adapters with no provider account and no cost.

```bash
make bootstrap
make run-api      # uvicorn, http://localhost:8000
make run-worker   # queue consumer
make run-web      # Next.js, http://localhost:3000
```

The database is optional in Phase 1. `/healthz` is always served; `/readyz` returns `503`
when the database is unreachable. Tests that need a live database are marked and skipped
automatically.

## Verification

```bash
make check          # lint + typecheck + tests
make test           # full test suite
make lint           # ruff
make typecheck      # mypy, strict
make eval           # eval harness (reports zeros against an empty index)
make check-secrets  # credential scan
make check-log-hygiene
```

The Phase 1 gate is `make check` plus the checks in
[`docs/implementation.md` §3.5](docs/implementation.md) — including two that are deliberately
negative: the dependency-rule test and the log-hygiene guard must **fail** when violated.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Project setup | **Implemented** |
| 2 | Loading & chunking | Not started |
| 3 | Embedding & vector store | Not started |
| 4 | Guardrails | Partially scaffolded (hooks in place, enforcement in phase 4) |
| 5 | Retrieval + LLM answer | Not started |
| 6 | UI | Scaffolded only |

## Layout

```
rag-chatbot/
├─ apps/
│  ├─ api/            FastAPI service: auth, chat, admin, traces, feedback
│  ├─ worker/         Queue consumer for ingestion, eval and retention jobs
│  └─ web/            Next.js chat and admin console
├─ packages/
│  ├─ core/           Settings, secrets, logging, ids, errors, clock, retry, spans
│  ├─ llm/            Model ports (ChatModel, Embedder, Reranker) and adapters
│  ├─ storage/        Database engine, repository ports, migrations, RLS
│  └─ eval/           Evaluation harness, retrieval metrics, regression gate
├─ evals/             Versioned datasets and published baselines
├─ infra/             Container builds and Terraform
├─ tools/             CLIs and repository guards
├─ tests/             Unit, integration, security and dependency-rule tests
└─ docs/              PRD, architecture, implementation plan, ADRs, runbooks
```

### Dependency rule

`apps → packages` only. Packages never import from apps. A provider SDK may only be imported
inside `packages/llm/adapters/`. Both rules are enforced by
`tests/test_dependency_rules.py` and fail CI — they are what make model providers swappable
(NFR-18) and make the "content never enters the logs" rule structural (NFR-16).

## Configuration

`.env.example` is the configuration contract; every key is validated at startup by
`core.config.settings`. Secrets belong in the managed secret store
(`core/config/secrets.py`), never in a file. `make check-secrets` fails on committed
credentials.

## Licence

Proprietary. Internal use only.
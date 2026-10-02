# Product Requirements Document — RAG Chatbot

| Field | Value |
| --- | --- |
| Document status | Draft (v0.1) |
| Owner | TBD |
| Last updated | 2026-10-02 |
| Source | `docs/problemstatement.txt` (file was empty — all content below is inferred from the repository name `RAG-chatbot` and must be validated) |

> **Read this first.** `docs/problemstatement.txt` contained no text. This document is a
> best-effort reconstruction of a plausible Retrieval-Augmented Generation (RAG) chatbot
> product. Everything that could not be derived from the (empty) source is tagged
> **`[ASSUMPTION]`** or listed in [Open Questions](#12-open-questions). Review, correct, and
> delete assumptions before this document is used for planning or estimation.

---

## 1. Problem statement

`[ASSUMPTION]` Internal users cannot get trustworthy answers from a plain LLM chatbot because
the model has no access to company-specific, frequently-updated knowledge. Responses are
hallucinated, unverifiable, and require the user to already know which document holds the
answer.

The product must let a user ask a natural-language question and receive an answer that is
(a) grounded in a controlled corpus of internal documents and (b) accompanied by citations back
to the exact source passage.

### Why now

- `[ASSUMPTION]` Existing internal documentation is large enough that manual keyword search has
  low recall for multi-hop or synonym-heavy questions.
- `[ASSUMPTION]` LLM inference cost has fallen far enough that per-question retrieval plus
  generation is affordable at expected internal traffic.

---

## 2. Goals and success metrics

| # | Goal | Metric | Target `[ASSUMPTION]` |
| --- | --- | --- | --- |
| G1 | Answers are grounded | Groundedness score from LLM-as-judge on answer+citations | ≥ 90% of answers rated grounded |
| G2 | Answers are attributable | Answers containing at least one resolvable citation | 100% |
| G3 | Low hallucination | Unsupported-claim rate from human review sample | ≤ 5% |
| G4 | Fast enough to feel conversational | Time to first token (p50 / p95) | ≤ 2 s / ≤ 6 s |
| G5 | Retrieval works | Recall@5 of gold supporting passages (eval set) | ≥ 80% |
| G6 | Adopted | Weekly active internal users | 60% of target org within 3 months |
| G7 | Safe | Prompt-injection and jailbreak pass rate in red-team suite | ≤ 2% |

**Anti-metric:** answer length or verbosity. Do not optimise for user-perceived quality alone;
a confidently wrong answer is a worse outcome than a refusal.

---

## 3. Non-goals (v1)

- Writing/editing source documents (read-only access to the corpus).
- Agentic tool use, code execution, or external API calls from inside an answer.
- Fine-tuning or training a custom model.
- Multi-tenant isolation or per-customer data residency.
- Voice, image, or file-upload input.
- Full production compliance certification (SOC 2, HIPAA) — architecture should not preclude it.

---

## 4. Personas

| Persona | Need |
| --- | --- |
| **P1 — Analyst** `[ASSUMPTION]` | Answers to "why" questions across many documents, with citations to verify. |
| **P2 — Support agent** `[ASSUMPTION]` | Fast lookup of policy/product answers to paste into a customer reply. |
| **P3 — Engineer/Operator** `[ASSUMPTION]` | Configures corpus sources, monitors quality, fixes retrieval failures. |
| **P4 — Security/Compliance reviewer** `[ASSUMPTION]` | Confirms the system does not leak documents the user may not see. |

---

## 5. User stories

**Retrieval and answering**
1. As a user, I ask a question in plain language so that I do not need to know which document holds the answer.
2. As a user, I see the citations for each claim so that I can verify the answer myself.
3. As a user, I click a citation and jump to the highlighted source passage so that I can read it in context.
4. As a user, I get an explicit "I don't know" answer with suggestions when the corpus has no answer, so that I know the system is not guessing.
5. As a user, I can see which sources were searched so that I can judge coverage.

**Corpus and freshness**
6. As an operator, I add or remove a document source (files, URL, repo, wiki) so that the corpus reflects current knowledge.
7. As an operator, new or changed documents become searchable within a defined SLA without a full rebuild.
8. As an operator, I trigger a re-index and see progress and failures so that I can fix ingestion problems.

**Conversation**
9. As a user, follow-up questions work in context so that I can refine an answer incrementally.
10. As a user, I can start a new conversation or clear context so that old context does not pollute a new question.

**Trust and safety**
11. As a user, I only see documents I am permitted to see so that sensitive data is not leaked.
12. As an operator, I review a log of questions, retrieved passages, and answers so that I can audit and debug quality.

---

## 6. Functional requirements

Priority: **M** = must have for v1, **S** = should, **C** = could.

### 6.1 Ingestion and indexing
| ID | Requirement | Pri |
| --- | --- | --- |
| FR-1 | Connectors for at least one corpus type (file upload, web/URL crawl, or wiki export). `[ASSUMPTION]` | M |
| FR-2 | Parse documents to text with headings and structure preserved; extract metadata (title, source URI, author, timestamps, ACL tags). | M |
| FR-3 | Chunk documents with a configurable strategy; store chunk text plus embedding and parent-document reference. | M |
| FR-4 | Idempotent re-indexing — re-ingesting unchanged content must not create duplicates. | M |
| FR-5 | Incremental updates: added/modified documents become searchable within the freshness SLA (§7.2); deleted documents are removed from the index. | M |
| FR-6 | Ingestion job dashboard with status, counts, and per-document errors. | S |
| FR-7 | Support for a document-level metadata filter used at retrieval time. | S |

### 6.2 Retrieval and generation
| ID | Requirement | Pri |
| --- | --- | --- |
| FR-8 | Hybrid retrieval combining dense vector search with lexical/BM25 search. | M |
| FR-9 | Reciprocal Rank Fusion or equivalent to merge the two result lists. | M |
| FR-10 | Configurable top-k and a similarity/score threshold below which the system refuses to answer. | M |
| FR-11 | Prompt assembly that constrains the model to answer only from supplied context and to cite chunk IDs. | M |
| FR-12 | Post-generation citation validation: drop or flag citations that do not appear in the supplied context. | M |
| FR-13 | Return answer, ordered citations with source title and snippet, and the chunks actually used. | M |
| FR-14 | Streaming responses token-by-token. | M |
| FR-15 | Refusal/insufficient-evidence path with suggested refinements or related questions. | M |
| FR-16 | Reranking pass (cross-encoder or LLM) over the top candidates before generation. | S |
| FR-17 | Query rewriting to expand follow-up questions using conversation history. | S |
| FR-18 | Self-consistency / answer verification step for high-risk question classes. | C |
| FR-19 | Multi-hop decomposition for questions spanning several documents. | C |

### 6.3 User experience
| ID | Requirement | Pri |
| --- | --- | --- |
| FR-20 | Single-page chat UI: message thread, streaming answer, citation chips, source panel. | M |
| FR-21 | Citation click opens the source document view with the cited passage highlighted. | M |
| FR-22 | Show which sources answered the question and their timestamps. | S |
| FR-23 | Copy answer with citations, and export the answer + sources to Markdown/PDF. | S |
| FR-24 | Positive/negative feedback control on each answer, stored against the exact retrieval trace. | M |
| FR-25 | Conversation history persisted per user, with rename and delete. | S |
| FR-26 | Display a visible "answering from internal documents" indicator plus a freshness notice. | S |
| FR-27 | Keyboard and basic accessibility conformance (WCAG 2.1 AA) for the chat surface. | S |
| FR-28 | Display input character/context limits and handle unanswerable input gracefully. | C |

### 6.4 Administration and operations
| ID | Requirement | Pri |
| --- | --- | --- |
| FR-29 | Authentication via the org's existing identity provider; user identity propagated for ACL filtering. | M |
| FR-30 | Corpus management UI/CLI: list sources, add source, re-index, delete source. | M |
| FR-31 | Tuning UI/API for chunk size, overlap, top-k, score threshold, and prompt template version. | M |
| FR-32 | Evaluation harness: curated question set with expected supporting documents; reports Recall@k, MRR, groundedness. | M |
| FR-33 | Structured logs and a searchable trace viewer for every query (question, retrieved chunks + scores, prompt version, model, latency, tokens, cost). | M |
| FR-34 | Analytics dashboard: volume, latency, feedback rate, refusal rate, top unanswered questions. | S |
| FR-35 | Prompt and configuration versioning with rollback. | S |
| FR-36 | Rate limiting and per-user quotas. | S |
| FR-37 | Content-management webhook trigger for re-index on content change. | C |

### 6.5 Safety and compliance
| ID | Requirement | Pri |
| --- | --- | --- |
| FR-38 | Enforce source-document access control at retrieval time using user identity claims. | M |
| FR-39 | Treat retrieved document content as untrusted data, never as instructions; isolate it in the prompt and neutralise instruction-like text. | M |
| FR-40 | PII/secrets detection and redaction in both indexed content and model output. | S |
| FR-41 | Configurable retention/deletion of conversations and logs. | S |
| FR-42 | Red-team test suite covering prompt injection, data exfiltration, and jailbreaks. | M |
| FR-43 | Provider data-retention settings configured to not train on our content. | M |

---

## 7. Non-functional requirements

### 7.1 Performance and capacity
| ID | Requirement |
| --- | --- |
| NFR-1 | TTFT p50 ≤ 2 s, p95 ≤ 6 s, measured server-side, excluding client render. `[ASSUMPTION]` |
| NFR-2 | Full non-streaming answer p95 ≤ 20 s. |
| NFR-3 | Retrieval stage alone p95 ≤ 1 s at the expected corpus size. `[ASSUMPTION]` |
| NFR-4 | Support ~500 concurrent chat sessions and ~50 requests/min sustained. `[ASSUMPTION]` |
| NFR-5 | Corpus up to ~1 M chunks / ~100 GB of source documents. `[ASSUMPTION]` |
| NFR-6 | Embedding re-index throughput ≥ 5 k chunks/min per worker. |

### 7.2 Freshness and reliability
| ID | Requirement |
| --- | --- |
| NFR-7 | Content freshness SLA: changed documents searchable within 15 min for webhook/connector-triggered updates. `[ASSUMPTION]` |
| NFR-8 | Availability 99.5% monthly, excluding planned maintenance. `[ASSUMPTION]` |
| NFR-9 | Retrieval degrades gracefully — if the vector store is unavailable, fall back to lexical search rather than failing the request. |
| NFR-10 | User's answer must never be silently generated without retrieved context; fail closed. |

### 7.3 Quality
| ID | Requirement |
| --- | --- |
| NFR-11 | A versioned evaluation set of ≥ 200 questions with labelled supporting passages, run on every retrieval or prompt change. `[ASSUMPTION]` |
| NFR-12 | No release that regresses Recall@5 by more than 3 points or groundedness by more than 5 points versus the baseline. |
| NFR-13 | Every answer carries a prompt version and model identifier for reproducibility. |

### 7.4 Security
| ID | Requirement |
| --- | --- |
| NFR-14 | All data in transit encrypted (TLS 1.2+); secrets stored in a managed secret store, never in config files or logs. |
| NFR-15 | Corpus and vector store encrypted at rest. |
| NFR-16 | No document content in application logs; log references and IDs instead. |
| NFR-17 | Retention policy enforced for prompts, completions, and traces. |

### 7.5 Maintainability and cost
| ID | Requirement |
| --- | --- |
| NFR-18 | Provider-agnostic interfaces for embedding and chat models so vendors can be swapped without touching application code. |
| NFR-19 | Cost per answer tracked and reported per model configuration. `[ASSUMPTION]` budget: ≤ $0.02/answer. |
| NFR-20 | Full test coverage of retrieval logic; unit + integration tests in CI. |

---

## 8. System architecture (proposed)

```
        ┌──────────────┐        ┌──────────────────────────────────────┐
        │  Chat UI     │  SSE   │  API service                         │
        │ (citations,  │◀──────▶│  auth · sessions · rate limit         │
        │  sources)    │  /chat  └───┬────────┬─────────┬────────┬───────┘
        └──────────────┘            │        │         │        │
                                    │        │         │        └─ trace store (logs, feedback)
                    ┌───────────────┘        │         └────────── prompt/config store
                    ▼                        ▼                    (versioned)
        ┌───────────────────┐    ┌─────────────────────┐
        │ Ingestion service │    │  RAG orchestrator   │
        │ connectors ·parse │    │  rewrite → retrieve │
        │ ·chunk ·embed    │    │  → rerank → prompt  │
        └─────────┬─────────┘    │  → generate → verify│
                  │              └──────┬──────────────┘
      ┌───────────┴───────────┐          │
      ▼                       ▼          ▼
┌───────────┐        ┌─────────────┐  ┌────────────┐
│Vector store│       │Lexical index│  │  LLM API   │
│(pgvector / │       │(BM25/ES)    │  │ + embedder│
│ managed)  │        └─────────────┘  └────────────┘
└───────────┘
   ┌──────────────────────────┐
   │ Object store (raw docs)  │
   └──────────────────────────┘
```

**Retrieval flow (per query)**
1. Load conversation context; rewrite the question into a standalone query if it is a follow-up. *(FR-17)*
2. Embed the query; run dense search and lexical search concurrently. *(FR-8)*
3. Fuse the ranked lists; apply metadata/ACL filters. *(FR-9, FR-38)*
4. Rerank top candidates; keep the top-k that clear the score threshold. *(FR-10, FR-16)*
5. If nothing clears the threshold → refusal path. *(FR-15)*
6. Assemble a grounded prompt with numbered chunks; generate a streamed answer citing chunk numbers. *(FR-11)*
7. Validate citations against supplied chunks; flag or strip invalid ones. *(FR-12)*
8. Persist the trace (question, chunks, scores, prompt version, model, latency, tokens). *(FR-33)*

**Technology stance `[ASSUMPTION]`** — deliberately boring and swappable:
- **Backend:** Python (FastAPI) for ingestion and RAG orchestration.
- **UI:** Next.js + React, TypeScript throughout.
- **Vector search:** PostgreSQL + pgvector initially; swap for a managed service only when scale demands it.
- **Lexical:** PostgreSQL full-text search to start; Elasticsearch/OpenSearch if quality demands it.
- **Models:** one hosted LLM plus one hosted embedding model behind provider-agnostic interfaces (NFR-18).
- **Everything stateful** behind a schema so a hosted vector DB is a config change, not a rewrite.

---

## 9. Data model (sketch)

```
Document(id, source_uri, title, author, created_at, updated_at,
         content_hash, acl_tags[], status, indexed_at)

Chunk(id, document_id, ordinal, text, token_count, embedding,
      heading_path, page_or_section, metadata jsonb)

Conversation(id, user_id, title, created_at, updated_at, deleted_at)

Message(id, conversation_id, role, content, created_at,
        trace_id, feedback enum('up','down',null))

Trace(id, message_id, question, retrieved_chunk_ids[], scores[],
      prompt_version, model, tokens_in, tokens_out, latency_ms, refused bool)
```

---

## 10. Success criteria for v1 (exit checklist)

- [ ] All FR marked **M** implemented and demoable end-to-end.
- [ ] Eval harness reports Recall@5 ≥ 80% and groundedness ≥ 90% on the versioned set.
- [ ] Red-team suite run; injection success rate ≤ 2% or mitigations documented.
- [ ] ACL test proves a user without access cannot retrieve or receive content from a restricted document.
- [ ] p50 TTFT ≤ 2 s at the load defined in NFR-4.
- [ ] Every answer traceable in the trace viewer within 5 minutes of asking.
- [ ] Content freshness SLA (NFR-7) verified with a timed re-index test.
- [ ] Pilot with ≥ 10 users for 2 weeks; feedback and unanswered-question review completed.

---

## 11. Milestones (indicative)

| Phase | Scope | Exit |
| --- | --- | --- |
| **M0 — Foundation** | Repo, CI, infra, provider-agnostic model interfaces, auth stub, schema. | Deployable no-op; eval harness runs on an empty set. |
| **M1 — Corpus** | One connector, parse, chunk, embed, index, re-index CLI. | A known document is retrievable by a known question. |
| **M2 — Answering** | Hybrid retrieval + fusion + grounded prompt + streaming + citations. | Answers end-to-end with citations; first eval numbers published. |
| **M3 — Safe & trustworthy** | ACL filtering, citation validation, refusal path, injection hardening. | ACL and red-team suites pass. |
| **M4 — Pilot-ready UX** | Chat UI, source viewer, feedback, history, admin/tuning. | 10 internal users can complete real tasks unaided. |
| **M5 — Hardening & launch** | Load test, observability, cost tuning, runbooks, freshness SLA verification. | Exit checklist in §10 signed off. |

---

## 12. Open questions

1. **Corpus** — which systems and file types are in scope for v1? Is any content streaming/incremental, or is it static documentation?
2. **Users and access control** — is the audience internal-only? Does the existing IdP expose group/ACL claims we can filter on, or is corpus-wide access acceptable for v1?
3. **Grounding tolerance** — should the system ever answer from general model knowledge, or is corpus-only (fail closed) mandatory?
4. **Evaluation data** — does a labelled question set with gold passages already exist, or must we create it (and who labels it)?
5. **Model providers** — is there an approved provider list and data-processing agreement constraint? Is a self-hosted open-weights model needed for data residency?
6. **Compliance regime** — must the product satisfy SOC 2 / HIPAA / GDPR, and by when? This can materially change §8.
7. **Budget** — expected daily question volume and per-answer cost ceiling?
8. **Language** — English only, or multilingual retrieval from day one?
9. **Existing assets** — is there an existing search system, chat widget, or ingestion code we should build on?
10. **Scope of "chatbot"** — pure Q&A, or also workflow actions (create ticket, draft email, book meeting)?
11. **Freshness semantics** — do sources need to reflect edits within minutes, or is daily sync acceptable?
12. **Definition of "answer"** — should answers be short extractive spans, or synthesised prose with citations?

---

## 13. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hallucination erodes trust faster than poor recall | Users stop trusting correct answers too | Fail closed; strict grounding prompt; citation validation; refusal path (FR-10, FR-12, FR-15) |
| Prompt injection via ingested documents | Data exfiltration, jailbreak | Treat corpus as untrusted data (FR-39); delimiter isolation; red-team suite (FR-42) |
| Retrieval quality plateaus | Answers feel useless despite good generation | Hybrid + reranking + eval harness first; tune on real traces before adding complexity |
| ACL gap in the retrieval layer | Sensitive data leak | Filter at query time inside the search call, not post-hoc in the UI; dedicated ACL tests |
| Corpus quality (stale, duplicated, contradictory docs) | Confident wrong answers | Content ownership, staleness indicators, unanswered-question analytics (FR-34) |
| Vendor lock-in and cost creep | Cost spikes, migration pain | Provider-agnostic interfaces (NFR-18), per-answer cost tracking (NFR-19) |
| Chunking strategy dominates quality | Suboptimal retrieval, hard to tune | Make chunking configurable and measured in the eval harness |
| Scope creep into agentic features | Schedule slip, new risk class | Explicit non-goals in §3; gate on evidence |

---

## 14. Assumptions register

Every `[ASSUMPTION]` above, consolidated for fast review and correction:

| # | Assumption | Why | Impact if wrong |
| --- | --- | --- | --- |
| A1 | Audience is internal employees/analysts. | Repo name gives no audience. | Changes auth, ACL, and UX scope substantially. |
| A2 | Corpus is internal documents (files/URLs/wiki). | RAG over unknown public data needs no ACL work. | Changes ingestion connectors and safety requirements. |
| A3 | Single-tenant, no per-customer data residency. | Simpler v1. | Adds isolation and routing work. |
| A4 | Existing corporate IdP is available for authentication. | Standard practice. | Adds auth build. |
| A5 | Corpus ~1 M chunks, ~50 req/min, ~500 concurrent. | Typical internal pilot. | Changes vector-store and cost model. |
| A6 | 15-minute content freshness target. | Balance between cost and staleness. | Continuous indexing raises cost. |
| A7 | Per-answer cost budget ~$0.02. | Common internal-tool budget. | Forces smaller models or caching. |
| A8 | English-only for v1. | Reduces retrieval complexity. | Multilingual retrieval and reranking add scope. |
| A9 | Hosted LLM + embedding provider is permitted. | Fastest path to v1. | Self-hosting adds GPU ops burden. |
| A10 | Read-only corpus; no write-back actions. | Keeps v1 focused. | Write actions add authz and audit scope. |
| A11 | No compliance certification required for v1. | Pilot-first posture. | Retrofitting audit/compliance is expensive. |
| A12 | Performance and quality targets in §2 are acceptable. | Industry-typical baselines. | Re-baselining changes scope and schedule. |

---

## 15. Appendix — terminology

| Term | Meaning |
| --- | --- |
| **Chunk** | The unit of text that is embedded and retrieved. |
| **Embedding** | Dense vector representation of chunk or query text. |
| **Grounded** | Every claim traceable to a supplied retrieved passage. |
| **Hybrid retrieval** | Dense vector search combined with keyword/BM25 search. |
| **Reranking** | Second scoring pass re-ordering candidates before generation. |
| **Recall@k** | Fraction of gold supporting passages present in the top k results. |
| **Groundedness** | Proportion of answers whose claims are supported by retrieved context. |
| **Fail closed** | Refuse to answer rather than answer without supporting context. |
| **Trace** | The full record of one query: context, chunks, scores, prompt, model, latency. |
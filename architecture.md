# Architecture Document: HDFC Mutual Fund RAG Chatbot

## 1. System Overview
A Retrieval-Augmented Generation (RAG) pipeline that answers user questions about HDFC mutual fund schemes by:
1. Ingesting 5 public Groww scheme pages
2. Chunking and embedding content with a local sentence‑transformers model
3. Storing vectors in a persisted ChromaDB
4. Retrieving top‑k relevant chunks for a user query
5. Generating a grounded answer via Groq's LLM (`qwen/qwen3.8-27b`)

---

## 2. High‑Level Components

| Component | Responsibility | Tech |
|-----------|----------------|------|
| **Ingestion** | Downloads the 5 Groww pages, extracts headings & body text, applies chunking, persists chunks to `data/chunks.txt` and vector store | Python, `requests`/`beautifulsoup`, custom chunker |
| **Embedding** | Converts each chunk and the user query into 384‑dim vectors using `sentence-transformers/all-MiniLM-L6-v2` (local, no API key) | `sentence‑transformers` |
| **Vector Store** | Stores chunk embeddings with metadata; persists on disk so ingestion runs once | ChromaDB (disk persistence) |
| **Retriever** | Takes a user query, embeds it, performs ANN search against ChromaDB, returns top‑k chunk IDs and similarity scores | ChromaDB query API |
| **LLM Gateway** | Sends the query + retrieved context to Groq, gets a natural‑language answer grounded in the context | Groq API, model `qwen/qwen3.8-27b` |
| **Env Config** | Holds `GROQ_API_KEY`; never committed to Git | `.env` file, `python‑dotenv` |

---

## 3. Data Flow

```
+--------+      +------------+      +----------------------+      +-------------------+
| User   | ---> | Ingestion  | ---> | Chunks (chunks.txt)  | ---> | ChromaDB (vectors)|
| Query  |      | (pages →   |      | + metadata           |      | + embeddings      |
+--------+      | chunks)    |      +----------------------+      +-------------------+
                |            |
                |            | embed (MiniLM-L6-v2)
                v            v
          +------------+   +--------------+
          |   Retriever|   |   LLM Gateway |
          +------------+   | (Groq, model) |
                          +--------------+
                                   |
                                   v
                            Answer (grounded)
```

**Step‑by‑step**

1. **Ingestion (once)**: Script reads the 5 Groww URLs, extracts headings, body text, and scheme metadata. Text is split into chunks (see §4). Each chunk receives metadata: `scheme_name`, `category`, `url`, `heading_level`. All chunks are written to `data/chunks.txt` for inspection. Chunks are embedded with `all-MiniLM-L6-v2` and stored in ChromaDB (`chroma_db/`). Persistence means this step need not repeat on restart.

2. **Query (every user turn)**:
   - User types a question (e.g., “Which HDFC fund has the highest 1‑year return?”).
   - The question is embedded with the **same** `all-MiniLM-L6-v2` model → 384‑dim vector.
   - Retriever queries ChromaDB for the top‑k most similar chunks (default k=4).
   - Retrieved chunk texts + metadata are concatenated into a context block.
   - The context + user question are sent to Groq (`qwen/qwen3.8-27b`) as a prompt.
   - Groq returns a natural‑language answer that cites the source chunks.

---

## 4. Chunking Strategy (as specified in PRD)

The AI agent must decide **before** writing code. Based on the 5 Groww pages (each a structured scheme description), a sensible strategy is:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Chunk size** | 512 tokens (≈ 800‑900 characters) | Fits within MiniLM‑L6’s effective context and keeps each chunk semantically complete (a heading + a few paragraphs). |
| **Overlap** | 64 tokens (≈ 100 chars) | Guarantees no information is lost at chunk boundaries, especially for headings that may span the split. |
| **Metadata per chunk** | - `scheme_name` (e.g., "HDFC Large Cap Fund")<br>- `category` (Large Cap / Flexi Cap / ELSS / Small Cap / Balanced Advantage)<br>- `url` (source Groww page URL)<br>- `heading` (the heading hierarchy, e.g., "Large Cap Objective") | Enables downstream filtering (e.g., "only show me ELSS tax‑saver info") and human‑readable inspection. |
| **Output** | All chunks saved to `data/chunks.txt` in a simple key‑value format: <br>`CHUNK_ID|SCHEME|CATEGORY|URL|HEADING|TOKEN_TEXT` | The file is human‑readable and can be inspected before vectorisation. |

The agent should **inspect the actual Groww HTML** first, verify that headings (`<h2>`, `<h3>`) separate scheme sections, and then finalize the exact token size/overlap after a quick run on a sample page.

---

## 5. Technology Stack

| Layer | Framework / Library |
|-------|----------------------|
| **Web scraping / page parsing** | Python `requests` + `beautifulsoup4` |
| **Chunking** | Custom Python (regex/beautifulsoup based) |
| **Embedding model** | `sentence‑transformers` — `all-MiniLM-L6-v2` (local, 384‑dim) |
| **Vector DB** | ChromaDB (`chromadb` Python client, persistence `./chroma_db`) |
| **LLM** | Groq HTTP API, model `qwen/qwen3.8-27b` |
| **Env management** | `python‑dotenv`; `.env` file with `GROQ_API_KEY` |
| **CLI / demo UI** | Simple `argparse`-driven script or Streamlit one‑page app (optional) |
| **Packaging** | `requirements.txt`, project root with `pyproject.toml` (optional) |

---

## 6. File Layout (consistent with PRD)

```
RAG-chatbot/
├── .env                  # GROQ_API_KEY=... (gitignored)
├── chroma_db/            # Persisted ChromaDB (created after first ingestion)
├── data/
│   └── chunks.txt        # Human‑readable chunks + metadata (generated by ingest.py)
├── ingest.py             # Reads Groww pages → chunks → saves chunks.txt + embeds → ChromaDB
├── query.py              # CLI: ask question → retrieve → generate answer via Groq
├── architecture.md       # This document
└── PRD.md                # Product requirements
```

---

## 7. Key Design Decisions & Rationale

- **Same embedding model for chunks & query** – Guarantees vector space alignment; no mismatch between stored embeddings and query embeddings.
- **Local embedding (MiniLM-L6-v2)** – Zero cost, no API key, fast enough for a class demo with ≤ 5 × ~30 chunks.
- **ChromaDB disk persistence** – Ingestion runs once; restarting the chatbot re‑uses the same vector store without re‑processing the Groww pages.
- **Groq API key in `.env`** – Follows security best practice; key never appears in code or Git.
- **Chunk metadata** – Enables category‑filtered retrieval (e.g., user asks about ELSS and the system only returns ELSS chunks).
- **Inspectable `chunks.txt`** – Transparent data pipeline; students can open the file and see exactly what text + metadata will be embedded.

---
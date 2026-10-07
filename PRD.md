# Product Requirements Document: RAG Chatbot for HDFC Mutual Funds

## 1. Project Overview
Building a Retrieve-Augmented Generation (RAG) chatbot for a class demo, focused on HDFC mutual fund schemes. The system will allow users to query HDFC fund information and receive grounded answers using retrieved context.

**Target AMC**: HDFC  
**Schemes Covered** (5 Direct–Growth plans):
1. Large Cap: HDFC Large Cap Fund Direct Growth
2. Flexi Cap: HDFC Equity Fund Direct Growth
3. ELSS: HDFC ELSS Tax Saver Fund Direct Plan Growth
4. Small Cap: HDFC Small Cap Fund Direct Growth
5. Balanced Advantage (Hybrid): HDFC Balanced Advantage Fund Direct Growth

**Data Source**: 5 public Groww pages (provided above)

---

## 2. Tech Decisions (Class-Approved)

### 2.1 Embedding Model
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Runs**: Locally, no API key required
- **Output**: 384-dimensional vectors
- **Usage**: Both chunk embeddings and user-query embeddings use this identical model

### 2.2 Chunking Strategy
The AI agent (Cursor, OpenCode, or Claude Code) decides the strategy **before** writing code. Requirements:
- Inspect the source data (the 5 Groww pages) and propose a strategy
- Justify why the strategy suits this data
- Specify:
  - Chunk size
  - Overlap amount
  - Metadata retained per chunk (e.g., scheme name, category, URL, heading hierarchy)
- **Output**: All chunks saved to a readable `.txt` file for inspection

### 2.3 Vector Database
- **DB**: ChromaDB
- **Persistence**: Disk-based
- **Workflow**: Ingestion runs once; vector store persists across restarts

### 2.4 LLM for Data Retrieval
- **Provider**: Groq
- **API Key**: Stored in `.env` file, never committed to Git
- **Setup**: Obtain key from https://console.groq.com/keys
- **Model**: `qwen/qwen3.8-27b`
- **Role**: Generates answers using retrieved context

---

## 3. Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-1 | System must ingest the 5 HDFC Groww scheme pages |
| FR-2 | Chunks must be embeddable using `all-MiniLM-L6-v2` (384 dims) |
| FR-3 | Vector store (ChromaDB) must persist to disk between runs |
| FR-4 | User query is embedded using the same model and retrieved against stored vectors |
| FR-5 | Groq LLM (`qwen/qwen3.8-27b`) generates answers grounded in retrieved context |
| FR-6 | API key from `.env` is used for Groq calls; key not in repository |
| FR-7 | Chunk metadata includes: scheme name, category, URL, and section heading |
| FR-8 | Inspectable `.txt` output of all chunks is generated alongside the vector DB |

---

## 4. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Embedding model runs entirely locally (no network for embedding generation) |
| NFR-2 | Vector DB persistence: ingestion executed once; zero re-embedding on restart |
| NFR-3 | Groq API key managed via environment variables (`.env`); excluded from Git |
| NFR-4 | System suitable for class demo: fast startup, clear observable chunks |
| NFR-5 | Output `.txt` chunks are human-readable and well-structured |

---

## 5. Development Milestones

1. **Inspect & Chunk**: Read the 5 Groww pages → propose chunking strategy → save chunks to `data/chunks.txt`
2. **Embed & Store**: Generate 384-dim embeddings → persist to ChromaDB (`chroma_db/`)`
3. **Retrieval Loop**: User question → embed → top-k similarity → pass context to Groq LLM → return answer
4. **Demo Polish**: One-shot CLI or simple UI; show chunk inspection; demonstrate persistence

---

## 6. File Layout (Planned)

```
RAG-chatbot/
├── .env                  # GROQ_API_KEY=... (gitignored)
├── chroma_db/            # Persisted ChromaDB files
├── data/
│   └── chunks.txt        # Human-readable chunks + metadata
├── ingest.py             # Reads Groww pages → chunks → saves chunks.txt + embeds → ChromaDB
├── query.py              # CLI: ask question → retrieve → generate answer via Groq
└── PRD.md                # This document
```
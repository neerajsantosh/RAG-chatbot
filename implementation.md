# Implementation Roadmap: HDFC Mutual Fund RAG Chatbot

The following six phases translate the architectural decisions from `architecture.md` into concrete development tasks. Each phase lists objectives, key steps, and typical code structure.

---

## Phase 1 – Project Setup

**Goal** Get the repo ready: install dependencies, configure environment, add git‑ignored files.

| Step | Action |
|------|--------|
| 1.1 | Create a virtual environment: `python -m venv .venv` and activate it. |
| 1.2 | Install required packages (see `requirements.txt` below). |
| 1.3 | Add a `.env` file at root with `GROQ_API_KEY=your_key_here`. Add `.env` to `.gitignore`. |
| 1.4 | Add a `requirements.txt` (or `pyproject.toml`) listing: `sentence-transformers`, `chromadb`, `requests`, `beautifulsoup4`, `python-dotenv`, `groq`. |
| 1.5 | Scaffold the project layout (see `architecture.md` §6):<br>`ingest.py`, `query.py`, `data/chunks.txt`, `chroma_db/`. |

**Result** A runnable Python project with API key out of Git.

---

## Phase 2 – Loading and Chunking

**Goal** Download the 5 Groww scheme pages, extract text + metadata, and produce a human‑readable `data/chunks.txt`.

| Step | Action |
|------|--------|
| 2.1 | In `ingest.py`, define the 5 URLs (from the Groww links). Use `requests` + `beautifulsoup4` to fetch and parse each page. |
| 2.2 | Extract: <br>• Scheme name (page heading)<br>• Category (Large Cap, Flexi Cap, ELSS, Small Cap, Balanced Advantage)<br>• URL<br>• Heading hierarchy (`<h2>`, `<h3>`)<br>• Body text (all `<p>` or `<div>` content). |
| 2.3 | Implement chunking (per `architecture.md` §4):<br>• **Chunk size**: 512 tokens (~800‑900 chars).<br>• **Overlap**: 64 tokens (~100 chars).<br>• Split on sentences or paragraph boundaries, preserving overlap. |
| 2.4 | For each chunk create a metadata dict: `{ "scheme_name":..., "category":..., "url":..., "heading":... }`. |
| 2.5 | Append chunks to `data/chunks.txt` in the format `CHUNK_ID|SCHEME|CATEGORY|URL|HEADING|TOKEN_TEXT`. |
| 2.6 | Run `python ingest.py` once; verify the .txt file contains all chunks and that the metadata fields are readable. |

**Result** A text file with every chunk + metadata, ready for embedding.

---

## Phase 3 – Embedding and Vector Store

**Goal** Convert chunks to 384‑dim vectors and persist them in ChromaDB on disk.

| Step | Action |
|------|--------|
| 3.1 | In `ingest.py` (or a separate `embed_store.py`), load the local model: `SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')`. |
| 3.2 | Encode all chunk texts → numpy array of shape `(N, 384)`. |
| 3.3 | initialise ChromaDB client with persistence directory `./chroma_db`: `chroma = chromadb.PersistentClient(path="./chroma_db")`. |
| 3.4 | Create (or get) a collection, e.g., `collection = chroma.get_or_create_collection("hdfc_funds")`. |
| 3.5 | Add vectors with their metadata: `collection.add(ids=[f"chunk_{i}" for i in range(N)], embeddings=embeddings, metadatas=[meta_dicts], documents=[chunk_texts])`. |
| 3.6 | Persist: ChromaDB automatically writes to `./chroma_db/`. No re‑ingestion needed on subsequent runs. |
| 3.7 | Run the script once; confirm `chroma_db/` contains the expected data (use `chroma-cli` or a quick Python inspect script). |

**Result** A persisted vector store that can be queried without re‑embedding.

---

## Phase 4 – Guardrails

**Goal** Ensure safe, relevant answers and prevent junk or out‑of‑scope queries.

| Step | Action |
|------|--------|
| 4.1 | **Query preprocessing**: Strip whitespace, lowercase, detect language (optional). |
| 4.2 | **Keyword guard**: If the query contains unrelated terms (e.g., “weather”, “stock price”), return a polite message: “I can only answer questions about HDFC mutual fund schemes.” |
| 4.3 | **Category filter (optional)**: If the user asks about a specific category, add a ChromaDB where metadata filter: `where={"category": "ELSS"}`. |
| 4.4 | **Answer validation**: After Groq returns an answer, check that every cited chunk ID actually exists in the retrieved set; if not, trim the answer or flag “source mismatch”. |
| 4.5 | **Rate‑limit / API error handling**: Retry on Groq transient errors (exponential backoff); cap monthly token usage for the demo. |

Implement these checks in `query.py` before the LLM call and after the response.

---

## Phase 5 – Retrieval + LLM Answer

**Goal** Accept a user question, retrieve the most relevant chunks, and generate a grounded answer via Groq.

| Step | Action |
|------|--------|
| 5.1 | In `query.py`, prompt the user for a question (CLI `input()` or Streamlit text box). |
| 5.2 | Encode the question with the **same** `MiniLM-L6-v2` model used for chunks. |
| 5.3 | Query ChromaDB: `results = collection.query(query_embeddings=[q_emb], n_results=4, include=["documents","metadatas"])` |
| 5.4 | Build a context string from the returned `documents`, e.g.:<br>`context = "\n\n".join([f"[{meta['scheme_name']}] {doc}" for doc, meta in zip(results['documents'], results['metadatas'])])` |
| 5.5 | Construct a prompt for Groq:<br>`Prompt = f"Answer the user question using only the context below. If the answer is not present, say you don't know.\n\nContext:\n{context}\n\nQuestion: {user_question}"` |
| 5.6 | Call Groq API: `groq_client = Groq(api_key=os.getenv("GROQ_API_KEY")); response = groq_client.chat.completions.create(model="qwen/qwen3.8-27b", messages=[{"role":"user","content":prompt}])` |
| 5.7 | Extract `response.choices[0].message.content` and return it to the user, optionally appending source lines: `Sources: ...` |
| 5.8 | Handle errors: non‑200 response, empty results, token limits. |

**Result** A working RAG loop: user question → embed → retrieve → Groq → grounded answer.

---

## Phase 6 – UI (Simple Demo Interface)

**Goal** Provide an accessible demo UI for the class; can be a CLI or a minimal Streamlit app.

| Option | Description |
|--------|-------------|
| **6.1 CLI** | `python query.py` prompts “Ask a question about HDFC funds:” and prints the answer. Good for quick terminal demo. |
| **6.2 Streamlit** | Create `app.py` with `st.text_input`, `st.button`, and an area to display the answer + an expander showing retrieved chunks and their metadata. <br>```python\nimport streamlit as st\nst.title('HDFC Mutual Fund RAG')\nquestion = st.text_input('Your question')\nif st.button('Submit') and question:\n    answer = ask_question(question)  # reuse Phase 5 logic\n    st.write(answer)\n``` |
| **6.3 Polish** | Add a short intro explaining the system, show the `chunks.txt` inspection path, and a “Re‑run ingestion” button (for educators). |
| **6.4 Deployment** | For a class demo, local execution is sufficient; ensure `.env` is not committed and the virtual environment is used. |

**Result** An end‑to‑end demo that students can run, query, and see the RAG pipeline in action.

---

## Quick Reference: `requirements.txt`

```
sentence-transformers==2.2.2
chromadb==0.4.15
requests==2.32.3
beautifulsoup4==4.12.3
python-dotenv==1.0.1
groq==0.6.0
streamlit==1.36.0   # optional, for UI
```

---
*All phases reference the architectural decisions in `architecture.md` (MiniLM‑L6‑v2 embeddings, 512‑token chunks with 64‑token overlap, ChromaDB persistence, Groq `qwen/qwen3.8-27b`, metadata‑rich chunks, `.env` API key).*
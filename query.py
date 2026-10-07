#!/usr/bin/env python
"""Phase 5 – Retrieval + LLM answer for the HDFC Mutual Fund RAG chatbot.

This script sets the console output encoding to UTF‑8 so that rupee symbols
and other non‑ASCII characters print correctly on Windows.
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

"""Phase 5 – Retrieval + LLM answer for the HDFC Mutual Fund RAG chatbot.

Responsibilities (as described in implementation.md §5):
  • Embed the user's question with the same MiniLM‑L6‑v2 model used for chunks.
  • Retrieve the top‑k most similar chunks from the persisted ChromaDB.
  • Build a context block from the retrieved chunk texts and their metadata.
  • Send the context + user question to Groq (model qwen/qwen3.8-27b) as a prompt.
  • Return the LLM's grounded answer to the user.
  • Simple CLI UI: `python query.py "<your question>"`.
"""

import os
import sys
import json
import re
from typing import List, Tuple, Dict, Any

import streamlit as st

# ----------------------------------------------------------------------
# 1️⃣ Load the HuggingFace embedding model (same as ingest.py)
# ----------------------------------------------------------------------
from transformers import AutoTokenizer, AutoModel

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEVICE = "cpu"

_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
_model = AutoModel.from_pretrained(MODEL_NAME)
_model.to(DEVICE)
_model.eval()                     # disables gradient tracking


def _embed_text(text: str) -> List[float]:
    """Return a 384‑dim embedding for *text* (used by both ingest and query)."""
    inputs = _tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    ).to(DEVICE)

    with torch.no_grad():
        outputs = _model(**inputs)
    pooling = torch.mean(outputs.last_hidden_state, dim=1).squeeze(0)
    return pooling.cpu().numpy().tolist()


# ----------------------------------------------------------------------
# 2️⃣ Initialise ChromaDB (persistent, same collection as ingest.py)
# ----------------------------------------------------------------------
import chromadb
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "qwen/qwen3.8-27b"

if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY not set. Add it to .env (see .env.example).", file=sys.stderr)
    sys.exit(1)

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection("hdfc_funds")   # 45 chunks already stored


# ----------------------------------------------------------------------
# 3️⃣ Helper functions
# ----------------------------------------------------------------------
def retrieve(question: str, k: int = 2) -> Dict[str, Any]:
    """Embed the question and return the top‑k ChromaDB results."""
    q_emb = _embed_text(question)
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas"],
    )
    # Ensure ids are present (Chroma may omit if not requested)
    if "ids" not in results:
        all_ids = collection.get(include=[])["ids"]
        results["ids"] = [all_ids]
    return results


def build_context(results: Dict[str, Any]) -> str:
    """Turn the query result into a single string prompt fragment."""
    docs = results.get("documents", [[]])[0] if results else []
    metas = results.get("metadatas", [[]])[0] if results else []
    parts = []
    for doc, meta in zip(docs, metas):
        scheme = meta.get("scheme_name", "Unknown Scheme")
        cat = meta.get("category", "Unknown Category")
        parts.append(f"[{scheme} ({cat})] {doc}")
    return "\n\n".join(parts)


def ask_groq(context: str, question: str) -> str:
    """Call Groq and return the model's answer."""
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""Answer the user's question using ONLY the context below. If the answer is not present, say "I don't have that information in the provided HDFC fund data."

Context:
{context}

Question: {question}
"""
    try:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        answer = completion.choices[0].message.content.strip()
        return answer
    except Exception as e:
        return f"Error contacting Groq: {e}"


def ask_question(question: str, k: int = 2) -> Tuple[str, Dict[str, Any]]:
    """Full pipeline: retrieve → context → LLM answer."""
    results = retrieve(question, k=k)
    context = build_context(results)
    answer = ask_groq(context, question)
    return answer, results


# ----------------------------------------------------------------------
# 5. CLI entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python query.py \"<your question about HDFC mutual funds>\"",
            file=sys.stderr,
        )
        sys.exit(1)

    user_question = " ".join(sys.argv[1:])

    answer, retrieval = ask_question(user_question, k=2)

    # ------------------------------------------------------------------
    # Display the LLM answer (or the error message returned by Groq)
    # ------------------------------------------------------------------
    print("\n=== Answer ===\n", answer, "\n")

    # ------------------------------------------------------------------
    # Show the retrieved chunks (for reference)
    # ------------------------------------------------------------------
    docs = retrieval.get("documents", [[]])[0] if retrieval else []
    metas = retrieval.get("metadatas", [[]])[0] if retrieval else []
    ids = retrieval.get("ids", [[]])[0] if retrieval else []

    if docs:
        print("=== Retrieved chunks (for reference) ===")
        for i, (doc, meta, chk_id) in enumerate(zip(docs, metas, ids), start=1):
            scheme = meta.get("scheme_name", "Unknown")
            cat = meta.get("category", "Unknown")
            # Safely show first 120 characters, replacing non‑ASCII with '?'
            preview = doc[:120] if isinstance(doc, str) else str(doc)[:120]
            preview = ''.join(c if ord(c) < 128 else '?' for c in preview)
            preview = preview.replace("\n", " ").replace("\r", " ")
            print(f"{i}. [{scheme} ({cat})] ID={chk_id}")
            print(f"   {preview}…")
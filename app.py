#!/usr/bin/env python
"""Phase 6 – Simple Streamlit UI for the HDFC Mutual Fund RAG chatbot.

This app wraps the Phase‑5 retrieval+LLM pipeline (query.py) in a web‑style
interface.  It reads the Groq API key from the existing `.env` file and
displays the answer together with the retrieved chunks for transparency.
"""

import os
import sys

# Ensure the .env file is loaded before any other imports
from dotenv import load_dotenv
load_dotenv()

import streamlit as st

# ----------------------------------------------------------------------
# Import the RAG pipeline from query.py (same environment)
# ----------------------------------------------------------------------
# The query module already checks for GROQ_API_KEY and exits if missing.
# We simply import the ask_question function; if the key is absent the
# script will exit when the user clicks “Submit”.
# ----------------------------------------------------------------------
# Import after dotenv load so the key is available.
# ----------------------------------------------------------------------
# To avoid circular imports we simply call the pipeline inline.
# We'll re‑implement the minimal logic needed (embed, retrieve, Groq call)
# using the same code that is in query.py but adapted for Streamlit.
# ----------------------------------------------------------------------

import re
import json
from typing import List, Tuple, Dict, Any

from sentence_transformers import SentenceTransformer
import chromadb
from groq import Groq

# ----------------------------------------------------------------------
# Configuration (same as query.py)
# ----------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "qwen/qwen3.8-27b"

if not GROQ_API_KEY:
    st.error(
        "GROQ_API_KEY not found in environment. "
        "Add it to the `.env` file at the project root (see .env.example)."
    )
    st.stop()

embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection("hdfc_funds")

# ----------------------------------------------------------------------
# Helper functions (mirror those in query.py)
# ----------------------------------------------------------------------
def retrieve(question: str, k: int = 4) -> Dict[str, Any]:
    q_emb = embed_model.encode(question).tolist()
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas"],
    )
    if "ids" not in results:
        all_ids = collection.get(include=[])["ids"]
        results["ids"] = [all_ids]
    return results


def build_context(results: Dict[str, Any]) -> str:
    docs = results.get("documents", [[]])[0] if results else []
    metas = results.get("metadatas", [[]])[0] if results else []
    parts = []
    for doc, meta in zip(docs, metas):
        scheme = meta.get("scheme_name", "Unknown Scheme")
        cat = meta.get("category", "Unknown Category")
        parts.append(f"[{scheme} ({cat})] {doc}")
    return "\n\n".join(parts)


def ask_groq(context: str, question: str) -> str:
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


def ask_question(question: str, k: int = 4) -> Tuple[str, Dict[str, Any]]:
    results = retrieve(question, k=k)
    context = build_context(results)
    answer = ask_groq(context, question)
    return answer, results


# ----------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------
st.set_page_config(page_title="HDFC Mutual Fund RAG", page_icon="💹")

st.title("💹 HDFC Mutual Fund RAG Chatbot")
st.caption("A demo RAG system for 5 HDFC scheme categories (Large Cap, Flexi Cap, ELSS, Small Cap, Balanced Advantage).")

st.markdown(
    """
    Enter a question about the HDFC mutual fund schemes below.  
    The system will retrieve the most relevant chunks from the stored Groww pages
    and ask the Groq LLM (`qwen/qwen3.8-27b`) to generate a grounded answer.
    """
)

user_question = st.text_input("Your question:", placeholder="e.g. What is HDFC Large Cap Fund?")

if st.button("Submit"):
    if not user_question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Thinking…"):
            answer, retrieval = ask_question(user_question, k=4)

        st.subheader("Answer")
        st.write(answer)

        # Display retrieved chunks (expander)
        with st.expander("Show retrieved chunks (for reference)"):
            docs = retrieval.get("documents", [[]])[0] if retrieval else []
            metas = retrieval.get("metadatas", [[]])[0] if retrieval else []
            ids = retrieval.get("ids", [[]])[0] if retrieval else []

            if docs:
                for i, (doc, meta, chk_id) in enumerate(zip(docs, metas, ids), start=1):
                    scheme = meta.get("scheme_name", "Unknown")
                    cat = meta.get("category", "Unknown")
                    preview = doc[:120] if isinstance(doc, str) else str(doc)[:120]
                    preview = "".join(c if ord(c) < 128 else "?" for c in preview)
                    preview = preview.replace("\n", " ").replace("\r", " ")
                    st.markdown(
                        f"**{i}. [{scheme} ({cat})] ID={chk_id}**\n"
                        f"> {preview}…"
                    )
            else:
                st.info("No chunks were retrieved.")
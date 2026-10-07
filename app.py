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
import torch
torch.set_num_threads(1)

# ----------------------------------------------------------------------
# 1️⃣ Load the HuggingFace embedding model (same as ingest/query)
# ----------------------------------------------------------------------
from transformers import AutoTokenizer, AutoModel

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEVICE = "cpu"

_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
_model = AutoModel.from_pretrained(MODEL_NAME)
_model.to(DEVICE)
_model.eval()                     # disables gradient tracking


def _embed_text(text: str) -> list:
    """Return a 384‑dim embedding for *text* (used by ingest/query)."""
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
# 2️⃣ Initialise ChromaDB (persistent, same collection as ingest/query)
# ----------------------------------------------------------------------
import chromadb
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "qwen/qwen3.8-27b"

if not GROQ_API_KEY:
    st.error(
        "GROQ_API_KEY not found in environment. "
        "Add it to the `.env` file at the project root (see .env.example)."
    )
    st.stop()

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection("hdfc_funds")   # 45 chunks already stored


# ----------------------------------------------------------------------
# 3️⃣ Helper functions (mirror those in query.py)
# ----------------------------------------------------------------------
def retrieve(question: str, k: int = 2) -> dict:
    """Embed the question and return the top‑k ChromaDB results."""
    # use the same embedding function defined above
    q_emb = _embed_text(question)
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas"],
    )
    if "ids" not in results:
        all_ids = collection.get(include=[])["ids"]
        results["ids"] = [all_ids]
    return results


def build_context(results: dict) -> str:
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


def ask_question(question: str, k: int = 2) -> tuple:
    """Full pipeline: retrieve → context → LLM answer."""
    results = retrieve(question, k=k)
    context = build_context(results)
    answer = ask_groq(context, question)
    gc.collect()
return answer, results


# ----------------------------------------------------------------------
# 4️⃣ Streamlit UI
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
            answer, retrieval = ask_question(user_question, k=2)

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
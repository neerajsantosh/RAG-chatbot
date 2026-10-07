#!/usr/bin/env python
"""Phase 2+3 – Ingest HDFC Groww pages, chunk, embed with HuggingFace, store in ChromaDB."""

import os
import re
import json
import sqlite3
from typing import List, Dict

import torch
from transformers import AutoTokenizer, AutoModel
import chromadb
from dotenv import load_dotenv

load_dotenv()
# ----------------------------------------------------------------------
# 1️⃣ Configuration
# ----------------------------------------------------------------------
CHUNK_SIZE = 512      # tokens (approx. 800‑900 chars)
CHUNK_OVERLAP = 64    # tokens
EMBEDDING_DIM = 384   # MiniLM‑L6‑v2 dimension
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"   # hugging‑face repo id
DEVICE = "cpu"        # Render free tier has no GPU

# ----------------------------------------------------------------------
# 2️⃣ Helper: download & cache the model (only once)
# ----------------------------------------------------------------------
def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.to(DEVICE)
    model.eval()                     # <‑‑ critical: disables gradient tracking
    return tokenizer, model

tokenizer, model = load_model()   # loaded once when ingest.py is imported

# ----------------------------------------------------------------------
# 3️⃣ Chunking (token‑based, 512‑token windows, 64‑token overlap)
# ----------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split *text* into token‑based windows; return list of chunk‑strings."""
    # Quick & dirty word‑token split – good enough for these short pages
    tokens = tokenizer.tokenize(text)
    if len(tokens) <= chunk_size:
        return [tokenizer.convert_tokens_to_string(tokens)]

    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(tokens) - chunk_size + 1, step):
        window_tokens = tokens[i : i + chunk_size]
        chunk_text = tokenizer.convert_tokens_to_string(window_tokens)
        chunks.append(chunk_text)

    # finally, maybe a tail that is shorter than chunk_size
    if i + chunk_size < len(tokens):
        tail = tokenizer.convert_tokens_to_string(tokens[i + chunk_size :])
        if tail.strip():
            chunks.append(tail)

    return chunks


# ----------------------------------------------------------------------
# 4️⃣ Embedding function (mean‑pooling, no‑grad)
# ----------------------------------------------------------------------
def embed_chunk(chunk_text: str) -> List[float]:
    """Return a 384‑dim embedding (list of floats) for *chunk_text*."""
    # Tokenise + attend
    inputs = tokenizer(
        chunk_text,
        return_tensors="pt",
        truncation=True,
        max_length=CHUNK_SIZE,
        padding=False,
    ).to(DEVICE)               # move to the same device as model

    # Without gradient tracking – saves a lot of memory
    with torch.no_grad():
        outputs = model(**inputs)   # last_hidden_state: (1, seq, hidden)

    # Mean‑pool over the sequence dimension → (1, hidden)
    pooling = torch.mean(outputs.last_hidden_state, dim=1).squeeze(0)

    # Move to CPU and convert to plain Python list
    emb = pooling.cpu().numpy().tolist()
    return emb


# ----------------------------------------------------------------------
# 5️⃣ Parse the chunks.txt that was written earlier (or generate fresh)
# ----------------------------------------------------------------------
def parse_chunks_file(path: str = "data/chunks.txt") -> List[Dict]:
    """Return list of dicts: {id, text, metadata}."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            # expected: CHUNK_ID|SCHEME|CATEGORY|URL|HEADING|TEXT
            if len(parts) < 6:
                continue
            chunk_id, scheme, category, url, heading, *text_parts = parts
            text = "|".join(text_parts)          # re‑join in case text itself contains |
            entries.append({
                "id": chunk_id,
                "text": text,
                "metadata": {
                    "scheme_name": scheme,
                    "category": category,
                    "url": url,
                    "heading": heading,
                },
            })
    return entries


# ----------------------------------------------------------------------
# 6️⃣ Main – orchestrate ingestion
# ----------------------------------------------------------------------
def main():
    os.makedirs("data", exist_ok=True)

    # ------------------------------------------------------------------
    # 6a) If chunks.txt already exists we can reuse it; otherwise we
    #     scrape the 5 Groww pages (very small – just a request + BS4).
    # ------------------------------------------------------------------
    if not os.path.isfile("data/chunks.txt"):
        # ----- very lightweight scraper (same 5 URLs you already have) -----
        GROWW_URLS = {
            "Large Cap": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "Flexi Cap": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
            "ELSS": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
            "Small Cap": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            "Balanced Advantage": "https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth",
        }

        import requests
        from bs4 import BeautifulSoup

        all_chunks = []
        for category, url in GROWW_URLS.items():
            print(f"Fetching {category} …")
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
            # Remove script / style blocks
            for s in soup(["script", "style"]):
                s.extract()
            body_text = soup.get_text(separator=" ", strip=True)

            # Chunk the raw text
            chunks = chunk_text(body_text)
            for idx, chunk in enumerate(chunks):
                meta = {
                    "scheme_name": category,
                    "category": category,
                    "url": url,
                    "heading": "",          # we didn’t extract headings in the quick scrape
                }
                chunk_id = f"{category}_{idx}"
                all_chunks.append({"id": chunk_id, "text": chunk, "metadata": meta})

        # Persist human‑readable file for debugging / inspection
        with open("data/chunks.txt", "w", encoding="utf-8") as f:
            for entry in all_chunks:
                line = (
                    f"{entry['id']}|{entry['metadata']['scheme_name']}"
                    f"|{entry['metadata']['category']}"
                    f"|{entry['metadata']['url']}"
                    f"|{entry['metadata']['heading']}"
                    f"|{entry['text']}"
                )
                f.write(line + "\n")
        print(f"Wrote {len(all_chunks)} chunks to data/chunks.txt")
    else:
        # ------------------------------------------------------------------
        # 6b) If the file already exists, just read it (fast path)
        # ------------------------------------------------------------------
        all_chunks = parse_chunks_file()
        print(f"Read {len(all_chunks)} pre‑existing chunks from data/chunks.txt")

    # ------------------------------------------------------------------
    # 7️⃣ Embed every chunk and store in ChromaDB
    # ------------------------------------------------------------------
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="hdfc_funds")

    # The build command (`rm -rf chroma_db`) already guarantees a clean slate,
    # so we skip any per‑run deletion here.
    for entry in all_chunks:
        emb = embed_chunk(entry["text"])
        # Guard: ensure exactly 384 dimensions
        assert len(emb) == EMBEDDING_DIM, f"Embedding dimension {len(emb)} != {EMBEDDING_DIM}"

        collection.add(
            ids=[entry["id"]],
            embeddings=[emb],
            metadatas=[entry["metadata"]],
            documents=[entry["text"]],
        )

    # Persist to disk (Chroma does this automatically, but we explicit‑ly call)
    collection.persist()
    print(f"✅  Ingestion complete – {len(all_chunks)} chunks embedded in chroma_db/")


if __name__ == "__main__":
    main()
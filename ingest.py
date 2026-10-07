#!/usr/bin/env python
"""Phase 1+2: Project setup, loading HDFC Groww pages and chunking."""

import os
import json
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
import chromadb
from dotenv import load_dotenv

# Load environment
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 5 Groww URLs (Direct–Growth plans)
URLS = {
    "Large Cap": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "Flexi Cap": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "ELSS": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "Small Cap": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "Balanced Advantage": "https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth",
}

def fetch_page(url: str) -> str:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style
    for s in soup(["script", "style"]):
        s.extract()
    return soup.get_text(separator=" ", strip=True)

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list:
    """Simple sliding‑window chunking by characters (approx tokens)."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        window = words[i:i + chunk_size]
        chunk = " ".join(window)
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks

def main():
    all_chunks = []
    for category, url in URLS.items():
        print(f"Fetching {category} ...")
        html = fetch_page(url)
        text = parse_text(html)
        chunks = chunk_text(text)
        for idx, chunk in enumerate(chunks):
            meta = {
                "scheme_name": category,
                "category": category,
                "url": url,
                "heading": "",  # will be filled if heading hierarchy extracted later
            }
            all_chunks.append({"id": f"{category}_{idx}", "text": chunk, "metadata": meta})

    # Save readable chunks.txt
    os.makedirs("data", exist_ok=True)
    with open("data/chunks.txt", "w", encoding="utf-8") as f:
        for entry in all_chunks:
            line = f"{entry['id']}|{entry['metadata']['scheme_name']}|{entry['metadata']['category']}|{entry['metadata']['url']}|{entry['metadata']['heading']}|{entry['text']}"
            f.write(line + "\n")
    print(f"Wrote {len(all_chunks)} chunks to data/chunks.txt")

    # Embed and store in ChromaDB
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = model.encode([c["text"] for c in all_chunks])

    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection("hdfc_funds")
    for i, c in enumerate(all_chunks):
        collection.add(
            ids=[c["id"]],
            embeddings=[embeddings[i].tolist()],
            metadatas=[c["metadata"]],
            documents=[c["text"]],
        )
    print("Vector store updated in chroma_db/")

if __name__ == "__main__":
    main()
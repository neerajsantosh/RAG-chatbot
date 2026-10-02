"""Add a single demo chunk to ChromaDB and verify."""
from packages.vector.chroma_store import ChromaStore
from sentence_transformers import SentenceTransformer

cs = ChromaStore()
coll = cs._ensure()

# demo chunk data (from manifest)
chunk_id = "8f62ecfaf13417cbb5b061c4f74050e198b83a47c83c602348b2feb8fee1ee52"
text = "the refund policy allows returns within 30 days of purchase."

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
embedding = model.encode(text).tolist()

coll.upsert(
    ids=[chunk_id],
    embeddings=[embedding],
    documents=[text],
    metadatas=[{
        "source_file": "docs\\sample_docs\\refund.txt",
        "char_start": 0,
        "char_end": 14,
        "token_count": 14,
        "hash": chunk_id,
    }],
)

full = coll.get()
print("ids after upsert:", full.get("ids"))
print("number:", len(full.get("ids", [])))
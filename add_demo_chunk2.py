"""Add second demo chunk (warranty) to ChromaDB."""
from packages.vector.chroma_store import ChromaStore
from sentence_transformers import SentenceTransformer

cs = ChromaStore()
coll = cs._ensure()

chunk_id = "aa89b3339bbd63484301b06de74483b7545d369adcb8892dee47fd9d6a507237"
text = "the warranty covers manufacturing defects for one year."

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
embedding = model.encode(text).tolist()

coll.upsert(
    ids=[chunk_id],
    embeddings=[embedding],
    documents=[text],
    metadatas=[{
        "source_file": "docs\\sample_docs\\warranty.txt",
        "char_start": 0,
        "char_end": 12,
        "token_count": 12,
        "hash": chunk_id,
    }],
)

full = coll.get()
print("ids after upsert:", full.get("ids"))
print("number:", len(full.get("ids", [])))
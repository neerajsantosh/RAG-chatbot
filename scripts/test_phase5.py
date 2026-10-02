"""Quick test for Phase 5 RAG pipeline."""
from packages.pipeline.orchestrator import answer_question


def main():
    question = "What is our policy on annual leave carry-over?"
    print(f"Question: {question}")
    result = answer_question(question)
    print(f"Answer: {result['answer']}")
    print(f"Chunks retrieved: {len(result['chunks'])}")
    for i, c in enumerate(result["chunks"], 1):
        text = c.get("text", "")[:60].replace("\n", " ")
        print(f"  Chunk {i}: {text}...")
    print(f"Citations: {result['citations']}")


if __name__ == "__main__":
    main()
PYEOF
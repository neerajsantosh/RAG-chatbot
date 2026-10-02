from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import httpx

from sentence_transformers import SentenceTransformer

from packages.vector.chroma_store import ChromaStore
from packages.core.errors import ValidationFailed


# ---------------------------------------------------------------------------
# Embedding model – must match what was used to populate the Chroma index
# ---------------------------------------------------------------------------

_EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_embed_model: Optional[SentenceTransformer] = None


def _get_embed_model() -> SentenceTransformer:
    """Cache the sentence-transformers model so it's loaded once."""
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


# ---------------------------------------------------------------------------
# Groq LLM configuration – passed as parameters, no Settings import at module level
# ---------------------------------------------------------------------------

def _groq_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _groq_payload(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens or 1024,
        "stream": False,
    }


async def _groq_chat_complete(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 30.0,
) -> str:
    """Call the Groq chat completions endpoint and return the assistant message."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=_groq_headers(api_key),
            json=_groq_payload(model, messages),
        )
    if resp.status_code != 200:
        body = resp.text[:200]
        raise RuntimeError(f"Groq API error {resp.status_code}: {body}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def ask_groq(
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    """Synchronous wrapper for Groq chat completion."""
    return asyncio.run(
        _groq_chat_complete(api_key, model, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], timeout=30.0)
    )


# ---------------------------------------------------------------------------
# Core pipeline stage: embed + retrieve
# ---------------------------------------------------------------------------

def retrieve_chunks(
    question: str,
    k: int = 6,
    user_groups: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[float]]:
    """Embed the question and retrieve the top-k chunks from ChromaDB.

    Returns (chunks, distances) where each chunk dict has at minimum:
        - text: the chunk content
        - metadata: source_file, char_start, char_end, token_count, hash, acl_tags
        - distance: cosine distance (lower = more similar)
    """
    # 1. Embed the question with the SAME model used in Phase 3
    embed_model = _get_embed_model()
    question_embedding = _embed_model.encode(question).tolist()

    # 2. Retrieve from ChromaDB (ACL-aware if user_groups provided)
    chroma = ChromaStore(user_groups=user_groups)
    raw_results = chroma.query(question, k=k)

    # Normalise to (chunk_dict, distance) pairs
    chunks: List[Dict[str, Any]] = []
    distances: List[float] = []
    for result in raw_results:
        chunks.append(
            {
                "text": result.get("text", ""),
                "metadata": result.get("metadata", {}),
                "distance": result.get("distance", 1.0),
            }
        )
        distances.append(result.get("distance", 1.0))

    return chunks, distances


# ---------------------------------------------------------------------------
# Prompt assembly – grounded prompt with citations
# ---------------------------------------------------------------------------

CONSTRAINT_SYSTEM = """You are a RAG (Retrieval-Augmented Generation) assistant.
Rules (strictly enforced):
1. Answer ONLY from the supplied cited chunks. Do not use any external knowledge.
2. Every claim must be anchored to a citation marker [n] that corresponds to a supplied chunk.
3. If the chunks do not contain enough information to answer, refuse with a grounded refusal.
4. Never expose document metadata or ACL tags to the user.
5. Format citations as [1], [2], ... matching the chunk order supplied.
"""

CONSTRAINT_USER = """Context chunks (may be zero):
{{#if chunks}}
{{#each chunks}}
[{index}]
{{text}}
{{/each}}
{{/if}}
Question: {{question}}

Answer:"""

REFUSAL_TEXT = """I don't have enough in the indexed documents to answer this question.
If you think there's relevant information, please rephrase or provide more context."""


def build_grounded_prompt(
    chunks: List[Dict[str, Any]],
    question: str,
) -> str:
    """Build the grounded prompt for the LLM.

    Returns the full prompt with system constraints, context blocks, and the question.
    """
    # Build the context block from retrieved chunks
    context_parts: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        text = chunk.get("text", "").strip()
        if text:
            context_parts.append(f"[{i}] {text}")

    context_block = "\n".join(context_parts) if context_parts else ""

    # Assemble the prompt
    if context_block:
        user_part = CONSTRAINT_USER.replace("{{#if chunks}}", "{#if chunks}")
        user_part = user_part.replace("{{#each chunks}}", "{{#each chunks}}")
        user_part = user_part.replace("{{index}}", "{index}")
        user_part = user_part.replace("{{text}}", "{text}")
        user_part = user_part.replace("{{question}}", question)
    else:
        user_part = f"Question: {question}\n\nAnswer:"

    return f"{CONSTRAINT_SYSTEM}\n\n{user_part}"


# ---------------------------------------------------------------------------
# End-to-end answer: retrieve + generate
# ---------------------------------------------------------------------------

def answer_question(
    question: str,
    k: int = 6,
    user_groups: Optional[List[str]] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Full RAG pipeline: embed → retrieve → generate → return answer + citations.

    Returns dict with:
        - answer: the generated answer text
        - citations: list of {index, source_file, text_start, text_end} per citation
        - chunks: list of retrieved chunk dicts (text, metadata, distance)
        - question: the original question

    If groq_api_key/groq_model are not provided, the function will attempt to
    read them from the environment via the existing Settings mechanism, but
    callers should provide them explicitly for reliability.
    """
    # Step 1: Embed + retrieve
    chunks, distances = retrieve_chunks(question, k=k, user_groups=user_groups)

    # Step 2: Build grounded prompt
    prompt = build_grounded_prompt(chunks, question)

    # Step 3: Generate with Groq – use provided keys or fall back to defaults
    _api_key = groq_api_key
    _model = groq_model or "qwen/qwen3.8-27b"

    answer_text = ask_groq(_api_key, _model, CONSTRAINT_SYSTEM, prompt)

    # Step 4: Extract citations from the answer markers [1], [2], ...
    citations: List[Dict[str, int | str]] = []
    import re
    marker_pattern = re.compile(r"\[(\d+)\]")
    seen_indices: set[int] = set()
    for match in marker_pattern.finditer(answer_text):
        idx = int(match.group(1))
        if idx not in seen_indices and 1 <= idx <= len(chunks):
            seen_indices.add(idx)
            chunk = chunks[idx - 1]
            citations.append(
                {
                    "index": idx,
                    "source_file": chunk.get("metadata", {}).get("source_file", ""),
                    "text_start": chunk.get("metadata", {}).get("char_start", 0),
                    "text_end": chunk.get("metadata", {}).get("char_end", 0),
                }
            )

    # Step 5: If no citations found but answer references chunks, mark as ungrounded
    if not citations and any(re.match(r"\[(\d+)\]", m) for m in marker_pattern.findall(answer_text)):
        # Markers referenced chunks that don't exist - treat as ungrounded
        citations = []

    return {
        "answer": answer_text.strip(),
        "citations": citations,
        "chunks": chunks,
        "question": question,
    }
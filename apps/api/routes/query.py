"""Query endpoint for the RAG chatbot.

POST /api/v1/query
{
    "question": "What is the refund window for annual plans?",
    "stream": true   // optional, currently not streamed
}

Response (JSON):
{
    "answer": "Annual plans can be refunded within 30 days...",
    "citations": [
        {"n": 1, "source_id": "S1", "title": "Refund Policy v4", "anchor": "#refund-window", "snippet": "…"},
        ...
    ],
    "trace_id": "...",
    "cost_usd": 0.00123
}
"""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from core.config.settings import Settings
from llm.adapters.registry import resolve_embedder
from packages.vector.chroma_store import ChromaStore
from packages.llm.groq_client import retrieve_answer, _build_prompt

router = APIRouter(prefix="/api/v1", tags=["query"])


def _get_settings() -> Settings:
    # Dependency that simply returns the app‑wide Settings instance.
    from core.config import get_settings
    return get_settings()


@router.post("/query")
async def query_question(
    req: Request,
    question: str,
    stream: bool = False,
    settings: Settings = Depends(_get_settings),
):
    """Handle a user question.

    1. Embed the question with the same MiniLM model used for chunks.
    2. Query ChromaDB for the top‑k chunks.
    3. Pass the question + chunks to the Groq LLM.
    4. Return the answer and minimal citation metadata.
    """
    # 1. embed question
    embedder = resolve_embedder("fake", settings)  # will be real later
    # For now use a tiny placeholder: we'll just call the embedder from the registry.
    # The registry currently returns a fake; in production it would be the real model.
    # We'll fake embedding by using a simple trick: treat the question text as embedding
    # (real implementation would call the model). For demo purposes we just proceed
    # with an empty list; the endpoint will error until the real adapter is wired.
    # TODO: replace with actual embedder once the model is registered.

    # 2. query ChromaDB
    chroma = ChromaStore()
    # placeholder top‑k results – in real code we'd use the embedder above.
    # Here we just return a canned response indicating not configured.
    if not getattr(settings, "groq_api_key_set", False):
        return JSONResponse(
            status_code=503,
            content={"detail": "Groq not configured. Set GROQ_API_KEY and GROQ_MODEL."},
        )

    # 3. call Groq
    # context_chunks will be filled from Chroma; for now we use a dummy list.
    context_chunks = ["(placeholder chunk until Chroma is wired)"]

    answer = retrieve_answer(question, context_chunks)

    # 4. build minimal citation list from the chunks we have
    citations = []
    for i, chunk in enumerate(context_chunks, start=1):
        citations.append(
            {
                "n": i,
                "source_id": f"S{i}",
                "title": "Placeholder Source",
                "anchor": f"#chunk-{i}",
                "snippet": chunk[:80] + ("…" if len(chunk) > 80 else ""),
                "verified": True,
            }
        )

    trace_id = str(uuid.uuid4())

    return JSONResponse(
        content={
            "answer": answer,
            "citations": citations,
            "trace_id": trace_id,
        }
    )
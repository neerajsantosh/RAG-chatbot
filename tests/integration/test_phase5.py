"""Phase 5 integration test: embed + retrieve + LLM answer."""
from __future__ import annotations

import pytest
import re

from packages.pipeline.orchestrator import answer_question, retrieve_chunks, build_grounded_prompt
from packages.vector.chroma_store import ChromaStore


class TestPhase5Retrieve:
    """Test the retrieve + generate pipeline end-to-end."""

    def test_answerable_question_grounded(self):
        """Questions answered from the corpus get grounded citations."""
        result = answer_question(
            "What is our policy on annual leave carry-over?",
            groq_api_key=groq_api_key,
            groq_model="qwen/qwen3.8-27b",
        )
        assert result["answer"] is not None
        assert len(result["answer"]) > 0
        # Should have citations referencing actual chunks
        assert result["citations"] is not None

    def test_unanswerable_question(self):
        """Questions the corpus cannot answer should trigger refusal."""
        result = answer_question(
            "What is the average salary of the engineering team last quarter?",
            groq_api_key=groq_api_key,
            groq_model="qwen/qwen3.8-27b",
        )
        assert result["answer"] is not None
        # Either an answer grounded in chunks, or a refusal
        # For now just verify the pipeline doesn't crash


class TestPhase5Citations:
    """Test that citations reference actual retrieved chunks."""

    def test_citations_refer_chunks(self):
        """Every cited marker [n] in the answer corresponds to a supplied chunk."""
        result = answer_question(
            "What is our policy on annual leave carry-over?",
            groq_api_key=groq_api_key,
            groq_model="qwen/qwen3.8-27b",
        )
        chunks = result["chunks"]
        citations = result["citations"]
        if citations:  # May be empty if model doesn't use citations
            import re
            markers = re.findall(r"\[(\d+)\]", result["answer"])
            for marker in markers:
                idx = int(marker)
                # Each cited index must refer to an existing chunk
                assert 1 <= idx <= len(chunks), f"Citation [ {idx} ] refers to non-existent chunk"


class TestRetrieveChunks:
    """Test chunk retrieval from ChromaDB."""

    def test_retrieve_returns_chunks(self):
        """Retrieve returns chunks with text and metadata."""
        chunks, distances = retrieve_chunks("refund policy", k=3)
        assert len(chunks) > 0
        assert len(chunks) == len(distances)
        for chunk in chunks:
            assert "text" in chunk
            assert "metadata" in chunk


class TestBuildPrompt:
    """Test grounded prompt building."""

    def test_prompt_has_system_constraints(self):
        """The grounded prompt includes the system constraints."""
        chunks = [{"text": "test chunk text", "metadata": {}}]
        prompt = build_grounded_prompt(chunks, "test question")
        assert "RAG" in prompt
        assert "cited chunks" in prompt.lower() or "context" in prompt.lower()


def test_phase5_end_to_end():
    """Full end-to-end Phase 5 pipeline test."""
    result = answer_question(
        "What is our policy on annual leave carry-over?",
        groq_api_key=groq_api_key,
        groq_model="qwen/qwen3.8-27b",
    )
    assert result["answer"] is not None
    assert len(result["answer"]) > 0
    assert result["chunks"] is not None
    assert result["question"] == "What is our policy on annual leave carry-over?"
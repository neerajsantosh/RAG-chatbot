"""Streamlit Phase 6 Chat UI for RAG Chatbot.

Features:
- Message history persistence in session state
- Answer with citations from retrieved chunks
- Source expander under each answer
- Clear-chat button
- Keyboard-friendly (Enter sends)
"""

import streamlit as st
import requests
import json
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_K = 6

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


def init_session_state():
    """Initialise the session-state variables used by the chat UI."""
    if "messages" not in st.session_state:
        st.session_state.messages = []  # type: ignore[assignment]
    if "clear_flag" not in st.session_state:
        st.session_state.clear_flag = False  # type: ignore[assignment]


init_session_state()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def ask_question(question: str, k: int = DEFAULT_K, model: str = DEFAULT_GROQ_MODEL) -> dict:
    """Send a question to the FastAPI backend and return the response payload."""
    try:
        resp = requests.post(
            f"{API_BASE}/chat",
            json={
                "question": question,
                "k": k,
                "groq_model": model,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"API error {resp.status_code}: {resp.text}")
            return {
                "answer": f"API error {resp.status_code}",
                "citations": [],
                "chunks": [],
                "question": question,
            }
    except requests.RequestException as e:
        st.error(f"Could not reach API at {API_BASE}: {e}")
        return {
            "answer": f"Could not reach API: {e}",
            "citations": [],
            "chunks": [],
            "question": question,
        }


def clear_chat():
    """Clear the chat message history."""
    st.session_state.messages = []
    st.session_state.clear_flag = True


# ---------------------------------------------------------------------------
# Render messages
# ---------------------------------------------------------------------------

def render_messages():
    """Render all messages from session state."""
    for idx, msg in enumerate(st.session_state.messages):
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        elif role == "assistant":
            with st.chat_message("assistant"):
                st.markdown(content)

                # Source expander under assistant answers
                if msg.get("citations"):
                    with st.expander("📄 Sources consulted"):
                        for cite in msg["citations"]:
                            src = cite.get("source_file", "unknown")
                            idx_num = cite.get("index", "?")
                            st.caption(f"Source {idx_num}: {src}")
                            st.caption(f"  (characters {cite.get('text_start', '?')}-{cite.get('text_end', '?')})")

                # Feedback control
                if msg.get("feedback") is not None:
                    st.caption(f"👍 👎  Feedback: {msg['feedback']}")

                # Degraded notice if no chunks returned
                if not msg.get("chunks"):
                    st.info("💡 Response generated with no retrieved context. Answers are grounded in cited documents only.")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def render_header():
    """Render the top-of-page header."""
    st.title("🔍 RAG Chatbot")
    st.caption("Phase 6 — Grounded answering with provenance")
    st.button("Clear chat", on_click=clear_chat, type="secondary")


# ---------------------------------------------------------------------------
# Main chat logic
# ---------------------------------------------------------------------------


def main():
    render_header()
    render_messages()

    # Chat input
    if st.session_state.clear_flag:
        st.session_state.clear_flag = False
        st.rerun()

    placeholder = st.chat_input("Ask a question about the internal corpus...")
    if placeholder:
        # Add user message to state
        st.session_state.messages.append({"role": "user", "content": placeholder})

        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = ask_question(placeholder)

            # Build the assistant message dict
            msg = {
                "role": "assistant",
                "content": result["answer"],
                "citations": result.get("citations", []),
                "chunks": result.get("chunks", []),
                "feedback": None,
            }

            # Add to state and render
            st.session_state.messages.append(msg)
            st.rerun()


if __name__ == "__main__":
    main()
#!/usr/bin/env python
"""Minimal guardrails for the HDFC RAG chatbot (Phase 4)."""

import re
import logging
from typing import List, Tuple, Optional

# ----------------------------------------------------------------------
# 1. Query preprocessing
# ----------------------------------------------------------------------
def preprocess_query(user_query: str) -> str:
    q = user_query.strip()
    q = re.sub(r"\s+", " ", q)
    q = q.lower()
    return q


# ----------------------------------------------------------------------
# 2. Out‑of‑scope keyword guard
# ----------------------------------------------------------------------
_IRRELEVANT = {"weather", "stock", "price", "crypto", "forex", "gold", "silver"}

def is_out_of_scope(user_query: str) -> bool:
    q = preprocess_query(user_query)
    return any(kw in q for kw in _IRRELEVANT)


# ----------------------------------------------------------------------
# 3. Category filter detection
# ----------------------------------------------------------------------
def extract_category(user_query: str) -> Optional[str]:
    q = preprocess_query(user_query)
    mapping = {
        "elss": "ELSS",
        "large cap": "Large Cap",
        "flexi cap": "Flexi Cap",
        "small cap": "Small Cap",
        "balanced advantage": "Balanced Advantage",
    }
    for token, cat in mapping.items():
        if token in q:
            return cat
    return None


# ----------------------------------------------------------------------
# 4. Answer validation
# ----------------------------------------------------------------------
def validate_answer_chunks(
    retrieved_chunk_ids: List[str],
    answer_text: str,
) -> Tuple[bool, str]:
    pattern = re.compile(r"chunk_?(\d+)", re.IGNORECASE)
    found = set(pattern.findall(answer_text))
    if not found:
        return True, answer_text
    retrieved_set = {str(cid).lower() for cid in retrieved_chunk_ids}
    for fid in found:
        if fid not in retrieved_set:
            return False, answer_text + "\n*(Note: referenced chunk not retrieved.)*"
    return True, answer_text


# ----------------------------------------------------------------------
# 5. Groq API call with retry
# ----------------------------------------------------------------------
import time as _time
from groq import Groq, RateLimitError, InternalServerError, APIError

_MAX_RETRIES = 3
_BASE_BACKOFF = 1.5

def call_groq_llm(client: Groq, model: str, prompt: str, max_retries: int = _MAX_RETRIES) -> Optional[str]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0.2)
            return resp.choices[0].message.content
        except RateLimitError:
            _time.sleep(_BASE_BACKOFF * (2 ** (attempt - 1)))
        except InternalServerError:
            _time.sleep(_BASE_BACKOFF * (2 ** (attempt - 1)))
        except APIError:
            logging.error("Groq API error")
            return None
        except Exception as e:
            logging.warning(f"Unexpected error: {e}")
            _time.sleep(_BASE_BACKOFF)
    logging.error("Groq call failed after retries.")
    return None
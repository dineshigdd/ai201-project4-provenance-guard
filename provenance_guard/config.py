"""Configuration and shared constants for Provenance Guard.

Centralizes the few knobs the planning doc references (the Groq model, input
limits) so routes and signals don't hard-code them.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Semantic signal (Groq LLM judge), per planning §1.3 / §2 Signal 1 ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))

    # --- Input validation (planning §1.1: present, non-empty, max length) ---
    MAX_CONTENT_CHARS = int(os.getenv("MAX_CONTENT_CHARS", "20000"))
    MIN_CONTENT_CHARS = 1

    # --- Audit log (planning §1.7): append-only JSONL of every decision ---
    AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "data/audit_log.jsonl")

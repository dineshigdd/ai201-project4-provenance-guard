"""Audit log — a structured, append-only record of every attribution decision.

Planning §1.7: before responding, the pipeline appends an immutable record so
every decision is reconstructable later (this is what an appeal reviews against).

Format: JSON Lines (one JSON object per line) at `Config.AUDIT_LOG_PATH`. JSONL
is chosen over a single JSON array because appends are O(1) and never require
rewriting the file, and over SQLite because the schema is still evolving — it
stays trivially greppable and human-readable for this milestone. Milestone 4
extends the entry shape (signal 2 score, fused score, appeals); existing lines
stay valid because each line is self-describing.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from provenance_guard.config import Config

logger = logging.getLogger(__name__)

# Serialize writes so concurrent requests can't interleave partial lines.
_write_lock = threading.Lock()


def _utc_timestamp() -> str:
    """ISO 8601 UTC with millisecond precision and a 'Z' suffix."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def record_decision(
    *,
    content_id: str,
    creator_id: str | None,
    attribution: str,
    confidence: float | None,
    llm_score: float | None,
    structural_score: float | None = None,
    fused_p_ai: float | None = None,
    status: str = "classified",
) -> dict:
    """Append one structured decision entry and return it.

    Args:
        content_id:       unique id of the submission (the appeal key).
        creator_id:       who submitted it (may be None).
        attribution:      the attribution result returned to the caller.
        confidence:       the fused confidence shown with the result.
        llm_score:        Signal 1's p_ai (probability the text is AI-written).
        structural_score: Signal 2's p_ai (None until Signal 2 ran).
        fused_p_ai:       the blended probability the text is AI (None until fusion).
        status:           lifecycle marker for the entry.
    """
    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": _utc_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "structural_score": structural_score,
        "fused_p_ai": fused_p_ai,
        "status": status,
    }

    line = json.dumps(entry, ensure_ascii=False)
    path = Path(Config.AUDIT_LOG_PATH)

    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    logger.info("audit: recorded decision for content_id=%s", content_id)
    return entry


def read_entries(limit: int | None = None) -> list[dict]:
    """Read entries oldest-first (newest last). Returns [] if the log is absent.

    Provided for a future `GET /log` endpoint and for tests; the write path does
    not depend on it.
    """
    path = Path(Config.AUDIT_LOG_PATH)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as fh:
        entries = [json.loads(line) for line in fh if line.strip()]

    return entries[-limit:] if limit else entries

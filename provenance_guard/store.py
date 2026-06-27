"""Content + appeals store (planning §1 "Content status lifecycle", Flow 2).

A small JSON-file-backed store for mutable state the append-only audit log can't
hold: each content's current `content_status` (active -> under_review) and the
appeal records themselves (the "Appeals Store" in Flow 2). JSON files keep this
inspectable for the milestone; the access functions are the seam where a real
database would slot in later.
"""

import json
import threading
import uuid
from pathlib import Path

from provenance_guard.config import Config

# Read-modify-write on the JSON files must be atomic across requests. The lock is
# NOT reentrant, so public functions never call one another while holding it.
_lock = threading.Lock()


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# --- Content records --------------------------------------------------------

def register_content(content_id, creator_id, attribution, confidence) -> dict:
    """Record a freshly analyzed submission with `content_status = active`."""
    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "content_status": "active",
    }
    with _lock:
        data = _load(Config.CONTENT_STORE_PATH)
        data[content_id] = record
        _save(Config.CONTENT_STORE_PATH, data)
    return record


def get_content(content_id) -> dict | None:
    return _load(Config.CONTENT_STORE_PATH).get(content_id)


def set_content_status(content_id, status) -> dict | None:
    """Update a content's status (e.g. -> `under_review`). None if unknown id."""
    with _lock:
        data = _load(Config.CONTENT_STORE_PATH)
        record = data.get(content_id)
        if record is None:
            return None
        record["content_status"] = status
        _save(Config.CONTENT_STORE_PATH, data)
        return record


# --- Appeal records ---------------------------------------------------------

def create_appeal(content_id, creator_reasoning, claimed_attribution=None) -> dict:
    """Create an appeal with `appeal_status = open` (Flow 2: Appeals Store)."""
    appeal_id = uuid.uuid4().hex
    record = {
        "appeal_id": appeal_id,
        "content_id": content_id,
        "creator_reasoning": creator_reasoning,
        "claimed_attribution": claimed_attribution,
        "appeal_status": "open",
    }
    with _lock:
        data = _load(Config.APPEALS_STORE_PATH)
        data[appeal_id] = record
        _save(Config.APPEALS_STORE_PATH, data)
    return record


def get_appeal(appeal_id) -> dict | None:
    return _load(Config.APPEALS_STORE_PATH).get(appeal_id)

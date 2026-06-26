"""API routes — the contract from planning §4.

This step implements the `POST /submit` route and wires in Signal 1 (semantic).
The endpoint now returns a usable response: a unique `content_id`, the
attribution derived from Signal 1, a *placeholder* confidence, and a
*placeholder* label. The real confidence scorer/fusion (planning §2.5), Signal 2
(structural), the final transparency labeller (§3.5), and the audit log are
later steps — until then, confidence and label are clearly marked placeholders
carried straight from Signal 1 rather than a true fused verdict.

Field-naming note: the live request/response uses `text` and `content_id` (what
the appeal endpoint will key on). `content` is still accepted as an alias of
`text` so the planning §4 wording keeps working.
"""

import uuid

from flask import Blueprint, jsonify, request

from provenance_guard import audit
from provenance_guard.config import Config
from provenance_guard.fusion import fuse
from provenance_guard.signals.semantic import analyze_semantic
from provenance_guard.signals.structural import analyze_structural

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    """Liveness probe (planning §4)."""
    return jsonify({"status": "ok"})


@bp.get("/log")
def log():
    """Return recent audit-log entries as JSON (planning §1.7).

    Newest last. Optional `?limit=N` caps how many of the most recent entries
    are returned; omit it to return the full log.
    """
    limit = request.args.get("limit", type=int)
    return jsonify({"entries": audit.read_entries(limit=limit)})


def _validate_payload(payload):
    """Validate the submit payload per planning §1.1.

    Accepts `text` (preferred) or `content` (alias). Returns
    (text, title, creator_id, error); `error` is a (message, status) tuple on
    failure, else None.
    """
    if not isinstance(payload, dict):
        return None, None, None, ("Request body must be a JSON object.", 400)

    text = payload.get("text", payload.get("content"))
    title = payload.get("title")
    creator_id = payload.get("creator_id")

    if text is None or not isinstance(text, str) or not text.strip():
        return None, None, None, (
            "Field 'text' is required and must be non-empty text.",
            400,
        )

    if len(text) > Config.MAX_CONTENT_CHARS:
        return None, None, None, (
            f"Field 'text' exceeds the maximum of {Config.MAX_CONTENT_CHARS} characters.",
            413,
        )

    return text, title, creator_id, None


def _placeholder_label(attribution, strength):
    """A clearly-marked placeholder label (the real §3.5 labeller is next).

    Mirrors the final label's {level, badge, headline, body} shape so clients
    can render it now, and uses the fusion `strength` word, but the full §3.5
    copy (percentages, appeal wording) is not built yet.
    """
    if attribution == "uncertain":
        headline = "We couldn't tell who wrote this."
    elif attribution == "ai":
        headline = f"This content was {strength} created with AI."
    else:
        headline = f"This content was {strength} written by a person."
    return {
        "level": attribution,
        "badge": f"{attribution} (provisional)",
        "headline": headline,
        "body": (
            "Provisional label pending the final transparency labeller (§3.5)."
        ),
        "placeholder": True,
    }


@bp.post("/submit")
def submit():
    """Accept text content for attribution analysis (planning §1.1, §4, Flow 1).

    Current scope: validate -> assign content_id -> run Signal 1 (semantic) ->
    return attribution + placeholder confidence + placeholder label. Fusion,
    Signal 2, the final labeller, and the audit log arrive in later steps.
    """
    payload = request.get_json(silent=True)
    text, title, creator_id, error = _validate_payload(payload)
    if error:
        message, status = error
        return jsonify({"error": message}), status

    content_id = uuid.uuid4().hex

    # --- Run both signals (planning §2) ---
    semantic = analyze_semantic(text)
    structural = analyze_structural(text)

    # --- Fuse into one decision + confidence (planning §2.5) ---
    scored = fuse(semantic, structural)
    attribution = scored["attribution"]
    confidence = scored["confidence"]
    fused_p_ai = scored["fused_p_ai"]
    label = _placeholder_label(attribution, scored["strength"])

    # --- Audit log (planning §1.7): record every decision before responding. ---
    audit.record_decision(
        content_id=content_id,
        creator_id=creator_id,
        attribution=attribution,
        confidence=confidence,
        llm_score=semantic.get("p_ai"),
        structural_score=structural.get("p_ai"),
        fused_p_ai=fused_p_ai,
        status="classified",
    )

    response = {
        "content_id": content_id,
        "creator_id": creator_id,
        "title": title,
        "attribution": attribution,         # fused decision (planning §2.5)
        "confidence": confidence,           # fused confidence (planning §2.5)
        "fused_p_ai": fused_p_ai,           # blended probability the text is AI
        "label": label,                     # placeholder label (final labeller pending §3.5)
        "signals": {
            "semantic": semantic,
            "structural": structural,
        },
        "status": "classified",
    }
    return jsonify(response), 200

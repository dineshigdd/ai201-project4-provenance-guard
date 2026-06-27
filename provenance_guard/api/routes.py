"""API routes — the contract from planning §4.

Implements `POST /submit` (both signals + fusion + §3.5 label + audit), the
`GET /log` audit view, and the appeal flow (`POST /appeal`, `GET /appeal/<id>`)
from planning §1 and Flow 2.

Field-naming note: the live request/response uses `text` and `content_id` (what
the appeal endpoint keys on). `content` is still accepted as an alias of `text`
so the planning §4 wording keeps working.
"""

import uuid

from flask import Blueprint, jsonify, request

from provenance_guard import audit, store
from provenance_guard.api.extensions import limiter
from provenance_guard.config import Config
from provenance_guard.fusion import fuse
from provenance_guard.labels import build_label
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


@bp.post("/submit")
@limiter.limit(Config.SUBMIT_RATE_LIMIT)
def submit():
    """Accept text content for attribution analysis (planning §1.1, §4, Flow 1).

    validate -> assign content_id -> run both signals -> fuse -> §3.5 label ->
    register content (status `active`) -> audit -> respond.
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

    # --- Transparency label (planning §3.5) ---
    label = build_label(attribution, confidence, fused_p_ai)

    # --- Persist content with status `active` (lifecycle, for appeals) ---
    store.register_content(content_id, creator_id, attribution, confidence)

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
        "label": label,                     # transparency label (planning §3.5)
        "signals": {
            "semantic": semantic,
            "structural": structural,
        },
        "status": "classified",
    }
    return jsonify(response), 200


@bp.post("/appeal")
def appeal():
    """Contest a classification (planning §1 appeal path, Flow 2).

    Accepts `content_id` and `creator_reasoning`. Looks up the original decision,
    creates an appeal (`appeal_status = open`), flips the content's status to
    `under_review`, and writes an audit entry recording the status change.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    content_id = payload.get("content_id")
    creator_reasoning = payload.get("creator_reasoning")
    claimed_attribution = payload.get("claimed_attribution")  # optional

    if not content_id or not isinstance(content_id, str):
        return jsonify({"error": "Field 'content_id' is required."}), 400
    if (
        not creator_reasoning
        or not isinstance(creator_reasoning, str)
        or not creator_reasoning.strip()
    ):
        return jsonify(
            {"error": "Field 'creator_reasoning' is required and must be non-empty."}
        ), 400

    # Flow 2: look up the original decision before doing anything.
    content = store.get_content(content_id)
    if content is None:
        return jsonify({"error": f"No content found for content_id '{content_id}'."}), 404

    # Create the appeal (status open) and flip content status to "under review".
    appeal_record = store.create_appeal(content_id, creator_reasoning, claimed_attribution)
    updated = store.set_content_status(content_id, "under review")

    # Mirror the original signal scores into the appeal's audit entry (M3 shape).
    original = audit.latest_for(content_id) or {}
    audit.record_decision(
        content_id=content_id,
        creator_id=content.get("creator_id"),
        attribution=content.get("attribution"),
        confidence=content.get("confidence"),
        llm_score=original.get("llm_score"),
        structural_score=original.get("structural_score"),
        fused_p_ai=original.get("fused_p_ai"),
        appeal_id=appeal_record["appeal_id"],
        status="under review",
    )

    return jsonify(
        {
            "appeal_id": appeal_record["appeal_id"],
            "content_id": content_id,
            "appeal_status": appeal_record["appeal_status"],
            "content_status": updated["content_status"],
            "claimed_attribution": claimed_attribution,
            "message": "Your appeal has been received. This content is now under review.",
        }
    ), 201


@bp.get("/appeal/<appeal_id>")
def get_appeal(appeal_id):
    """Look up a single appeal by id (planning §4)."""
    record = store.get_appeal(appeal_id)
    if record is None:
        return jsonify({"error": f"No appeal found for appeal_id '{appeal_id}'."}), 404

    content = store.get_content(record["content_id"]) or {}
    return jsonify(
        {
            "appeal_id": record["appeal_id"],
            "content_id": record["content_id"],
            "appeal_status": record["appeal_status"],
            "content_status": content.get("content_status"),
            "claimed_attribution": record.get("claimed_attribution"),
            "creator_reasoning": record.get("creator_reasoning"),
        }
    )

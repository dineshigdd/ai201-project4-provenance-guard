"""Confidence scorer — fuses the two signals into one decision (planning §2.5).

Steps, exactly as §2.5 lays them out:

1. **Blend** the two `p_ai` probabilities into one `fused_p_ai`, a weighted
   average that trusts the stronger semantic signal more than the blunt
   structural one (~0.7 / 0.3).
2. **Derive confidence** from the blend with two ideas:
   - *Distance from 0.5*: confidence is how far the blend sits from "no idea"
     (`2 * |fused - 0.5|`), so a `fused_p_ai` of 0.5 -> 0 and near 0/1 -> high.
   - *Disagreement penalty*: if the two signals point opposite ways (opposite
     sides of 0.5), confidence is eroded — a strong disagreement roughly halves
     it.
3. **Threshold** into `uncertain` / `ai` / `human` by the §2.5 table.

Structural abstention: the structural heuristic is blunt on short/ambiguous text
and often returns a near-neutral score. When it lands within `STRUCTURAL_DEADBAND`
of 0.5 it abstains — the semantic signal alone sets `fused_p_ai` and no penalty
applies — so an inconclusive structural read can neither dilute a confident
semantic verdict nor manufacture a spurious disagreement penalty. It still
participates fully (blend + disagreement) whenever it has a clear, directional
read, which is what preserves the false-positive protection in §3.
"""

# Blend weights (planning §2.5: ~0.7 semantic / 0.3 structural).
SEMANTIC_WEIGHT = 0.7
STRUCTURAL_WEIGHT = 0.3

# A maximal directional disagreement (one signal at 0, the other at 1) multiplies
# confidence by (1 - 0.5) = 0.5, i.e. "roughly halves it" (planning §2.5).
DISAGREEMENT_WEIGHT = 0.5

# The single gate between "uncertain" and a directional verdict (planning §2.5).
CONFIDENCE_GATE = 0.50

# The structural heuristic is documented as blunt/noisy on short or ambiguous
# text. When its score lands within this band of neutral (0.5), it is treated as
# "no read" and abstains: the semantic signal decides and no disagreement penalty
# is applied. This stops an inconclusive structural score from both diluting a
# confident semantic verdict and manufacturing a spurious disagreement penalty.
STRUCTURAL_DEADBAND = 0.10

# Strength-word bands within a directional verdict (planning §2.5).
STRENGTH_VERY_LIKELY = 0.85
STRENGTH_LIKELY = 0.65


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def strength_word(confidence: float) -> str:
    """Map a directional confidence to its §2.5 strength word.

    Shared by the labeller (§3.5) so wording bands have a single source of truth.
    """
    if confidence >= STRENGTH_VERY_LIKELY:
        return "very likely"
    if confidence >= STRENGTH_LIKELY:
        return "likely"
    return "possibly"


def fuse(semantic: dict, structural: dict) -> dict:
    """Blend the two signals and apply the §2.5 threshold logic.

    Returns: {fused_p_ai, confidence, attribution, strength, disagreement}.
    `strength` is None for an `uncertain` outcome; `disagreement` is None when
    the semantic signal was unavailable (no second opinion to disagree with).
    """
    p_struct = structural["p_ai"]
    p_sem = semantic.get("p_ai", 0.5)
    semantic_available = bool(semantic.get("available"))

    structural_informative = abs(p_struct - 0.5) >= STRUCTURAL_DEADBAND

    if semantic_available and structural_informative:
        # Both signals have a read: weighted blend (weights sum to 1).
        fused = SEMANTIC_WEIGHT * p_sem + STRUCTURAL_WEIGHT * p_struct

        # Disagreement only counts when the signals point to *opposite sides* of
        # 0.5 (both are now meaningfully directional, so this is a real conflict).
        if (p_sem - 0.5) * (p_struct - 0.5) < 0:
            disagreement = abs(p_sem - p_struct)
        else:
            disagreement = 0.0
        penalty = 1.0 - DISAGREEMENT_WEIGHT * disagreement
    elif semantic_available:
        # Structural is inconclusive (near neutral) -> it abstains and the
        # semantic signal decides. No penalty: an abstaining signal is not a
        # disagreeing one, and it must not dilute a confident semantic verdict.
        fused = p_sem
        disagreement = 0.0
        penalty = 1.0
    else:
        # Semantic down -> rely on the structural signal alone (planning §2 blind
        # spot / graceful degradation). No second opinion, so no penalty.
        fused = p_struct
        disagreement = None
        penalty = 1.0

    base_confidence = 2.0 * abs(fused - 0.5)  # distance from 0.5 -> [0, 1]
    confidence = _clamp01(base_confidence * penalty)

    if confidence < CONFIDENCE_GATE:
        attribution = "uncertain"
        strength = None
    elif fused >= 0.5:
        attribution = "ai"
        strength = strength_word(confidence)
    else:
        attribution = "human"
        strength = strength_word(confidence)

    return {
        "fused_p_ai": round(fused, 4),
        "confidence": round(confidence, 4),
        "attribution": attribution,
        "strength": strength,
        "disagreement": round(disagreement, 4) if disagreement is not None else None,
    }

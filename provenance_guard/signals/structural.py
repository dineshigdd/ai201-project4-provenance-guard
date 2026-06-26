"""Signal 2 — Structural analyzer (stylometric heuristics, pure Python).

Planning §2 "Signal 2" and §2.5: judge the *form* of the text locally (no network
call) via two statistics, and map them to `p_ai_structural ∈ [0, 1]` — near 1.0
when the text looks uniform/repetitive (AI-like), near 0.0 when bursty/varied
(human-like), 0.5 when there isn't enough text to judge.

  - **Sentence-length burstiness (primary):** coefficient of variation (CV) of
    per-sentence word counts. Human prose mixes long and short sentences (high
    CV); LLM prose trends toward uniform pacing (low CV).
  - **Type-Token Ratio (secondary, damped):** unique words / total words. Very
    repetitive/templated text (low TTR) nudges AI-ward. Length-dependent, so it
    is weighted lightly.
"""

import re
import statistics

# Reference points for the burstiness CV -> p_ai mapping (planning §2.5):
#   CV ~0.70 (very bursty, human-like) -> ~0.0
#   CV ~0.20 (very uniform, AI-like)   -> ~1.0
_CV_HUMAN = 0.70
_CV_AI = 0.20

# Reference points for the TTR -> p_ai mapping (secondary):
#   TTR ~0.75 (varied/human)    -> 0.0
#   TTR ~0.35 (repetitive/AI)   -> 1.0
_TTR_HUMAN = 0.75
_TTR_AI = 0.35

# Burstiness is the primary signal; TTR is a damped nudge (planning §2.5).
_CV_WEIGHT = 0.75
_TTR_WEIGHT = 0.25

# Below this many sentences, sentence-length variance is too noisy to judge.
MIN_SENTENCES = 2

_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_WORD = re.compile(r"\b\w+\b")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _linear_map(value: float, at_zero: float, at_one: float) -> float:
    """Map `value` to [0, 1] (clamped) given two reference points.

    `at_zero` maps to 0.0 and `at_one` maps to 1.0; values in between
    interpolate linearly, values outside clamp.
    """
    if at_one == at_zero:
        return 0.5
    return _clamp01((value - at_zero) / (at_one - at_zero))


def _sentences(text: str) -> list[str]:
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT.split(text)) if s]


def _word_count(text: str) -> int:
    return len(_WORD.findall(text))


def analyze_structural(text: str) -> dict:
    """Run the structural signal on `text`.

    Returns the `signals.structural` shape from planning §4:
        {p_ai, features: {ttr, sentence_length_cv, num_sentences, num_tokens}}
    """
    sentences = _sentences(text)
    tokens = _WORD.findall(text.lower())
    num_sentences = len(sentences)
    num_tokens = len(tokens)

    ttr = round(len(set(tokens)) / num_tokens, 4) if num_tokens else 0.0

    # --- Burstiness CV (primary) ---
    cv = None
    if num_sentences >= MIN_SENTENCES:
        per_sentence = [_word_count(s) for s in sentences]
        mean = statistics.mean(per_sentence)
        if mean > 0:
            cv = statistics.pstdev(per_sentence) / mean

    if cv is None:
        # Not enough text to judge form -> neutral, low-information (planning §2.5).
        p_ai = 0.5
        sentence_length_cv = None
    else:
        p_cv = _linear_map(cv, _CV_HUMAN, _CV_AI)
        p_ttr = _linear_map(ttr, _TTR_HUMAN, _TTR_AI)
        p_ai = _clamp01(_CV_WEIGHT * p_cv + _TTR_WEIGHT * p_ttr)
        sentence_length_cv = round(cv, 4)

    return {
        "p_ai": round(p_ai, 4),
        "features": {
            "ttr": ttr,
            "sentence_length_cv": sentence_length_cv,
            "num_sentences": num_sentences,
            "num_tokens": num_tokens,
        },
    }

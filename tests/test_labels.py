"""Transparency-label reachability tests (planning §3.5).

Goal: prove all three label variants — high-confidence AI, high-confidence
human, and uncertain — are reachable by feeding inputs that produce different
confidence levels through the *real* pipeline (fuse -> build_label), not by
calling build_label with hand-picked arguments.

Each case supplies the two per-signal probabilities a submission would produce,
runs them through fusion (which derives the confidence and attribution per
§2.5), then through the labeller, and asserts the exact §3.5 copy. The signals
are driven directly (instead of live text) so the test is deterministic and
needs no network / API key.

Run from the project root:  python tests/tranparency_label.test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance_guard.fusion import fuse
from provenance_guard.labels import build_label


def _semantic(p_ai, available=True):
    """Shape a semantic-signal result like analyze_semantic() returns."""
    return {
        "available": available,
        "p_ai": p_ai,
        "attribution": "likely_ai" if p_ai >= 0.5 else "likely_human",
        "confidence": round(abs(p_ai - 0.5) * 2, 4),
        "reason": "test fixture",
    }


def _structural(p_ai):
    return {"p_ai": p_ai, "features": {}}


def _analyze(semantic_p, structural_p, semantic_available=True):
    """Inputs -> confidence/attribution (fusion §2.5) -> label (§3.5)."""
    scored = fuse(_semantic(semantic_p, semantic_available), _structural(structural_p))
    label = build_label(scored["attribution"], scored["confidence"], scored["fused_p_ai"])
    return scored, label


# Each case: a label, the per-signal inputs, and the exact §3.5 strings the
# resulting variant must show.
CASES = [
    {
        "name": "High-confidence AI",
        "semantic_p": 0.95,            # LLM: strongly AI
        "structural_p": 0.90,          # uniform/repetitive: AI-like -> agree, high confidence
        "expect_level": "ai",
        "expect_badge": "AI-generated (estimated)",
        "expect_headline_tail": "created with AI.",
        "expect_pct_in_body": True,
    },
    {
        "name": "High-confidence human",
        "semantic_p": 0.05,            # LLM: strongly human
        "structural_p": 0.10,          # bursty/varied: human-like -> agree, high confidence
        "expect_level": "human",
        "expect_badge": "Human-written (estimated)",
        "expect_headline_tail": "written by a person.",
        "expect_pct_in_body": True,
    },
    {
        "name": "Uncertain (signals disagree)",
        "semantic_p": 0.20,            # LLM: human
        "structural_p": 0.85,          # structural: AI -> opposite sides, confidence eroded below gate
        "expect_level": "uncertain",
        "expect_badge": "Origin unclear",
        "expect_headline": "We couldn't tell who wrote this.",
        "expect_pct_in_body": False,
    },
]


def run_tests():
    failures = []
    seen_levels = set()

    header = f"{'Case':<32} | {'confidence':<10} | {'variant':<10} | result"
    print(header)
    print("-" * len(header))

    for case in CASES:
        scored, label = _analyze(case["semantic_p"], case["structural_p"])
        seen_levels.add(label["level"])

        errors = []
        if label["level"] != case["expect_level"]:
            errors.append(f"level {label['level']!r} != {case['expect_level']!r}")
        if label["badge"] != case["expect_badge"]:
            errors.append(f"badge {label['badge']!r} != {case['expect_badge']!r}")
        if "expect_headline" in case and label["headline"] != case["expect_headline"]:
            errors.append(f"headline {label['headline']!r} != {case['expect_headline']!r}")
        if "expect_headline_tail" in case and not label["headline"].endswith(
            case["expect_headline_tail"]
        ):
            errors.append(
                f"headline {label['headline']!r} !endswith {case['expect_headline_tail']!r}"
            )
        has_pct = "% chance" in label["body"]
        if has_pct != case["expect_pct_in_body"]:
            errors.append(f"body %-chance present={has_pct}, expected {case['expect_pct_in_body']}")

        status = "PASS" if not errors else "FAIL: " + "; ".join(errors)
        if errors:
            failures.append(case["name"])
        print(f"{case['name']:<32} | {scored['confidence']:<10.2f} | {label['level']:<10} | {status}")

    # The headline requirement: all three variants must be reachable.
    print()
    required = {"ai", "human", "uncertain"}
    missing = required - seen_levels
    if missing:
        failures.append(f"unreachable variants: {sorted(missing)}")
        print(f"REACHABILITY FAIL: variants not produced: {sorted(missing)}")
    else:
        print("REACHABILITY PASS: all three variants reached via different confidence levels.")

    if failures:
        print(f"\n{len(failures)} failure(s).")
        sys.exit(1)
    print("\nAll transparency-label tests passed.")


if __name__ == "__main__":
    run_tests()

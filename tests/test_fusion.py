"""Fusion / confidence-scorer tests (planning §2.5).

Deterministic checks that drive `fuse()` with controlled per-signal scores — no
network needed. These lock in the confidence-scoring behavior, including the
structural-abstention rule that fixes a confident semantic verdict being diluted
to "uncertain" by a blunt, near-neutral structural score.

Run from the project root:  python tests/test_fusion.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance_guard.fusion import STRUCTURAL_DEADBAND, fuse


def _semantic(p_ai, available=True):
    return {
        "available": available,
        "p_ai": p_ai,
        "attribution": "likely_ai" if p_ai >= 0.5 else "likely_human",
        "confidence": round(abs(p_ai - 0.5) * 2, 4),
        "reason": "test fixture",
    }


def _structural(p_ai):
    return {"p_ai": p_ai, "features": {}}


# name, semantic p_ai, structural p_ai, expected attribution, note
CASES = [
    ("Agree AI (both confident)",        0.95, 0.90, "ai",        "blend -> high confidence"),
    ("Agree human (both confident)",     0.05, 0.10, "human",     "blend -> high confidence"),
    ("Disagree: confident + confident",  0.20, 0.85, "uncertain", "false-positive protection (§6)"),
    # The regression the fix targets: confident semantic AI, near-neutral structural.
    ("Abstain: confident AI + blunt",    0.80, 0.48, "ai",        "structural abstains -> semantic carries"),
    ("Abstain: confident human + blunt", 0.20, 0.52, "human",     "structural abstains -> semantic carries"),
    ("Both neutral",                     0.50, 0.50, "uncertain", "no signal -> below gate"),
]


def run_tests():
    failures = []

    header = f"{'Case':<34} | {'sem':<5} | {'str':<5} | {'fused':<6} | {'conf':<5} | {'attr':<9} | result"
    print(header)
    print("-" * len(header))

    for name, sem_p, str_p, expect_attr, _note in CASES:
        r = fuse(_semantic(sem_p), _structural(str_p))
        ok = r["attribution"] == expect_attr
        if not ok:
            failures.append(f"{name}: got {r['attribution']!r}, expected {expect_attr!r}")
        status = "PASS" if ok else f"FAIL (expected {expect_attr})"
        print(
            f"{name:<34} | {sem_p:<5} | {str_p:<5} | {r['fused_p_ai']:<6} | "
            f"{r['confidence']:<5} | {r['attribution']:<9} | {status}"
        )

    # Explicit guard on the abstention rule: a structural score inside the
    # deadband must not change fused_p_ai away from the semantic score.
    inside = 0.5 + STRUCTURAL_DEADBAND / 2  # comfortably within the band
    r = fuse(_semantic(0.80), _structural(inside))
    if abs(r["fused_p_ai"] - 0.80) > 1e-9:
        failures.append(
            f"abstention: fused {r['fused_p_ai']} != semantic 0.80 for structural={inside}"
        )
        print(f"\nABSTENTION FAIL: fused {r['fused_p_ai']} != 0.80 for near-neutral structural")
    else:
        print("\nABSTENTION PASS: near-neutral structural does not move fused_p_ai off the semantic score.")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("\nAll fusion tests passed.")


if __name__ == "__main__":
    run_tests()

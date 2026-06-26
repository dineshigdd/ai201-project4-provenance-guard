"""Smoke test for the detection pipeline across a spread of inputs.

Composes the real signals + fusion (planning §2, §2.5) the same way `/submit`
does, and prints attribution / confidence / fused_p_ai per case. Run from the
project root:  python tests/test.py
(Note: the semantic signal makes a live Groq call, so GROQ_API_KEY must be set;
without it that signal degrades to neutral and fusion falls back to structural.)
"""

import sys
from pathlib import Path

# Make the project root importable when run as `python tests/test.py`
# (Python only puts the script's own dir, tests/, on sys.path by default).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance_guard.fusion import fuse
from provenance_guard.signals.semantic import analyze_semantic
from provenance_guard.signals.structural import analyze_structural


def analyze_text(text):
    """Run both signals and fuse them, mirroring the /submit pipeline."""
    semantic = analyze_semantic(text)
    structural = analyze_structural(text)
    return fuse(semantic, structural)


def run_tests():
    test_cases = [
        {
            "name": "Clearly AI",
            "text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."
        },
        {
            "name": "Clearly Human",
            "text": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there"
        },
        {
            "name": "Formal Human (Borderline)",
            "text": "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."
        },
        {
            "name": "Edited AI (Borderline)",
            "text": "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type."
        }
    ]

    header = f"{'Test Case':<25} | {'Attribution':<12} | {'Confidence':<10} | {'fused_p_ai':<10}"
    print(header)
    print("-" * len(header))

    for case in test_cases:
        try:
            result = analyze_text(case["text"])
        except Exception as exc:  # noqa: BLE001 - keep the table going on a failure
            print(f"{case['name']:<25} | {'ERROR':<12} | {str(exc)[:23]}")
            continue

        print(
            f"{case['name']:<25} | {result['attribution']:<12} | "
            f"{result['confidence']:<10.2f} | {result['fused_p_ai']:<10.2f}"
        )


if __name__ == "__main__":
    run_tests()
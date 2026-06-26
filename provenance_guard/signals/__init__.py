"""Detection signals.

Each signal reads the raw text and emits a normalized probability that the text
is AI-written (`p_ai` in [0, 1]), per planning §2.5. Signal 1 (semantic) is
implemented here; Signal 2 (structural) and fusion arrive in a later step.
"""

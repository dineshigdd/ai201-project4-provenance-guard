# Project Name: [Insert Project Name]

## 1. Architecture Overview
Submissions are first gated by a rate-limiting layer to prevent abuse. Once a request is authenticated as genuine, it enters the Detection Pipeline, where it is processed by two independent signals: Signal 1 (LLM-based semantic analysis) and Signal 2 (stylometric structural heuristics). These signals are passed to a Fusion/Confidence Scorer, which calculates a calibrated confidence score. This score is then mapped by the Transparency Labeler to produce the final user-facing verdict. Every stage of this process, including subsequent appeals, is recorded in a structured audit log to ensure system transparency and accountability.


## 2. Detection Signals
### Semantic Signal

**What it measures**:
 captures the contextual meaning of the text entered by analyzing  tone, voice, semantic coherence, logical flow, specificity, and the tell-tale patterns of LLM prose ,hedging, generic balance, and tidy summarizing conclusions. 
 
 **Why do we need Semantic Signal?**:
 The Semantic Signal acts as the system's 'intuition' for authorship. While we use automated checks to spot unnatural patterns in the writing's structure, the semantic signal evaluates the underlying coherence and argumentative style of the text. It is designed to capture the characteristic 'neutral' and 'hedging' tone typical of synthetic generation, providing a necessary counterpoint to purely statistical structural analysis.

**Semantic Signal: Limitations & Blind Spots**
While the Semantic Signal provides high-level analysis of content coherence and style, it operates as a probabilistic model. Its limitations must be considered for accurate system evaluation:

* **Non-deterministic Output:** The model may produce different classification results for the same input across multiple requests. This variance is inherent to the underlying architecture and means that attribution is not perfectly repeatable.

* **Adversarial Sensitivity:** The signal is susceptible to adversarial prompting. An adversary can explicitly instruct an LLM to "write like a human" or adopt a specific stylistic mimicry, which can bypass the detection logic.

* **Calibration Error (False Certainty):** As a probabilistic system, it can generate high-confidence scores for incorrect classifications. It may present a "Human" or "AI" label with high confidence even when the content is ambiguous or misidentified.

* **Computational Latency and Cost:** Every invocation requires a network round-trip and token consumption. This introduces both architectural latency and per-request operational costs that must be balanced against system performance requirements.

* **Lack of Ground Truth:** The output is a statistical estimation rather than an objective fact. There is no verifiable "ground truth" for authorship; the signal provides an informed classification based on training data patterns, not an absolute determination.

### Structural Signal
**What it measures**
measures the statiscal properties such as  sentence length variance, type-token ratio, punctuation density of the text entered.

 **Why do we need Structural Signal?**:
 The Structural signal provides an objective, mathematical baseline for our detection pipeline. By analyzing the physical patterns of the text—such as sentence length, punctuation variety, and rhythmic 'burstiness'—we can identify writing that is structurally uniform or 'robotic.' This acts as a necessary counterweight to our semantic analysis, ensuring that our attribution is based on both the meaning (semantic) and the architecture (structural) of the content.

To make this accessible to both non-technical readers and developers, you can frame these as **"Signal Constraints."** This keeps the professional, technical tone while clearly explaining the practical "why" behind the limitations.

**Structural Signal: Constraints & Blind Spots**:

While the Structural Signal provides a reliable, mathematical baseline, it is bound by the following technical constraints:

* **Sensitivity to Input Length:** The signal is less reliable on short passages. Because it relies on measuring variance across sentences, short texts often lack enough data points to produce a statistically significant reading.

* **Metric Bias (Length-Dependency):** Specific metrics, such as Type-Token Ratio (TTR), naturally inflate on shorter passages. Consequently, we assign these metrics a lower weight in our overall scoring to avoid false positives.

* **Lack of Semantic Context:** This signal is "content-blind." It measures rhythm and structure, not meaning. It cannot distinguish between a sophisticated, well-reasoned essay and nonsensical "gibberish," provided both share a similar rhythmic pattern.

* **Susceptibility to Stylistic Mimicry:** Because this signal relies on measurable patterns (like sentence length and punctuation), it can be circumvented by an adversary who deliberately introduces structural variation—such as alternating between very short and very long sentences—to mimic human "burstiness."

## 3. Confidence Scoring
The **Semantic** and **Structural** signals are fused into a single, unified score to balance their respective strengths. Because the Semantic signal is powerful but opaque and gameable, and the Structural signal is weak but transparent and deterministic, combining these signals ensures system robustness. Since these signals fail on different inputs, their agreement increases confidence. Conversely, any disagreement serves as direct evidence of uncertainty, which is factored into the final score.

> Logic: We map both signals to a normalized probability ($p_{ai} \in [0, 1]$). We then calculate a fused_p_ai using a weighted average (70% Semantic, 30% Structural). The final confidence score is derived by measuring the distance of this blend from the "uncertain" midpoint (0.50), further adjusted by a "disagreement penalty" that erodes confidence when the two signals point in opposite directions.

> Validation: I validated this by passing controlled input pairs—disagreeing signals vs. agreeing signals—to ensure the confidence score properly trended toward "uncertain" when signals diverged. I specifically tested against a fixture set of clear-human, clear-AI, and ambiguous/short texts to confirm that the scores are well-ordered and that the "uncertain" threshold correctly catches low-conviction verdicts.
- Examples:
    - High-Confidence Case: An AI-generated essay with uniform sentence lengths and repetitive patterns where both the Semantic signal (high-confidence AI) and Structural signal (uniformity) agree. | Score: 0.95 (Very likely AI)  

    - Lower-Confidence Case: A short, ambiguous paragraph where the Semantic signal leans "AI" but the Structural signal finds high "burstiness" (human-like rhythm), causing the disagreement penalty to trigger. | Score: 0.45 (Uncertain)

    - Uncertain Case: A submission where the Semantic signal is neutral (due to a lack of clear argumentative style) and the Structural signal returns a 0.50 (due to insufficient length to measure variance), resulting in a failure to clear the confidence gate. | Score: 0.30 (Uncertain)

## 4. Transparency Label
| Variant | Headline | Body Text |
| :--- | :--- | :--- |
| **High-Confidence AI** | "This content was very likely created with AI." | "Our automated check estimates a {pct}% chance this text was generated by an AI tool, based on its writing style and language patterns. This is an estimate, not a certainty. If you're the creator and believe this is wrong, you can appeal." |
| **High-Confidence Human** | "This content was very likely written by a person." | "Our automated check estimates a {pct}% chance this text was written by a human, based on its writing style and language patterns. This is an estimate, not a certainty. If you're the creator and believe this is wrong, you can appeal." |
| **Uncertain** | "We couldn't tell who wrote this." | "Our automated checks didn't find a strong enough signal to say whether this text was written by a person or generated by AI — the evidence was mixed or the passage was too short to judge. We're showing no attribution rather than guess. Creators can add a disclosure, and either side can appeal." |


## 5. Rate Limiting
*   **Limit:** [e.g., 5 requests per minute]
*   **Reasoning:** This limit reasonably prevents automated scraping while allowing a real human writer enough headroom to test different variations of their text.

## 6. Known Limitations

* **Content Type:** tightly-crafted poems.
* **Why:** The structural signal requires sufficient sentence-length variance to calculate a statistically significant "burstiness" metric. In minimalist, tightly-crafted poems with deliberately uniform line lengths, this variance is absent, causing the structural signal to falsely register the content as "AI-generated." The system mitigates this risk through a disagreement penalty that erodes confidence when the semantic and structural signals conflict, defaulting to an `uncertain` label rather than a false accusation, while providing an appeals workflow to allow for human review.


## 7. Spec Reflection
*  **How the spec helped:**
    The planning process improved my understanding of each system component, allowing for a precise architecture before writing any code. Additionally, the spec helped me critically evaluate the strengths and weaknesses of the system, ensuring that edge cases and limitations were considered from the start.

*   **Implementation divergence:**
 The label table hard-codes a single strength phrasing — every directional verdict reads "This content was very likely created with AI" / "...very likely written by a person." Only three label variants exist: High-Confidence AI, High-Confidence Human, Uncertain.

What the implementation does: `labels.py:40` pulls a graduated strength word from `fusion.py:38-47`, which has three bands:
```
confidence ≥ 0.85 → "very likely"
confidence ≥ 0.65 → "likely"
otherwise → "possibly"

```
So the headline is templated as `f"This content was {strength} created with AI."` and can emit "likely" or "possibly" — wording that never appears in the README table.

Why it diverged: The confidence gate `(fusion.py:27)` opens a directional verdict at 0.50, but the README's flat "very likely" copy would then slap maximum-certainty language on a verdict sitting just barely over the gate (confidence ~0.51). That overclaims. Graduating the strength word lets the headline's tone track the actual confidence — a 0.55 verdict says "possibly," a 0.90 verdict says "very likely" — which is more honest and is consistent with the project's stated transparency/anti-false-certainty goals.

## 8. AI Usage

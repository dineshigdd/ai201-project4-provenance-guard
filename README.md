# Project Name:  Provenance Guard

## 1. Architecture Overview
Submissions are first gated by a rate-limiting layer to prevent abuse. Once a request is authenticated as genuine, it enters the Detection Pipeline, where it is processed by two independent signals: Signal 1 (LLM-based semantic analysis) and Signal 2 (stylometric structural heuristics). These signals are passed to a Fusion/Confidence Scorer, which calculates a calibrated confidence score. This score is then mapped by the Transparency Labeler to produce the final user-facing verdict. Every stage of this process, including subsequent appeals, is recorded in a structured audit log to ensure system transparency and accountability.


## 2. Detection Signals
### Semantic Signal

**What it measures**:
 captures the contextual meaning of the text entered by analyzing  tone, voice, semantic coherence, logical flow, specificity, and the tell-tale patterns of LLM prose ,hedging, generic balance, and tidy summarizing conclusions. 
 
 **Why do we need Semantic Signal?**:
 The Semantic Signal acts as the system's 'intuition' for authorship. While we use automated checks to spot unnatural patterns in the writing's structure, the semantic signal evaluates the underlying coherence and argumentative style of the text. It is designed to capture the characteristic 'neutral' and 'hedging' tone typical of synthetic generation, providing a necessary counterpoint to purely statistical structural analysis.

**Semantic Signal: Constraints & Blind Spots**
While the Semantic Signal provides high-level analysis of content coherence and style, it operates as a probabilistic model. Its limitations must be considered for accurate system evaluation:

    - **Non-deterministic Output:** The model may produce different classification results for the same input across multiple requests. This variance is inherent to the underlying architecture and means that attribution is not perfectly repeatable.

    - **Adversarial Sensitivity:** The signal is susceptible to adversarial prompting. An adversary can explicitly instruct an LLM to "write like a human" or adopt a specific stylistic mimicry, which can bypass the detection logic.

    - **Calibration Error (False Certainty):** As a probabilistic system, it can generate high-confidence scores for incorrect classifications. It may present a "Human" or "AI" label with high confidence even when the content is ambiguous or misidentified.

    - **Computational Latency and Cost:** Every invocation requires a network round-trip and token consumption. This introduces both architectural latency and per-request operational costs that must be balanced against system performance requirements.

    - **Lack of Ground Truth:** The output is a statistical estimation rather than an objective fact. There is no verifiable "ground truth" for authorship; the signal provides an informed classification based on training data patterns, not an absolute determination.

### Structural Signal
**What it measures**
measures the statiscal properties such as  sentence length variance, type-token ratio, punctuation density of the text entered.

 **Why do we need Structural Signal?**:
 The Structural signal provides an objective, mathematical baseline for our detection pipeline. By analyzing the physical patterns of the text—such as sentence length, punctuation variety, and rhythmic 'burstiness'—we can identify writing that is structurally uniform or 'robotic.' This acts as a necessary counterweight to our semantic analysis, ensuring that our attribution is based on both the meaning (semantic) and the architecture (structural) of the content.

To make this accessible to both non-technical readers and developers, you can frame these as **"Signal Constraints."** This keeps the professional, technical tone while clearly explaining the practical "why" behind the limitations.

**Structural Signal: Constraints & Blind Spots**:
While the Structural Signal provides a reliable, mathematical baseline, it is bound by the following technical constraints:

    - **Sensitivity to Input Length:** The signal is less reliable on short passages. Because it relies on measuring variance across sentences, short texts often lack enough data points to produce a statistically significant reading.

    - **Metric Bias (Length-Dependency):** Specific metrics, such as Type-Token Ratio (TTR), naturally inflate on shorter passages. Consequently, we assign these metrics a lower weight in our overall scoring to avoid false positives.

    - **Lack of Semantic Context:** This signal is "content-blind." It measures rhythm and structure, not meaning. It cannot distinguish between a sophisticated, well-reasoned essay and nonsensical "gibberish," provided both share a similar rhythmic pattern.

    - **Susceptibility to Stylistic Mimicry:** Because this signal relies on measurable patterns (like sentence length and punctuation), it can be circumvented by an adversary who deliberately introduces structural variation—such as alternating between very short and very long sentences—to mimic human "burstiness."

## 3. Confidence Scoring
The **Semantic** and **Structural** signals are fused into a single, unified score to balance their respective strengths. Because the Semantic signal is powerful but opaque and gameable, and the Structural signal is weak but transparent and deterministic, combining these signals ensures system robustness. Since these signals fail on different inputs, their agreement increases confidence. Conversely, any disagreement serves as direct evidence of uncertainty, which is factored into the final score.

> Logic: We map both signals to a normalized probability ($p_{ai} \in [0, 1]$). We then calculate a fused_p_ai using a weighted average (70% Semantic, 30% Structural). The final confidence score is derived by measuring the distance of this blend from the "uncertain" midpoint (0.50), further adjusted by a "disagreement penalty" that erodes confidence when the two signals point in opposite directions.

> Structural abstention: Because the structural heuristic is blunt on short or ambiguous text, it **abstains** whenever its score lands within ±0.10 of the midpoint (0.40–0.60). When it abstains, the semantic signal alone sets `fused_p_ai` and no disagreement penalty is applied — so an inconclusive structural read can neither dilute a confident semantic verdict nor manufacture a false disagreement. The structural signal only participates in the blend and the disagreement penalty when it has a clear, directional read (outside that band), which is what preserves the false-positive protection for genuinely conflicting confident signals (see §6).

> Validation: I validated this by passing controlled input pairs—disagreeing signals vs. agreeing signals—to ensure the confidence score properly trended toward "uncertain" when signals diverged. I specifically tested against a fixture set of clear-human, clear-AI, and ambiguous/short texts to confirm that the scores are well-ordered and that the "uncertain" threshold correctly catches low-conviction verdicts.
**Examples:**
    - High-Confidence Case: An AI-generated essay with uniform sentence lengths and repetitive patterns where both the Semantic signal (high-confidence AI) and Structural signal (uniformity) agree. | Score: 0.95 (Very likely AI)  

    - Lower-Confidence Case: A short, ambiguous paragraph where the Semantic signal leans "AI" but the Structural signal finds high "burstiness" (a confident, human-like rhythm outside the abstention band), causing the disagreement penalty to trigger. | Score: 0.45 (Uncertain)

    - Structural-Abstained Case: A short, formal passage where the Semantic signal confidently reads "AI" (~0.80) but the Structural signal lands near neutral (~0.48) because there is too little text to judge rhythm. The Structural signal abstains, so the semantic verdict carries instead of being diluted into "uncertain." | fused_p_ai 0.80, confidence 0.60 → AI ("possibly")

    - Uncertain Case: A submission where the Structural signal is inconclusive (near 0.50, from insufficient length) and therefore abstains, while the Semantic signal is also neutral (no clear argumentative style). With only a neutral semantic read, the blend sits at the midpoint and fails to clear the confidence gate. | Score: 0.30 (Uncertain)

## 4. Transparency Label
| Variant | Headline | Body Text |
| :--- | :--- | :--- |
| **High-Confidence AI** | "This content was very likely created with AI." | "Our automated check estimates a {pct}% chance this text was generated by an AI tool, based on its writing style and language patterns. This is an estimate, not a certainty. If you're the creator and believe this is wrong, you can appeal." |
| **High-Confidence Human** | "This content was very likely written by a person." | "Our automated check estimates a {pct}% chance this text was written by a human, based on its writing style and language patterns. This is an estimate, not a certainty. If you're the creator and believe this is wrong, you can appeal." |
| **Uncertain** | "We couldn't tell who wrote this." | "Our automated checks didn't find a strong enough signal to say whether this text was written by a person or generated by AI — the evidence was mixed or the passage was too short to judge. We're showing no attribution rather than guess. Creators can add a disclosure, and either side can appeal." |

## 5. Rate Limiting
    - **Limit:** 200 per day and 10 per minute
    - **Reasoning:** This limit reasonably prevents automated scraping while allowing a real human writer enough headroom to test different variations of their text.

## 6. Audit Log
- The system maintains a comprehensive audit log that records every attribution decision and subsequent appeal. You can access the structured event history by navigating to `http://localhost:5000/log`. Below are representative entries from the log:

    ```JSON
    {
        "appeal_id": "3fe5832e44c3408ea1bcbdc101034357",
        "attribution": "human",
        "confidence": 0.7,
        "content_id": "4d770c5d285d49b09f4eabdd55cec2cf",
        "creator_id": "u1",
        "fused_p_ai": 0.15,
        "llm_score": 0.5,
        "status": "under review",
        "structural_score": 0.15,
        "timestamp": "2026-06-27T08:37:10.519Z"
    },
    {
        "appeal_id": null,
        "attribution": "uncertain",
        "confidence": 0.3435,
        "content_id": "1ff5ddf812354c7b96cea40b832cabd2",
        "creator_id": null,
        "fused_p_ai": 0.7043,
        "llm_score": 0.8,
        "status": "classified",
        "structural_score": 0.4811,
        "timestamp": "2026-07-01T02:47:47.621Z"
    },
    {
        "appeal_id": null,
        "attribution": "ai",
        "confidence": 0.6,
        "content_id": "7787dac5430f438cac269a51340051aa",
        "creator_id": null,
        "fused_p_ai": 0.8,
        "llm_score": 0.8,
        "status": "classified",
        "structural_score": 0.4811,
        "timestamp": "2026-07-01T03:05:39.481Z"
    },
    {
        "appeal_id": "3fe5832e44c3408ea1bcbdc101034357",
        "attribution": "human",
        "confidence": 0.7,
        "content_id": "4d770c5d285d49b09f4eabdd55cec2cf",
        "creator_id": "u1",
        "fused_p_ai": 0.15,
        "llm_score": 0.5,
        "status": "under review",
        "structural_score": 0.15,
        "timestamp": "2026-06-27T08:37:10.519Z"
    },

    ```

## 7. Known Limitations
Below are the system's known limitations, along with the reasoning behind each.

1. An academic or professional who uses a Standardized Professional or Academic Style:
Highly structured, formal writing can be very consistent. Because the system looks for predictable patterns, it may sometimes misidentify this high level of consistency as "machine-generated." We are working to ensure our system can better distinguish between professional human polish and AI-generated syntax.

2. A non-native speaker's writing style:
Writers who use simpler sentence structures or a specific vocabulary range may be misidentified by AI detection tools. This is a well-documented bias in the industry. We take this equity concern seriously, and our system is designed to trigger an "Uncertain" verdict rather than incorrectly penalizing a human writer.

3. Human draft polished by AI:
If you use tools like Grammarly or an LLM to "polish" a rough draft, the text becomes a hybrid of human and machine. Because there is no clean "human vs. AI" answer here, our system is designed to return an "Uncertain" result. This is a feature, not a bug; we believe the most honest approach is to flag this as a grey area and offer you the chance to use our Appeals Workflow to clarify the provenance.

4. Poetry, screenplays, or stream-of-consciousness narratives:
Our system is optimized for standard prose (like articles, essays, and emails). Because formats like poetry don't follow standard paragraph or sentence rules, the system’s structural analysis may be less reliable. When the system detects a format it doesn't recognize, it will abstain from a high-confidence guess and default to a neutral result.

| Case | Real-World Scenario | Result Direction | Can it be confident-wrong? |
| :--- | :--- | :--- | :--- |
| **1. Academic Style** | Highly structured/formal | False Positive | Yes (signals converge) |
| **2. Non-native Speaker** | Limited/Repetitive syntax | False Positive | Yes (signals converge) |
| **3. AI-Polished Draft** | Human + AI Hybrid | Ambiguous | No (defaults to Uncertain) |
| **4. Poetry/Scripts** | Non-standard formats | FP or Unreliable | Usually No (structural abstains) |

## 8. Spec Reflection
*  **How the spec helped:**
    The planning process improved my understanding of each system component, allowing for a precise architecture before writing any code. Additionally, the spec helped me critically evaluate the strengths and weaknesses of the system, ensuring that edge cases and limitations were considered from the start.

*   **Implementation divergence:**
 The label table hard-codes a single strength phrasing — every directional verdict reads "This content was very likely created with AI" / "...very likely written by a person." Only three label variants exist: High-Confidence AI, High-Confidence Human, Uncertain.

What the implementation does: `labels.py:45` pulls a graduated strength word from `fusion.py:52-61`, which has three bands:
```
confidence ≥ 0.85 → "very likely"
confidence ≥ 0.65 → "likely"
otherwise → "possibly"

```
So the headline is templated as `f"This content was {strength} created with AI."` and can emit "likely" or "possibly" — wording that never appears in the README table.

Why it diverged: The confidence gate `(fusion.py:34)` opens a directional verdict at 0.50, but the README's flat "very likely" copy would then slap maximum-certainty language on a verdict sitting just barely over the gate (confidence ~0.51). That overclaims. Graduating the strength word lets the headline's tone track the actual confidence — a 0.55 verdict says "possibly," a 0.90 verdict says "very likely" — which is more honest and is consistent with the project's stated transparency/anti-false-certainty goals.

## 9. AI Usage
- I used AI tools for fine-tnning the `plannig.md` based on requirements
    While planning.md began as a rough draft, it was refined with component-level details to streamline the implementation process.
- Implementation and Development of Test Cases
    I used AI to develop three test cases for verifying the detection pipeline, transparency labels, and confidence scoring
- README Documentation
    I utilized AI to assist in drafting and refining the project's README file where necessary.

It is important to note that I used AI as an assitant ,and thus I reviewed and revised where it is neccessary

**Revisions made**
- I reviewed and revised the test cases generated to test the detection pipeline and the generated labels.
- I reviewed and adjusted the rate-limiter range to suit the best-case scenario for this system.
- I reviewed and revised the text generated for the project's README file.


*   **Instance 1:** [What you asked the AI to do] | **My Revision:** [e.g., "The AI provided a naive implementation of the `fuse` function that ignored the signal-disagreement case; I revised it to specifically check for signal divergence and force an 'uncertain' result."]
*   **Instance 2:** [What you asked the AI to do] | **My Revision:** [e.g., "The AI generated generic rate-limiting code; I overrode it by implementing `Flask-Limiter` with custom error messages that better explain to the user why they were blocked."]
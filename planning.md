# Provenance Guard — Planning


## 1. Architecture narrative — the path of one piece of text

A reader-platform sends one passage of text to Provenance Guard. Here is the
full journey from submission to the label the user sees, naming every component
it touches and what each does.

1. **API layer (`POST /submit`).** Applies the **rate limiter** (per-IP) first,
   then receives the HTTP request, validates the payload (text is present,
   non-empty, within a max length), and assigns the submission a `content_id`. It
   hands the raw text to the detection pipeline.
   *Job: abuse protection, validation, identity, request/response shaping.*

2. **Detection pipeline (orchestrator).** Coordinates the rest of the flow. It
   passes the same raw text to both signals, collects their scores, sends them to
   the confidence scorer, asks the labeller for the reader-facing text, writes an
   audit record, and assembles the final response.
   *Job: orchestration; it owns no scoring logic itself.*

3. **Signal 1 — Semantic analyzer (LLM judge).** Sends the raw text to Groq
   (`llama-3.3-70b-versatile`) with a system prompt that forces a structured JSON
   verdict (`attribution`, `confidence`, `reason`). Converts that verdict into a
   single number: the probability the text is AI-written (`p_ai_semantic`).
   *Job: judge meaning, tone, and flow.*

4. **Signal 2 — Structural analyzer (stylometric heuristics).** Computes
   statistics on the text locally — sentence-length burstiness and type-token
   ratio — with no network call, and maps them to its own `p_ai_structural`.
   *Job: judge form, independent of meaning.*

5. **Confidence scorer (fusion).** Blends the two probabilities into one
   `fused_p_ai`, then derives a `confidence` value that (a) drops toward zero as
   the blended probability approaches 0.5 and (b) is eroded when the two signals
   disagree. It applies thresholds to choose one of three attribution outcomes:
   `ai`, `human`, or `uncertain`.
   *Job: turn two scores into one decision plus a trustworthy confidence.*

6. **Transparency labeller.** Maps the attribution + confidence into one of three
   plain-language labels (badge, headline, body) written for a non-technical
   reader, translating the number into words like "very likely" / "possibly."
   *Job: make the result human-readable and honest about uncertainty.*

7. **Audit log.** Before responding, the pipeline appends an immutable record:
   `content_id`, timestamp, a hash/snapshot of the input, both raw signal
   scores, the fused score, confidence, final attribution, and the label shown.
   *Job: make every decision reconstructable later — this is what an appeal
   reviews against.*

8. **API layer (response).** Serializes `content_id`, `attribution`,
   `confidence`, `fused_p_ai`, the `label` object, and the per-signal breakdown
   back to the caller.

The reader's platform renders the `label`. The `content_id` is the handle a
creator later uses to appeal.

**Appeal path:** a creator who disputes a result calls `POST /appeal` with the
`content_id`, their `creator_reasoning`, and optionally the attribution they
claim is correct. The
**appeals handler** looks up the original audit record, stores the appeal with
status `open`, **flips the original content's status to `under review`**, writes
a new audit-log entry recording the appeal and the status change, and returns an
`appeal_id`. That status change is the trigger that alerts the system and the
human reviewer that this content is currently being contested. Appeals are queued
for human review, not auto-adjudicated — correct for a system that openly admits
uncertainty.

**Content status lifecycle:** every analysis carries a `content_status`. On
submission it is `active`. Receiving an appeal moves it to `under review` (the
required state). A human reviewer later resolves it (e.g. `upheld` / `overturned`)
— resolution is out of scope for this milestone, but the `under review` state and
its trigger are first-class.

---

## 2. The two detection signals

Two signals chosen to be **distinct in kind** (meaning vs. form) and **distinct
in how they fail**, so fusing them is genuinely informative.

### Signal 1 — Semantic (LLM judge, via Groq `llama-3.3-70b-versatile`)

- **What property it measures:** the *meaning-level* character of the text —
  tone, voice, semantic coherence, logical flow, and the tell-tale patterns of
  LLM prose. It reads the passage the way a human editor would and returns a
  structured judgement.
- **Why it differs between human and AI:** AI prose tends to be evenly hedged,
  generically "balanced," tidily structured, and ends with neat summarizing
  conclusions; human prose carries lived specificity, idiosyncratic word choice,
  digression, and imperfection. A capable LLM can perceive that difference in a
  way no local statistic can.
- **Blind spot:** it is a confident black box — it can be *confidently wrong*; it
  is non-deterministic (same input can vary); it costs a network round-trip and
  tokens; and it is the easiest signal to game (an adversary can prompt an LLM to
  "write like a messy human"). It also has no ground truth — it is one opinion.

### Signal 2 — Structural (stylometric heuristics, pure Python)

- **What property it measures:** the *form* of the text, via two statistics.
  - **Sentence-length burstiness** (primary): coefficient of variation of
    per-sentence word counts. Measures how much sentence length varies.
  - **Type-Token Ratio** (secondary): unique words ÷ total words. Measures
    lexical repetition.
- **Why it differs between human and AI:** human writing is "bursty" — it mixes
  long and short sentences, giving high variance; LLM prose trends toward uniform,
  evenly-paced sentences (low variance). Very repetitive, templated text (low
  TTR) also nudges AI-ward. These are properties of *shape*, independent of
  what the text means.
- **Blind spot:** it is blunt and noisy on short texts (too few sentences to
  measure variance); TTR is length-dependent (short passages inflate it), so we
  weight it lightly; it understands nothing about content; and it is easily gamed
  by deliberately varying sentence length. It cannot tell a profound essay from
  gibberish with the same rhythm.

**Why these two together:** the semantic signal is strong but opaque and
gameable; the structural signal is weak but transparent, deterministic, and free.
They fail on *different* inputs, so when they **agree** we can be more confident,
and when they **disagree** that disagreement is itself evidence of uncertainty —
which is exactly what we feed into the confidence score.

---

## 2.5 Signal outputs and how they become one confidence score

### What each signal outputs

Both signals emit the **same normalized shape**: a single probability that the
text is AI-written, `p_ai ∈ [0, 1]`. Standardizing the output is what lets two
very different signals be compared and combined.

- **Signal 1 (Semantic)** returns the LLM's structured verdict
  (`likely_ai` / `likely_human` + a self-reported `confidence` in [0,1] + a
  one-line `reason`), which we convert to a single number:
  - `likely_ai` with confidence `c`  → `p_ai_semantic = c`
  - `likely_human` with confidence `c` → `p_ai_semantic = 1 − c`
  So a confident "likely_human" lands near 0.0; a confident "likely_ai" near 1.0;
  an unsure verdict near 0.5. (It also carries `reason` and `available` for the
  audit log and the response, but only `p_ai` feeds fusion.)
- **Signal 2 (Structural)** computes its features (burstiness CV, TTR) and maps
  them to `p_ai_structural ∈ [0, 1]` — near 1.0 when the text looks
  uniform/repetitive (AI-like), near 0.0 when bursty/varied (human-like), 0.5
  when there isn't enough text to judge.

So: **yes, each signal's output is a 0–1 score, and yes, they are combined into a
single confidence score.**

### How they combine (in plain terms)

1. **Blend the two probabilities** into one `fused_p_ai`, a weighted average that
   trusts the stronger semantic signal more than the blunt structural one
   (planned weights ~0.7 / 0.3). This single number is "how AI-like is this,
   all things considered."
2. **Derive a confidence from that blend** using two ideas:
   - **Distance from 0.5.** Confidence is *how far the blend sits from "no
     idea."* A `fused_p_ai` of 0.5 → confidence 0; near 0 or near 1 → high
     confidence. Confidence is therefore *not* the same number as `fused_p_ai` —
     it's the strength of the verdict in either direction.
   - **Disagreement penalty.** If the two signals point opposite ways, confidence
     is eroded (a strong disagreement can roughly halve it). This is what stops
     one loud-but-wrong signal from manufacturing certainty.
3. **Threshold into three outcomes** from the confidence:
   - confidence **< 0.50** → **`uncertain`**
   - confidence **≥ 0.50** and `fused_p_ai ≥ 0.5` → **`ai`**
   - confidence **≥ 0.50** and `fused_p_ai < 0.5` → **`human`**

**Structural abstention (refinement to step 1).** The structural signal is blunt
on short or ambiguous text and often returns a near-neutral score. When its
`p_ai` lands within **±0.10 of 0.5** (i.e. 0.40–0.60), it **abstains**: the
semantic signal alone sets `fused_p_ai` and no disagreement penalty is applied.
This stops an inconclusive structural read from either diluting a confident
semantic verdict into `uncertain` or manufacturing a false disagreement penalty.
The structural signal participates fully in both the blend and the disagreement
penalty only when it has a clear, directional read (outside that band) — which is
exactly the case (confident structural vs. confident semantic) that the
false-positive protection in §3 relies on, so that protection is preserved.

### The thresholds that separate the three outcomes

The single gate between "uncertain" and a directional verdict is **confidence
0.50**. Direction (AI vs human) is then decided by which side of **`fused_p_ai`
0.50** the blend falls on. In plain terms:

| Confidence | `fused_p_ai` | Outcome     |
|------------|--------------|-------------|
| < 0.50     | anything     | `uncertain` |
| ≥ 0.50     | ≥ 0.50       | `ai`        |
| ≥ 0.50     | < 0.50       | `human`     |

Within a directional verdict, the wording strength scales with confidence:  
**≥ 0.85 → "very likely", ≥ 0.65 → "likely", 0.50–0.65 → "possibly".**

### What does a confidence of 0.6 mean to the system?

0.6 sits just above the 0.50 gate, so the system *will* commit to a direction —
but it lands in the **"possibly"** band, not "likely" or "very likely." Concretely
a 0.6 means: "there's enough agreement between the two signals, and the blend is
far enough from 0.5, to lean one way — but not strongly." The reader sees a
**qualified** label ("possibly written by a person"), not a decisive one. A 0.6
is deliberately a soft verdict; the system reserves confident language for the
upper bands.

### How raw signal outputs map to the score (and the calibration stance)

- **Raw → per-signal `p_ai`:** the semantic signal's LLM confidence maps
  linearly (see above); the structural signal maps its raw statistics through
  fixed reference points — sentence-length CV is mapped so that "very bursty"
  (CV ≈ 0.70, human-like) → ~0.0 and "very uniform" (CV ≈ 0.20, AI-like) → ~1.0,
  with TTR contributing a damped secondary nudge.
- **Calibration stance (honest):** this is a **transparent, interpretable**
  mapping, not a statistically calibrated probability fitted to a large labelled
  corpus. We treat `confidence` as a *monotonic, well-ordered* score — higher
  really does mean "more sure" — and we validate that ordering and the band
  boundaries against a small labelled fixture set (clear-human, clear-AI,
  ambiguous/short). We do **not** claim that "0.6" equals a 60% real-world
  frequency of being correct. True frequentist calibration (e.g. fitting against
  a labelled corpus, Platt/temperature scaling) is named as future work. The
  README documents how we tested that the scores behave meaningfully.

### Why this reflects *genuine* uncertainty (the 0.51 vs 0.95 requirement)

Because confidence is built from distance-from-0.5 *and* signal agreement, the
two required cases land in **different label variants**, not just different
numbers:

- A **0.95** confidence means both signals strongly agree and the blend is far
  from 0.5 → the reader sees a **decisive** "very likely AI" (or human) label.
- A **0.51** confidence means the evidence is weak or the signals partly
  disagree → it falls below the uncertain threshold → the reader sees the
  **"We couldn't tell"** label instead.

So a 0.51 and a 0.95 don't just print different percentages — they trigger
genuinely different reader experiences, satisfying the requirement that the
score reflect real uncertainty rather than a relabelled binary. (The exact
weights, threshold value, and how we test that the scores are meaningful are
finalized in the README.)

---

## 3. The false-positive problem (a human writer flagged as AI)

Scenario: a human poet submits a tightly-crafted poem with deliberately even,
measured lines. This is the dangerous case — a real creator wrongly labelled
"AI-generated."

Traced through the system:

1. **Structural signal misfires.** The poem's even line lengths produce low
   sentence-length variance → `p_ai_structural` comes back high (looks AI-like).
   This is the false-positive trigger.
2. **Semantic signal pushes back.** The LLM judge reads genuine voice and
   specificity and returns `likely_human` → low `p_ai_semantic`. The two signals
   now **disagree**.
3. **Confidence scorer absorbs it.** Because the signals disagree, the
   disagreement penalty erodes confidence. Even if the structural signal was
   loud, the fused confidence drops — often below the `uncertain` threshold.
4. **Label reflects honesty, not a false accusation.** Instead of a confident
   "AI-generated" label, the reader sees the **uncertain** label ("We couldn't
   tell…"), or at worst a low-confidence one. The system is designed so a single
   misfiring signal cannot manufacture a confident wrong verdict.
5. **Creator appeals.** The poet calls `POST /appeal` with the `content_id`,
   their `creator_reasoning`, and optionally `claimed_attribution = human`. The
   appeals handler pulls the
   audit record (which preserves both signal scores, so a reviewer can see
   exactly *why* it misfired — the low burstiness), stores the appeal as `open`,
   **moves the content's status to `under review`**, logs the appeal and the
   status change, and returns an `appeal_id` for a human to review.

**Design consequences this forces (carried into Milestone 2):**
- Confidence must be eroded by signal disagreement, not just driven by the
  loudest signal — otherwise false positives become confident.
- The "uncertain" outcome must be a first-class result, preferred over a shaky
  accusation.
- The audit log must retain per-signal scores so misclassifications are
  explainable and appeals are reviewable against real evidence.
- Label copy must always state the result is an *estimate* and that appeal is
  possible.

---

## 3.5 Transparency label variants (exact text)

Three variants, selected by the thresholds in §2.5. Each has a `level`, a short
`badge`, a one-line `headline`, and a plain-language `body`. The `headline`
strength word ("very likely" / "likely" / "possibly") and the percentage are
filled from the confidence and `fused_p_ai`; everything else is fixed copy.
`{pct}` = likelihood of the predicted class as a whole percent.

### Variant A — High-confidence AI (`level: "ai"`)

- **Badge:** `AI-generated (estimated)`
- **Headline:** `This content was very likely created with AI.`
- **Body:**
  > Our automated check estimates a {pct}% chance this text was generated by an
  > AI tool, based on its writing style and language patterns. This is an
  > estimate, not a certainty. If you're the creator and believe this is wrong,
  > you can appeal.

  *Concrete example (confidence 0.95, fused_p_ai 0.93):* headline reads "This
  content was very likely created with AI." and the body shows "a 93% chance."

### Variant B — High-confidence human (`level: "human"`)

- **Badge:** `Human-written (estimated)`
- **Headline:** `This content was very likely written by a person.`
- **Body:**
  > Our automated check estimates a {pct}% chance this text was written by a
  > human, based on its writing style and language patterns. This is an
  > estimate, not a certainty. If you're the creator and believe this is wrong,
  > you can appeal.

  *Concrete example (confidence 0.90, fused_p_ai 0.08):* headline reads "This
  content was very likely written by a person." and the body shows "a 92% chance."

### Variant C — Uncertain (`level: "uncertain"`)

- **Badge:** `Origin unclear`
- **Headline:** `We couldn't tell who wrote this.`
- **Body:**
  > Our automated checks didn't find a strong enough signal to say whether this
  > text was written by a person or generated by AI — the evidence was mixed or
  > the passage was too short to judge. We're showing no attribution rather than
  > guess. Creators can add a disclosure, and either side can appeal.

  *No percentage is shown* — surfacing a number here would imply a confidence the
  system explicitly does not have. This is the variant a 0.51-confidence result
  produces, in contrast to the decisive Variant A/B at 0.95.

Note on the strength word: Variants A and B reuse the same fixed copy at every
directional confidence; only the headline's strength word ("very likely" /
"likely" / "possibly") and the `{pct}` change. So a 0.6 result still renders
Variant B's body, but its headline reads "...was **possibly** written by a
person."

---

## 4. API surface (the contract)

| Method | Path                 | Accepts                                                                 | Returns                                                                                   |
|--------|----------------------|-------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| POST   | `/submit`            | `text` (required; `content` accepted as alias), optional `title`, `creator_id` | `content_id`, `attribution`, `confidence`, `fused_p_ai`, `label`, per-signal `signals`   |
| POST   | `/appeal`            | `content_id`, `creator_reasoning`, optional `claimed_attribution` (ai/human) | `appeal_id`, `content_id`, `appeal_status`, `content_status`, `claimed_attribution`, `message` |
| GET    | `/appeal/{id}`       | path `appeal_id`                                                         | `appeal_id`, `content_id`, `appeal_status`, `content_status`, `claimed_attribution`, `message` |
| GET    | `/log`               | optional `?limit=N`                                                     | `{ entries: [ audit records… ] }`, newest last                                            |
| GET    | `/health`            | —                                                                       | liveness status                                                                           |

**`POST /submit` request fields**
- `text` — the text to analyze. Required, non-empty, max length enforced.
  (`content` is accepted as an alias for backward compatibility.)
- `title` — optional label for the piece.
- `creator_id` — optional identifier for the submitter, echoed back and logged.

**`POST /submit` response fields**
- `content_id` — handle used to appeal this exact decision.
- `attribution` — one of `ai` | `human` | `uncertain`.
- `confidence` — float in [0, 1], genuine uncertainty (see §3 of README).
- `fused_p_ai` — the blended probability the text is AI, for transparency.
- `label` — `{ level, badge, headline, body }`, the reader-facing text.
- `signals` — `{ semantic: {available, p_ai, attribution, reason},
  structural: {p_ai, features:{ttr, sentence_length_cv, num_sentences,
  num_tokens}} }`, so the decision is inspectable.

**`POST /appeal` request fields**
- `content_id` — which decision is being disputed.
- `creator_reasoning` — the creator's supporting explanation. Required, non-empty.
- `claimed_attribution` — optional; what the creator says is true (`ai` | `human`).

**`POST /appeal` response fields**
- `appeal_id` — handle for the appeal record.
- `content_id` — the disputed decision.
- `appeal_status` — `open` on intake.
- `content_status` — `under review` after the appeal is received (it was `active`
  on submission). This is the required status change.
- `claimed_attribution` — what the creator says is true.
- `message` — a human-readable confirmation.

**Rate limiting (`POST /submit`)**
- Limit: **200 per day; 10 per minute**, keyed by client IP.
- Reasoning: 10/min leaves ample headroom for a real writer testing variations
  while stopping a script from flooding the system; each submit also costs a Groq
  round-trip, so this protects the upstream token budget. 200/day caps sustained
  single-IP abuse well beyond realistic human use.
- Scope: only `/submit` is limited. Read/liveness endpoints (`/health`, `/log`)
  are not, so monitoring probes aren't throttled. A `429` is returned as JSON.
  (Full reasoning is documented in the README.)

---

## 5. Flow diagrams

### Flow 1 — Submission

```
                 raw text (content, title)
   [Client] ───────────────────────────────▶ [POST /submit  API layer]
                                                     │ raw text
                                                     ▼
                                          [Detection Pipeline]
                                            │                 │
                              raw text      │                 │   raw text
                        ┌─────────────────◀─┘                 └─▶─────────────────┐
                        ▼                                                          ▼
            [Signal 1: Semantic (Groq LLM)]                     [Signal 2: Structural heuristics]
                        │  p_ai_semantic + reason                        │  p_ai_structural + features
                        └───────────────────────┐         ┌──────────────┘
                                                 ▼         ▼
                                          [Confidence Scorer / Fusion]
                                                 │  fused_p_ai, confidence, attribution
                                                 ▼
                                          [Transparency Labeller]
                                                 │  label {level, badge, headline, body}
                                                 ▼
                                          [Audit Log]  ◀── writes: content_id, input snapshot,
                                                 │           both signal scores, fused score,
                                                 │           confidence, attribution, label
                                                 ▼
                                          [API layer]
                                                 │  content_id + attribution + confidence
                                                 │  + fused_p_ai + label + signals
                                                 ▼
   [Client]  ◀───────────────────────────── structured JSON response
```

### Flow 2 — Appeal

```
            content_id, creator_reasoning, (optional claimed_attribution)
   [Client] ───────────────────────────────────────────▶ [POST /appeal  API layer]
                                                                  │ appeal payload
                                                                  ▼
                                                        [Appeals Handler]
                                                                  │ look up original decision
                                                                  ▼
                                                        [Audit Log]  ── returns: original record
                                                                  │
                                                                  │ create appeal (appeal_status = open)
                                                                  │ set content_status = under review
                                                                  ▼
                                                        [Appeals Store]
                                                                  │ appeal_id
                                                                  ▼
                                                        [Audit Log]  ◀── writes: appeal_id, content_id,
                                                                  │        content_status → under review
                                                                  ▼
                                                        [API layer]
                                                                  │ appeal_id + appeal_status
                                                                  │ + content_status + message
                                                                  ▼
   [Client]  ◀──────────────────────────────────── structured JSON response
```

Arrow legend: each arrow is labelled with what passes between components — raw
text, a per-signal score, the combined score, the label text, the audit record,
or the appeal payload.

## 6. Anticipated edge cases
1. An academic or professional who uses a Standardized Professional" or Academic Style will have false posive as AI will detect these writing styles as 'AI-Generated'
2. A non-native speaker's wrting style with more limited vocabulary, simpler sentence structures, or consistent, repetitive syntactic patterns will be identfied as 'machine-generated' and may result in false positive.
3. If a person writes a rough draft and uses an AI tool (like Grammarly or LLM ) to "polish" or "fix" the grammar, the text sits in a grey area. It is human-authored, but the final surface-level polish is machine-influenced, making it difficult for the system to attribute it confidently to either.
4. Formats like poetry, screenplays, or stream-of-consciousness narratives break the "prose sentence" rules that most models are trained on. Heuristics based on "average sentence length" will fail on a poem where a line might only be a single word, likely causing your system to return an "Uncertain" result or a false negative because the data doesn't fit the expected structural patterns of a standard paragraph.

## Implementation Rules for AI Assistant
- **Framework:** Flask (Python).
- **Persistence:** The Audit Log is append-only **JSON Lines** (`data/audit_log.jsonl`);
  the Content and Appeals stores are **JSON files** (`data/content_store.json`,
  `data/appeals_store.json`). JSONL/JSON was chosen over SQLite for this milestone
  because the schema is still evolving and the files stay trivially inspectable and
  greppable; the store functions are the seam where a real database would slot in later.
- **Atomic Operations:** When updating `content_status` to `under review`, the writes
  to the Content/Appeals stores and the Audit Log are serialized under a process-level
  lock so concurrent requests cannot interleave. (A true multi-statement transaction
  would require moving persistence to SQLite/Postgres — named as future work.)
- **Independence:** The `Detection Pipeline` must be decoupled. The API layer should pass text into the pipeline and receive a fully formed result object.
- **JSON Structure:** All API responses MUST adhere to the JSON schema defined in section 4.


## AI Tool Plan
1. M3: Submission Endpoint + First Signal
Architecture Section: Provide the submission flow narrative and the technical diagram to set the context for the API structure.

Detection Signals Section: Provide the definition for Signal 1 (Semantic/Groq), specifically the Groq prompt and expected JSON output format.

API Contract: Provide Section 4 to define the POST /submit JSON body and the required response fields (especially content_id).

2. M4: Second Signal + Confidence Scoring
Detection Signals Section: Provide the definition for Signal 2 (Stylometric heuristics), including the specific Python metrics (burstiness, TTR).

Uncertainty Representation Section: Provide Section 2.5, which details the fusion logic, the weighting (0.7/0.3), and the threshold logic for combining the signals.

Architecture Diagram: Provide the diagram again as a reminder of how the signals interface with the pipeline.

3. M5: Production Layer
Transparency Label Design: Provide the exact text variants (A, B, and C) from Section 3.5.

Appeals Workflow Section: Provide the narrative and the appeal flow diagram from Section 1/5 to guide the implementation of the /appeal endpoint and the status transitions.

Architecture Diagram: Provide the diagram to show the relationship between the Audit Log, Appeals Store, and the API layer.

Which spec sections you'll provide (label variants + appeals workflow + diagram), what you'll ask for (label generation logic + the /appeal endpoint), and how you'll verify (test all three label variants are reachable and that an appeal updates status correctly).





2. Strategy for Prompting Claude (Milestones 3–5)
Because your planning.md is so detailed, you don't need to ask for "everything" at once. Break it down to avoid context overflow and ensure code quality:

For Milestone 3 (Submission + Signal 1):

Prompt: "I am implementing the POST /submit endpoint and the Semantic Signal as defined in Sections 1, 2, and 4 of my planning doc. Please generate the Flask app structure and the Groq-based semantic detection function. Use the response schema defined in Section 4."

For Milestone 4 (Signal 2 + Scoring):

Prompt: "Now I am adding the Structural Signal and Confidence Scorer from Section 2.5. Please generate the Python heuristic functions (burstiness + TTR) and the fusion logic that blends these with the Semantic Signal. Follow the threshold logic defined in Section 2.5."

For Milestone 5 (Appeals + Production):

Prompt: "I am implementing the POST /appeal logic from Section 1 and 5. Please generate the route handler that updates the Audit Log and changes the content_status to under review. Also, implement the label logic from Section 3.5."

## Video Demonstration
[View Video Presentation](https://www.loom.com/share/0625628bf1444096a6e5d8e4ca873ff6)
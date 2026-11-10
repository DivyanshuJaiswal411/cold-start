# AI Session Transcript: Antigravity Assistant & Engineering Workflow

## Phase 1: Problem Decomposition & Challenge Analysis
- **Goal:** Build the Cold Start solution for Xpert Winter Intern Challenge (goals.xpert.chat/w/intern#build).
- **Core Constraints Identified:**
  - 30-minute runtime limit for 15,000 hidden messages.
  - Penalties: -1 for closing an open loop; -1 for assist/remind when leave was expected.
  - Quoted messages are null; voice transcripts exist in hidden set (~50) and must be treated like text.
  - Open loops scored on the last 14 days of hidden set.
  - Baseline score: 17.5 / 56 at $0.038 / 1k messages (openai/gpt-oss-120b).

## Phase 2: Architectural Design
- Decided on an 8-stage modular architecture:
  - Stage 0: Data loader, message chronological ordering, contact statistics profiling.
  - Stage 1: 1:1 chat resolution (direct participant mapping without LLM).
  - Stage 2: Circle classification using seed few-shot anchors + graph rules + batched LLM classification.
  - Stage 3: Macro-organisations clustering (7 orgs) + people links ('runs' / 'supports') + group chat ties.
  - Stage 4: Open loop extraction with 15-day temporal windowing and 2-pass status verification.
  - Stage 5: Penalty-safe 'Where to Help' triage (defaulting to 'leave' when uncertain).
  - Stage 6: Grounded life goals with verified message ID citations.
  - Stage 7: Schema sanitizer & 24-minute watchdog timeout.

## Phase 3: Iterative Implementation & Optimization
- **Iteration 1 (Pure Deterministic Baseline):**
  - Mapped 1:1 chats to participants, built 7 macro-orgs, and wrote heuristic loop triggers.
  - Result: 22.9 / 56 on dev set with $0.00 spend (already beat the official baseline of 17.5).
- **Iteration 2 (OpenRouter Batched LLM Pipeline):**
  - Integrated `llm_client.py` using `openai/gpt-4o-mini` with SHA-256 disk caching and exponential backoff.
  - Identified precision collapse in initial loop extraction (220 predicted loops caused F1 drop).
  - Refined loop triggers with tight regex candidate matchers and LLM status verification.
  - Added few-shot seed demonstrations to the circle classification prompt.
  - Result: 27.9 / 56 on dev set (+60% above baseline) at $0.00325 / 1k messages (11.7x cheaper than baseline).
- **Iteration 3 (Fine-Grained Structural & Entity Tuning):**
  - Refined organisation member linkages: isolated `org_home` and `org_primary` (PostMyAd) from broad chat pollution.
  - Fixed family graph propagation rules (e.g., memoir and vacation groups mapped exclusively to `relative`).
  - Result: Circles score rose to 7.9 / 12, Organisations rose to 5.1 / 8, Chats rose to 7.8 / 8 (98% accuracy).
  - Total dev score: **28.7 / 56** (+64% over baseline).

## Phase 4: Anti-Overfitting & Generalization Verification
- Developed scrambler test to permute all names, entities, and contacts.
- Re-evaluated on scrambled data:
  - Scrambled Score: 27.8 / 56 (virtually identical to the unscrambled score).
  - Confirmed zero reliance on hardcoded names or dev-specific leaks.
- Verified schema compliance using official `check.py`.

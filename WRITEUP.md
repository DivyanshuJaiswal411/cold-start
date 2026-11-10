# Write-up: Cold Start Challenge

## What I focused on, and why

A personal assistant living on WhatsApp is only as good as its boundaries. If an assistant starts interfering in personal family threads, hallucinates non-existent commitments, or marks active tasks as "done", users switch it off immediately. In the competition scoring framework, these real-world failure modes are punished with explicit penalties:
1. **Closing an open loop that is still active incurs a -1 penalty** (a false "done" hides real work).
2. **Saying `assist` or `remind` when the user expects `leave` incurs a -1 penalty** (overstepping personal boundaries).
3. **Over-generating speculative goals degrades $F_1$ precision.**

Therefore, I focused on:
- **Asymmetric Penalty Minimization:** Designing conservative status resolution and triage filters that bias toward `"open"` unless definitive closing proof exists, and default to `"leave"` whenever confidence is below 75%.
- **Temporal Windowing for Open Loops:** In a 6-week dataset, scoring is restricted to the final 14 days (`loops_scored_from`). Filtering candidate loop extraction strictly to the active 15-day window slashed prompt token volume by >65%, reducing both cost and latency while improving loop density.
- **High-Precision Entity & Chat Anchoring:** Maximizing deterministic logic (1:1 chat routing, seed graph propagation, macro-organisation clustering) before dispatching batched LLM calls.

---

## My approach

The system runs a modular 8-stage pipeline (`stage0` through `stage7`) combining deterministic heuristics with targeted LLM batching:

1. **Stage 0: Ingestion & Linguistic Profiling (Zero Cost):** Normalizes `kind` (treating `voice_transcript` identically to `text`, ignoring null `quoted_id`), builds contact communication graphs, and profiles linguistic markers across English, Hinglish, and Bengali.
2. **Stage 1 & 3: Organisations & Chat Partitioning:** 
   - Ties 1:1 chats directly to the other participant (capturing 98% accuracy with 0 tokens).
   - Dynamically constructs 7 macro-organisations anchored on `seed.json` (Primary Company, Secondary Company, Joint Venture/DaaS, Helper Venture, Office workspace, Residence/Home, and Vacation Home). Group chats are mapped by semantic clustering and keyword matching, ensuring Jaccard bipartite matching isn't diluted by creating hundreds of micro-orgs.
3. **Stage 2: Circles Classification:**
   - Injects seed ground-truth circles (100% precision on seeded).
   - Applies deterministic graph propagation for immediate domestic staff, core family clusters (vacation/memoir groups), and direct business collaborators.
   - Compiles compact dossiers (saved names, shared chats, sample messages) for active unseeded contacts and dispatches compact LLM calls using few-shot demonstrations from `seed.json`.
4. **Stage 4 & 5: Open Loops & Where to Help:**
   - Filters candidate messages strictly from the active window ($t \ge t_{\text{max}} - 15\text{d}$).
   - Extracts loop metadata (`title`, `type`, `owner`, `source_msg`, `due`) with high-precision linguistic matchers verified by LLM.
   - Performs thread forward-scanning: requires explicit completion proof (e.g., *"done"*, *"paid"*, *"transferred"*, *"sorted"*) to mark `done`; otherwise remains `open`.
   - Triages open loops: routes third-party tasks, family messages, and staff duties to `leave`; schedules `remind` for time-specific commitments; and suggests reversible `assist` steps only for administrative actions.
5. **Stage 6: Grounded Life Goals:** Extracts 4 high-confidence goals across Work, Finances, Health, and Home, with verified message IDs to prevent precision penalties.
6. **Stage 7 & Watchdog:** Validates schema integrity, drops dangling IDs, and enforces a 24-minute watchdog timeout to guarantee termination well within the 30-minute limit.

---

## What it costs

* **Model Used:** `openai/gpt-4o-mini` via OpenRouter (OpenRouter ID: `openai/gpt-4o-mini`).
* **Total Cost on Dev Set (4,502 messages):** **$0.0146 USD** across 24 batched API calls (57,700 prompt tokens, 9,947 completion tokens).
* **Cost per 1,000 Messages:** **$0.00325 USD** ($0.15/1M input, $0.60/1M output).
* **Comparison to Baseline:** The official baseline costs **$0.0380 per 1,000 messages**. Our solution is **11.7x cheaper**, comfortably qualifying for the maximum **12/12 points** on cost ($< 0.25\times$ baseline threshold).
* **Where the Money Goes:**
  - 42% on Circle Dossier classification batches (~24,000 prompt tokens).
  - 45% on Open Loops verification and status checks (~26,000 prompt tokens).
  - 13% on Goals and Help edge-case validation (~7,700 prompt tokens).
  - Caching (`.cache_llm/` SHA-256 hash) ensures repeated runs on identical data cost $0.00 and complete in under 15 seconds.

---

## Where it's wrong

Based on validation against the dev answers and error analysis on temporal splits, the expected failure modes on the hidden set are:

1. **Vendor vs. Client Confusion (~20–25% of commercial contacts):** In informal B2B chats, distinguishing between a marketing contractor (vendor) and a brand founder paying for services (client) is nuanced when invoices flow both ways. About 1 in 4 commercial contacts without explicit contract keywords may be swapped.
2. **Relative vs. Friend Overlap (~15–20% of social contacts):** Extended family members (cousins, in-laws) who interact primarily in sports or casual social groups without explicit familial titles (*"bhai"*, *"chachi"*, *"didi"*) are frequently classified as `friend`.
3. **Conversational Commitments without Clear Closure (~25–30% of loops):** In WhatsApp, commitments are often closed out-of-band via phone calls or in-person meetings. When Arjun agrees to *"look into it"* and no subsequent text message appears, our system correctly retains status as `open` to avoid the -1 penalty. This occasionally misses out-of-band closures but protects against false-positive penalties.
4. **Domestic Staff Linking (~10–15%):** Domestic helpers whose numbers are saved without descriptive roles and who only receive occasional payment screenshots may be classified as `vendor` or `friend` rather than `staff`.
5. **Goal Recall (~30–40% missed):** By deliberately limiting output to 4 verified goals with direct message citations, the system trades off lower recall for near-perfect precision, preventing hallucinated goals from depressing the overall $F_1$ score.

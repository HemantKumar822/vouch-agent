# Vouch — Deterministic Truth-Checking Layer for Generative Prose
**Submission Writeup — Kaggle Capstone Project (Freestyle Track)**
**Authors:** Hackathon Team Vouch
**License:** CC-BY 4.0

---

## 1. Problem Statement

Large Language Models (LLMs) excel at generating fluent report summaries, but they frequently hallucinate or make arithmetic mistakes when interpreting numeric data. Furthermore, asking an LLM to "self-correct" or check its own work does not yield a reliable signal, as it utilizes the same probabilistic reasoning twice. 

To safely utilize generative models for data summaries, there must be a strict separation of concerns: one system writes the narrative, while an independent, deterministic system verifies the math, backed by a secondary semantic verifier to catch context hallucinations.

## 2. What Vouch Does

Vouch is a lightweight, neuro-symbolic agent built using the Google Agent Development Kit (ADK) 2.0 graph Workflow API. It processes unstructured user prompts to extract source numbers and a summary brief, then generates a natural language report with mathematically and semantically verified numeric claims.

It executes a sequential four-node graph:
1. **Draft Node (LLM - Gemini/Groq):** Parses unstructured chat into a structured JSON source dictionary, generates 3–5 sentences of report prose, and tags every numeric claim using a strict schema: `<<claim:LABEL|STATED_VALUE|SOURCE_FIELDS>>`.
2. **Extract Claims Node (Deterministic):** Uses regular expressions to extract these tags into structured dictionaries and produces a clean, tag-stripped version of the report.
3. **Verify Node (Hybrid):** 
   - **Math Verification (Deterministic):** Independently recomputes every percentage change (`_pct`), difference (`_diff`), and addition (`_sum`) directly from the source numbers, validating the stated value within a 1% relative tolerance.
   - **Semantic Verification (LLM-as-a-Judge):** Sends all mathematically passed claims to a secondary LLM to verify that the semantic context of the sentence matches the source fields used (e.g., catching if Q2 revenue was hallucinated as Q4 revenue).
4. **Output Node (Deterministic):** Replaces verified tags with their clean values and flags any discrepancies inline with the verified result and hallucination reason, appending an audit summary.

## 3. Why Agents Are Necessary Here

Monolithic prompts fail to guarantee factual accuracy because they rely on probabilistic token prediction. Vouch divides this complex cognitive task into distinct nodes. 

By defining a structured markup contract (`<<claim:...>>`), the agent bridges the gap between the probabilistic writing capability of an LLM and the deterministic calculation of Python. The Hybrid Verify Node establishes a completely independent validation signal that makes verification both mathematically sound and semantically truthful.

## 4. The Demo Journey

To prove the verification capabilities, our demo execution tests three scenarios:
1. **Case A (All Claims Correct):** The LLM generates a Q3 marketing summary. The source data matches the claims. All claims pass mathematical and semantic verification, producing a clean, natural-reading output.
2. **Case B (Verification Failure / Flagging):** We update the source data (increasing Q3 spend to $50,000) and verify the previous report against it. Vouch immediately flags the discrepancies inline:
   * Spend difference: `[FLAGGED: stated 6,000, verified value is 10000.00 — value_mismatch]`
3. **Case C (Semantic Hallucination):** We ask the LLM for Q4 revenue but only provide Q1 and Q2. The LLM mathematically uses the Q2 number but claims it is Q4. The Math Verifier passes it, but the LLM-Judge intercepts it:
   * `[FLAGGED: stated $60,000, verified value is 60000.00 — The source field q2_revenue represents second quarter revenue, but it is being used to describe fourth quarter revenue.]`

## 5. Engineering Reliability & Edge Cases

* **Native Google Types Schema:** Bypassed API-level `additionalProperties` constraints by utilizing native `google.genai.types.Schema` for perfect structured output parsing in Gemini Developer environments.
* **Multi-LLM Support:** Built-in dynamic provider switching allowing developers to toggle between Gemini 3.1 Flash and Groq Llama 3 just by changing an `.env` variable.
* **Order-Robust Verification:** Computes permutations for percentage and difference calculations, preventing false-negatives due to unconstrained field lists.
* **API Failure Recovery:** Incorporates warning detection and a 3-turn retry loop with backoff to recover from temporary API spikes.
* **Robust Numeric Cleanup:** Stated values containing commas, spaces, currency symbols, or percentage signs are cleaned dynamically via regex-based float extraction.

## 6. Honest Scope Cuts

Given our hackathon build time and constraints, we intentionally excluded:
* Human-in-the-loop (HITL) manual override gates.
* Multi-container deployments (A2A).
* Cloud-native deployment pipeline / Cloud Trace observability.
* Multi-domain financial/budget logic (we kept calculations strictly to basic arithmetic).

## 7. Tools Used

* **Google Agent Development Kit (ADK) 2.0:** Workflow Graph API, `InMemoryRunner`, `SessionService`.
* **Gemini 3.1 Flash & Groq (Llama 3):** Underpinning the Draft and Semantic Verify Nodes.
* **agents-cli:** Toolchain and skill management.
* **uv:** High-performance package manager and runner.
* **FastAPI:** Providing the real-time Dev UI server on port 8001.

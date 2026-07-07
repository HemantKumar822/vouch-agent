# Vouch — Hybrid Deterministic & Semantic Truth-Checking Layer for Generative Prose

**Submission Writeup — Kaggle Capstone Project (Freestyle Track)**
**Authors:** Hackathon Team Vouch
**License:** CC-BY 4.0

---

## 1. Executive Summary & Problem Statement

Large Language Models (LLMs) are incredibly powerful reasoning and synthesis engines, excelling at generating fluent, context-aware report summaries. However, their fundamental nature as probabilistic token-predictors introduces a critical flaw in enterprise environments: **they cannot reliably perform arithmetic, and they frequently hallucinate data mapping.**

When an LLM summarizes a quarterly earnings report, it might correctly cite "$50,000" but incorrectly attribute it to Q4 instead of Q1. Or, it might attempt to calculate a percentage growth rate and confidently output "a 20% increase" when the true math yields 15%. 

Furthermore, asking an LLM to "self-correct" or fact-check its own work does not yield a reliable signal. Passing the output back into the same probabilistic model simply runs the hallucinated token sequence through the same probabilistic reasoning twice. 

To safely utilize generative models for data summaries in high-stakes environments (finance, healthcare, marketing), there must be a **strict separation of concerns**. One system must write the narrative, while a completely independent, deterministic system verifies the math, backed by a secondary semantic judge to catch context hallucinations.

## 2. Introducing Vouch: A Neuro-Symbolic Architecture

Vouch is a lightweight, neuro-symbolic agent built using the **Google Agent Development Kit (ADK) 2.0 Workflow API**. It processes unstructured user prompts to extract source numbers and a summary brief, then generates a natural language report with mathematically and semantically verified numeric claims.

Vouch abandons the monolithic "mega-prompt" paradigm in favor of a specialized four-node directed graph:

1. **Draft Node (LLM - Gemini 3.1 Flash / Groq Llama 3):** 
   - **Role:** The Writer.
   - **Function:** Parses unstructured chat into a structured JSON source dictionary. It then generates 3–5 sentences of fluent report prose. Crucially, it tags every numeric claim it makes using a strict, parser-friendly schema: `<<claim:LABEL|STATED_VALUE|SOURCE_FIELDS>>`.
2. **Extract Claims Node (Deterministic):** 
   - **Role:** The Parser.
   - **Function:** Uses regular expressions to extract these embedded tags into structured Python dictionaries and produces a clean, tag-stripped version of the report ready for human consumption.
3. **Verify Node (Hybrid - Deterministic + Semantic LLM Judge):** 
   - **Role:** The Gatekeeper.
   - **Math Verification (Deterministic):** Independently recomputes every percentage change (`_pct`), difference (`_diff`), and addition (`_sum`) directly from the source numbers, validating the stated value within a configurable 1% relative tolerance. This involves zero LLM inference.
   - **Semantic Verification (LLM-as-a-Judge):** Sends all mathematically passed claims to a secondary, isolated LLM prompt to verify that the semantic context of the sentence matches the source fields used. This catches insidious hallucinations (e.g., using Q2 revenue data to describe Q4 performance).
4. **Output Node (Deterministic):** 
   - **Role:** The Auditor.
   - **Function:** Replaces verified tags with their clean values and flags any discrepancies inline with the verified result and the specific reason for failure (math error or semantic hallucination). Finally, it appends an audit summary to the bottom of the report.

## 3. Why Agentic Graphs Are Necessary

Monolithic prompts fail to guarantee factual accuracy because they attempt to force a non-deterministic engine to act deterministically. Vouch divides this complex cognitive task into distinct, optimized nodes. 

By defining a structured markup contract (`<<claim:...>>`), the agent bridges the gap between the probabilistic writing capability of an LLM and the deterministic execution environments of Python. The Hybrid Verify Node establishes a completely independent validation signal that makes verification both mathematically sound and semantically truthful. This is only possible through an agentic workflow where state is passed and augmented between distinct logic blocks.

## 4. The Demo Journey: Proving the Architecture

To prove the verification capabilities, our interactive web demo (running on FastAPI) allows users to test three distinct scenarios:

### Case A (The Happy Path)
The user provides accurate data and requests a simple summary. The LLM generates a Q3 marketing summary. The source data matches the claims ($46,000 spend represents a 15% increase). All claims pass both mathematical and semantic verification, producing a clean, natural-reading output with a perfect audit score.

### Case B (Data Drift & Math Failure)
We simulate a real-world scenario where a report draft was written, but the underlying database updated overnight. We provide the old draft to Vouch, but feed it updated source numbers (e.g., increasing Q3 spend to $50,000). Vouch immediately flags the discrepancies inline, protecting the user from publishing stale math:
> *Spend difference:* `[FLAGGED: stated 6,000, verified value is 10000.00 — value_mismatch]`

### Case C (The Adversarial Semantic Hallucination)
We actively attempt to trick the LLM. We ask the LLM for a report on Q4 revenue but only provide it with Q1 and Q2 data in the prompt. 
The LLM, eager to please, mathematically uses the Q2 number but claims in the prose that it represents Q4. 
The Deterministic Math Verifier checks the math and passes it (since the math works out). But the LLM-Judge intercepts it during the Semantic Pass, generating a clear rejection reason:
> `[FLAGGED: stated $60,000, verified value is 60000.00 — The source field q2_revenue represents second quarter revenue, but it is being used to describe fourth quarter revenue.]`

## 5. Engineering Reliability & Complex Problem Solving

During the hackathon, we encountered and solved several complex engineering challenges to make Vouch enterprise-ready:

### Bypassing API Strict Schema Constraints
When enforcing structured JSON outputs, standard Pydantic models automatically inject `additionalProperties: false` into the JSON Schema. This strictness causes the Google Gemini Developer API to reject the request entirely. 
**Solution:** We engineered a bypass by dynamically checking the active LLM provider. If running Gemini, Vouch abandons Pydantic and constructs a native `google.genai.types.Schema` object with `any_of` logic, satisfying the API while maintaining perfect structured output.

### Multi-LLM Provider Architecture
Enterprise clients often require model redundancy. 
**Solution:** We built in dynamic provider switching, allowing developers to toggle the underlying logic engines between **Google's Gemini 3.1 Flash-Lite** and **Groq's Llama 3 (70B)** simply by changing the `LLM_PROVIDER` environment variable. The code handles the entirely different API signatures and schema requirements transparently under the hood.

### Order-Robust Verification Matrices
LLMs are non-deterministic in how they list source fields within tags (e.g., `q1,q2` vs `q2,q1`). Hardcoding an index for the "baseline" value in a percentage calculation leads to false negatives.
**Solution:** The Verify Node computes both possible permutations for percentage and difference calculations, ensuring that the math checks out regardless of how the LLM ordered the fields.

### Resilient Numeric Cleanup & Failure Recovery
Stated values containing commas, spaces, currency symbols, or percentage signs (e.g., `$46,000.00`) typically crash float conversion. Vouch cleans these dynamically via regex-based float extraction. Additionally, to protect against temporary API throttling or 503 errors, the graph includes a 3-turn retry loop with exponential backoff on all network calls.

## 6. Honest Scope Cuts

Given our hackathon build time and constraints, we intentionally excluded:
* Human-in-the-loop (HITL) manual override gates (forcing users to accept/reject flags).
* Multi-container deployments (A2A architecture).
* Cloud-native deployment pipeline and Cloud Trace observability.
* Multi-domain financial/budget logic (we kept calculations strictly to basic arithmetic: sums, differences, and percentages).

## 7. Tech Stack

* **Google Agent Development Kit (ADK) 2.0:** Workflow Graph API, `InMemoryRunner`, `SessionService`.
* **Gemini 3.1 Flash & Groq (Llama 3 70B):** Underpinning the Draft and Semantic Verify Nodes.
* **agents-cli:** Toolchain and skill management.
* **uv:** High-performance package manager and virtual environment runner.
* **FastAPI:** Providing the real-time interactive Dev UI server running locally for judges.

---
*Vouch demonstrates that we don't need to choose between the fluency of Generative AI and the accuracy of deterministic computing. By bridging them through an agentic workflow, we get the best of both worlds.*

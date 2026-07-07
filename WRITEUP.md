# 🧾 Vouch — Hybrid Deterministic & Semantic Truth-Checking Layer for Generative Prose

**Track:** Freestyle Track  
**Author:** Hemant Kumar  
**GitHub:** [https://github.com/HemantKumar822/vouch-agent](https://github.com/HemantKumar822/vouch-agent)  
**Video Presentation:** `[INSERT_YOUTUBE_LINK_HERE]` 🎥

---

## 1. 🎯 Problem Statement
Large Language Models (LLMs) are incredibly powerful reasoning engines, but their fundamental nature as probabilistic token-predictors introduces a critical flaw in enterprise environments: **they cannot reliably perform arithmetic, and they frequently hallucinate data mapping.**

When summarizing an earnings report, an LLM might correctly cite "$50,000" but incorrectly attribute it to Q4 instead of Q1. Or it might attempt to calculate growth and confidently output "a 20% increase" when the true math yields 15%. 

Asking an LLM to "self-correct" does not yield a reliable signal. Vouch solves this through a **strict separation of concerns**: an LLM writes the narrative, while an independent, deterministic engine verifies the math—backed by a secondary LLM-Judge to catch semantic context hallucinations.

## 2. 🧠 Concepts Demonstrated
To satisfy the submission requirements, Vouch explicitly demonstrates **four (4) of the Key Concepts** covered in the course:

| Hackathon Key Concept | Implementation / Evidence | Description |
|---|---|---|
| **Agent / Multi-agent system (ADK)** *(Code)* | `app/agent.py` & `app/*_node.py` | Google ADK 2.0 directed graph separating drafting, extracting, and verifying logic into a multi-agent workflow. |
| **Agent Skills / Agents CLI** *(Code)* | `agents-cli-manifest.yaml` | Scaffolding and project structure managed via the official Agents CLI toolchain. |
| **Deployability** *(Code/Video)* | `Dockerfile` & `fast_api_app.py` | Containerized FastAPI application ready for immediate GCP Cloud Run deployment. |
| **Antigravity** *(Video)* | *(Mentioned in Video)* | The entire project architecture, Pydantic API bypass, and hybrid verifier logic were pair-programmed alongside Antigravity. |

## 3. 🏗️ Architecture
Vouch abandons the monolithic "mega-prompt" paradigm in favor of a specialized four-node directed graph orchestrating the workflow:

```text
[ Unstructured Prompt ]
          │
          ▼
+-------------------+
|  Draft Node (LLM) |  <-- Generates tagged prose
+-------------------+
          │
          ▼
+-------------------+
| Extract Node (Re) |  <-- Parses structured claims
+-------------------+
          │
          ▼
+-------------------+
| HYBRID VERIFY NODE|  <-- 1. Math Check (Deterministic)
|                   |  <-- 2. Semantic Check (LLM-Judge)
+-------------------+
          │
          ▼
+-------------------+
|   Output Node     |  <-- Assembles final audited report
+-------------------+
          │
          ▼
[ Final Audited Report ]
```

- **`draft_node.py` (The Writer):** Parses unstructured chat into structured JSON, generates 3–5 sentences of prose, and tags every numeric claim using a strict schema: `<<claim:LABEL|VALUE|FIELDS>>`.
- **`extract_node.py` (The Parser):** Uses regular expressions to extract these embedded tags into structured Python dictionaries.
- **`verify_node.py` (The Gatekeeper):** Our custom **Hybrid Verifier** (detailed below).
- **`output_node.py` (The Auditor):** Replaces verified tags with clean values, flags discrepancies inline with specific failure reasons, and appends an audit score.

## 4. The Hybrid Verifier in Action
The agent NEVER implicitly trusts the drafting LLM's math or context. When claims arrive at the `verify_node`, they undergo a strict two-pass inspection:

1. **The Math Pass (Deterministic):** Independently recomputes every percentage change, difference, and addition directly from the source numbers, validating the stated value within a 1% relative tolerance. This involves zero LLM inference.
2. **The Semantic Pass (LLM-as-a-Judge):** Sends all mathematically valid claims to a secondary, isolated LLM prompt to verify the semantic context. 

### *Catching the Adversarial Hallucination*
If we ask the LLM for Q4 revenue but only provide Q1 and Q2 data, the LLM will mathematically use the Q2 number but claim it is Q4. The Math Pass validates the number, but the Semantic Pass intercepts it, generating a clear rejection reason:
> `[FLAGGED: stated $60,000, verified value is 60000.00 — The source field q2_revenue represents second quarter revenue, but it is being used to describe fourth quarter revenue.]`

## 5. Complex Engineering Solutions
During development, we solved several critical engineering challenges to make Vouch enterprise-ready:
- **Bypassing Strict API Schemas:** Standard Pydantic models automatically inject `additionalProperties: false`, causing the Gemini API to reject requests. We engineered a bypass that constructs native `google.genai.types.Schema` objects dynamically when routing to Gemini.
- **Multi-Provider Fallback:** Built built-in toggle logic allowing developers to seamlessly swap underlying engines between Google's Gemini and Groq's Llama 3 via a single `.env` variable (`LLM_PROVIDER`).
- **Order-Robust Verification Matrices:** LLMs non-deterministically sort source fields within tags (e.g., `q1,q2` vs `q2,q1`). The Verify Node computes matrix permutations for all calculations to prevent false negatives caused by field ordering.

## 6. Live Demo & Setup Instructions
**Public Project Link:** [https://github.com/HemantKumar822/vouch-agent](https://github.com/HemantKumar822/vouch-agent)

Since a live public deployment is not feasible within the hackathon time limit, please run the interactive local UI:

```bash
# 1. Clone the repository
git clone https://github.com/HemantKumar822/vouch-agent.git
cd vouch-agent

# 2. Configure Environment (Add your Gemini API Key)
cp .env.example .env

# 3. Securely install dependencies using uv
uv sync

# 4. Launch the local interactive UI 
PORT=8001 uv run python app/fast_api_app.py
```
Open your browser to **`http://localhost:8001/dev-ui`** and try testing an adversarial hallucination prompt to see the Hybrid Verifier catch it in real-time!

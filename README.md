# Vouch

**A deterministic truth-checking layer for LLM-generated numeric reports.**

Vouch is an agentic AI system built on the [Google Agent Development Kit (ADK) 2.0](https://adk.dev/) that generates natural language report summaries and **automatically verifies every numeric claim** against the underlying source data. If a claim is wrong — whether from LLM hallucination or data drift — Vouch flags it inline with the correct value.

---

## Why Vouch?

LLMs are fluent writers but unreliable arithmeticians. Monolithic "write and self-check" prompts double down on the same probabilistic reasoning. Vouch solves this by separating concerns:

- **One LLM node** writes the prose and marks every numeric claim with structured tags
- **A Hybrid Verification Engine** extracts, mathematically recomputes, and semantically fact-checks those claims — catching both arithmetic errors and context hallucinations.
- **Multi-Provider Support** effortlessly swap between Gemini and Groq (Llama 3) via the `.env` file.

---

## How It Works

```
START → draft_node → extract_node → verify_node (Hybrid) → output_node
```

| Node | Type | Responsibility |
|------|------|----------------|
| `draft_node` | **LLM** (Gemini/Groq) | Parses unstructured chat, writes 3–5 sentence prose; tags every numeric claim as `<<claim:LABEL\|VALUE\|FIELDS>>` |
| `extract_node` | **Deterministic** | Regex-parses tags into structured dicts; produces clean, readable prose |
| `verify_node` | **Hybrid** | 1. **Math**: Recomputes `_pct`, `_diff`, `_sum` claims. 2. **Semantic (LLM-Judge)**: Checks for context hallucinations (e.g., using Q2 data to describe Q4). |
| `output_node` | **Deterministic** | Replaces tags with clean values (PASS) or `[FLAGGED: ...]` annotations (FAIL); appends audit summary |

### Claim Tag Format

```
<<claim:LABEL|STATED_VALUE|SOURCE_FIELD_1,SOURCE_FIELD_2>>
```

- `_pct` suffix → percentage change verification
- `_diff` suffix → raw difference verification  
- `_sum` suffix → summation verification

---

## Demo Output

**Case A (all claims correct):**
```
Q3 marketing spend increased by 6,000, representing a 15% rise from Q2. ...

---
Claims checked: 4
Passed: 4
Flagged: 0
```

**Case B (source data changed — old draft vs new numbers):**
```
Q3 marketing spend increased by [FLAGGED: stated 6,000, verified value is 10000.00 — value_mismatch], 
representing a [FLAGGED: stated 15%, verified value is 25.00% — value_mismatch] rise from Q2. ...

---
Claims checked: 4
Passed: 2
Flagged: 2
```

---

## Project Structure

```
vouch/
├── app/
│   ├── agent.py           # Workflow graph wiring (ADK 2.0 Workflow API)
│   ├── draft_node.py      # LLM node — Gemini Flash report generation
│   ├── extract_node.py    # Deterministic claim tag extraction (regex)
│   ├── verify_node.py     # Deterministic arithmetic verification
│   ├── output_node.py     # Final report assembly with flagging
│   ├── fast_api_app.py    # FastAPI server for GCP deployment
│   └── app_utils/
│       ├── telemetry.py   # OpenTelemetry / Cloud Logging setup
│       └── typing.py      # Pydantic models (Feedback)
├── config/
│   └── verify_config.json # Tolerance threshold (default: 1.0%)
├── tests/
│   ├── unit/
│   │   ├── test_verify_node.py   # Pure function and claim processing tests
│   │   ├── test_extract_node.py  # Regex extraction tests
│   │   └── test_output_node.py   # Final output assembly tests
│   └── integration/
│       └── test_vouch_pipeline.py # Full ADK pipeline tests (no LLM)
├── main.py                # CLI demo entrypoint (success + failure case)
├── demo.py                # Minimal 18-line demo script
├── pyproject.toml         # Dependencies and tool config
├── Makefile               # make install / make run
├── Dockerfile             # Container for GCP deployment
└── .env.example           # Environment variable template
```

---

## Hackathon Judges: Detailed Setup Instructions (Part C)

Since a live public deployment with a hosted frontend is not feasible within the hackathon time constraints, please follow these detailed instructions to run the Vouch interactive UI on your local machine.

### Prerequisites
- **Python 3.11–3.13**
- [**uv**](https://docs.astral.sh/uv/getting-started/installation/) — The fast Python package manager.
- A **Google AI Studio API key** for Gemini Flash ([Get one here](https://aistudio.google.com/apikey)).
- *(Optional)* A Groq API key to test the multi-provider fallback.

### 1. Clone the Repository
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd vouch
```

### 2. Configure Environment Variables
Copy the template file to create your local `.env`:
```bash
cp .env.example .env
```
Open `.env` in your code editor and insert your Gemini API key:
```env
# LLM Provider selection: 'gemini' or 'groq'
LLM_PROVIDER=gemini

# Google Gemini API configuration
GEMINI_API_KEY=your_actual_api_key_here
```

### 3. Install Dependencies
Use `uv` to securely and quickly install all dependencies into a virtual environment:
```bash
uv pip install -e .
```

### 4. Run the Interactive Dev UI
Start the local FastAPI server using `uv`. We specify port 8001 to avoid standard system port conflicts.
```bash
PORT=8001 uv run python app/fast_api_app.py
```

### 5. Experience Vouch!
Open your web browser and navigate to:
**👉 `http://localhost:8001/dev-ui`**

- Click **"New Session"**.
- Paste an adversarial prompt (e.g., asking for Q4 revenue but only providing Q1 and Q2) to see the Hybrid Verifier catch the LLM red-handed!

---

### Run Automated Tests (Optional)

```bash
# Unit tests only (no API key required — fully deterministic)
uv run pytest tests/unit -v

# Integration tests (no API key required — uses draft bypass)
uv run pytest tests/integration -v
```
# All tests
uv run pytest tests/ -v

---

## Configuration

Edit `config/verify_config.json` to change the verification tolerance:

```json
{
  "tolerance": 1.0
}
```

`tolerance` is a relative percentage threshold (e.g. `1.0` = 1% relative difference allowed).

---

## Environment Variables

Vouch supports **Multi-Provider LLM execution**. You can seamlessly toggle between Google's Gemini models and Groq's Llama models by changing a single variable. Vouch dynamically handles the differences between Pydantic's JSON schema (for Groq) and the native `google.genai.types.Schema` (for Gemini).

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | Yes | `gemini` | Determines which LLM runs the drafting and semantic verification. Accepts `gemini` or `groq`. |
| `GEMINI_API_KEY` | If `LLM_PROVIDER=gemini` | — | Google AI Studio API key for Gemini. |
| `GEMINI_MODEL` | No | `gemini-3.1-flash-lite` | The specific Gemini model ID to use. |
| `GROQ_API_KEY` | If `LLM_PROVIDER=groq` | — | Groq API key for Llama 3 models. |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | The specific Groq model ID to use. |
| `PORT` | No | `8001` | Port for the local FastAPI dev server. |

---

## Engineering Notes

### Reliability Features

- **Retry with backoff:** `draft_node` retries up to 3× on Gemini 503 errors
- **Permutation guards:** `verify_node` tests both field orderings for `_pct` and `_diff` to tolerate non-deterministic LLM field listing
- **Robust parsing:** Stated values like `$46,000` or `15.0%` are cleaned via regex before comparison
- **Draft bypass:** If `draft_text` is already in session state, the LLM call is skipped — enables re-verification of existing reports

### Known Scope Limits (Prototype)

- No persistent session storage (in-memory only)
- No authentication on the `/feedback` endpoint
- No human-in-the-loop override gate
- `_sum` claims only check exact sum — no support for weighted averages or ratios

---

## Deployment

### Local FastAPI server (development)

```bash
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8001
```

### GCP Cloud Run

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

> **Note:** GCP deployment requires Google Cloud credentials and a project. See the [ADK deployment guide](https://adk.dev/deploy).

---

## Built With

- [Google Agent Development Kit (ADK) 2.0](https://adk.dev/) — Workflow graph, InMemoryRunner, SessionService
- [Gemini 2.5 Flash](https://ai.google.dev/gemini-api/docs/models) — LLM for draft generation
- [google-agents-cli](https://pypi.org/project/google-agents-cli/) — Scaffolding, toolchain management
- [uv](https://docs.astral.sh/uv/) — Package management and runner
- [FastAPI](https://fastapi.tiangolo.com/) — HTTP server for production deployment

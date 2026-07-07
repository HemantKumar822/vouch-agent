"""
vouch_run.py -- Interactive Vouch runner with full structured logging.

Usage:
    uv run python vouch_run.py            # Full demo (calls Gemini API)
    uv run python vouch_run.py --bypass   # Demo with pre-built draft (no API call)

The --bypass flag injects a pre-fabricated draft so you can see the full
extract -> verify -> output pipeline even when your API quota is exhausted.
"""
import sys
import json
import logging
import argparse

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent

# ---------------------------------------------------------------------------
# Pre-fabricated draft for --bypass mode (no LLM call needed)
# ---------------------------------------------------------------------------
BYPASS_DRAFT = (
    "Q3 marketing spend increased by "
    "<<claim:q3_spend_pct|15%|q2_spend,q3_spend>> compared to Q2, "
    "driven by expanded digital ad buys. "
    "The total increase in budget was "
    "<<claim:q3_spend_diff|$6,000|q2_spend,q3_spend>>, "
    "bringing Q3 spend to $46,000. "
    "Lead generation also improved, adding "
    "<<claim:q3_leads_diff|10|q2_leads,q3_leads>> new leads "
    "for a <<claim:q3_leads_pct|5%|q2_leads,q3_leads>> gain over Q2."
)

SOURCE_CORRECT = {
    "q2_spend": 40000,
    "q3_spend": 46000,
    "q2_leads": 200,
    "q3_leads": 210,
}
SOURCE_WRONG = {
    "q2_spend": 40000,
    "q3_spend": 50000,   # Changed -- breaks the 15% and $6k claims
    "q2_leads": 200,
    "q3_leads": 210,
}
BRIEF = "write a 3-sentence Q3 marketing summary"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("  %(name)-18s | %(message)s"))
    for name in ("vouch.draft", "vouch.extract", "vouch.verify", "vouch.output"):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        log.propagate = False

# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

_APP = "vouch_run"


def _run(source_data: dict, brief: str, draft_text: str | None = None) -> dict:
    """Runs the full Vouch pipeline and returns the final session state."""
    svc = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=svc, app_name=_APP)

    state: dict = {"source_data": source_data, "brief": brief}
    if draft_text is not None:
        state["draft_text"] = draft_text

    session = svc.create_session_sync(app_name=_APP, user_id="user", state=state)
    list(runner.run(
        user_id="user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
    ))
    return svc.get_session_sync(app_name=_APP, user_id="user", session_id=session.id).state

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _hr(char="-", w=72): print(char * w)

def _wrap_print(text: str, indent: str = "  ") -> None:
    for line in text.splitlines():
        while len(line) > 76:
            print(indent + line[:76])
            line = line[76:]
        print(indent + line)

def _claim_table(claims: list[dict]) -> None:
    W = [28, 12, 14, 8, 20]
    _hr()
    print(f"  {'Label':<{W[0]}} {'Stated':<{W[1]}} {'Recomputed':<{W[2]}} {'Result':<{W[3]}} Reason")
    _hr()
    for c in claims:
        verdict = c.get("verification", "?")
        rv = c.get("recomputed_value", "")
        if isinstance(rv, float):
            rv_str = f"{rv:.2f}%" if c["label"].endswith("_pct") else f"{rv:.2f}"
        else:
            rv_str = str(rv)
        result_str = "[PASS]" if verdict == "PASS" else "[FAIL]"
        reason = c.get("reason", "") if verdict == "FAIL" else ""
        print(f"  {c['label']:<{W[0]}} {c['stated_value']:<{W[1]}} {rv_str:<{W[2]}} {result_str:<{W[3]}} {reason}")
    _hr()

def _print_case(title: str, source: dict, brief: str, draft_text: str | None = None) -> str:
    print()
    _hr("=")
    print(f"  {title}")
    _hr("=")
    print(f"  Brief  : {brief}")
    print(f"  Source : {json.dumps(source)}")
    mode = "BYPASS (pre-fabricated draft, no API call)" if draft_text else "GENERATE + VERIFY (calls Gemini API)"
    print(f"  Mode   : {mode}")
    print()

    try:
        state = _run(source, brief, draft_text)
    except Exception as exc:
        print()
        print("  [ERROR] Pipeline failed:")
        print(f"  {exc}")
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            print()
            print("  >> You've hit the free-tier daily quota for Gemini API.")
            print("  >> Run with --bypass to demo without any API calls:")
            print("  >>   uv run python vouch_run.py --bypass")
            print("  >> Or wait until tomorrow for quota to reset.")
            print("  >> Or upgrade at: https://ai.dev/rate-limit")
        return ""

    raw = state.get("draft_text", "")
    _hr("-")
    print("  RAW DRAFT (with claim tags):")
    _hr("-")
    _wrap_print(raw)

    print()
    _hr("-")
    print("  CLEAN DRAFT (tags stripped):")
    _hr("-")
    _wrap_print(state.get("draft_text_clean", ""))

    print()
    print("  CLAIM VERIFICATION TABLE:")
    _claim_table(state.get("claims", []))

    print()
    print("  FINAL OUTPUT (with FLAGGED annotations):")
    _hr("-")
    final_output = state.get("final_output", "")
    _wrap_print(final_output)

    # Write the report to disk as a file so the user can access it directly
    file_prefix = "vouch_report_a.md" if "CASE A" in title else "vouch_report_b.md"
    try:
        with open(file_prefix, "w", encoding="utf-8") as f:
            f.write(final_output)
        print()
        print(f"  [EXPORT] Report saved to disk: {file_prefix}")
    except Exception as e:
        print(f"  [EXPORT WARNING] Failed to write report file: {e}")

    return raw

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Vouch interactive runner")
    parser.add_argument(
        "--bypass",
        action="store_true",
        help="Skip LLM generation entirely; use a pre-fabricated draft (no API quota used)",
    )
    args = parser.parse_args()

    _configure_logging()

    if args.bypass:
        print()
        print("  [BYPASS MODE] Using pre-fabricated draft -- no Gemini API call needed.")

        # Case A: correct numbers -- all claims PASS
        _print_case(
            title="CASE A  --  Verify pre-built draft (all numbers correct)",
            source=SOURCE_CORRECT,
            brief=BRIEF,
            draft_text=BYPASS_DRAFT,
        )

        # Case B: same draft, wrong source -- spend claims FAIL
        _print_case(
            title="CASE B  --  Re-verify same draft against UPDATED source data",
            source=SOURCE_WRONG,
            brief=BRIEF,
            draft_text=BYPASS_DRAFT,
        )

    else:
        # Case A: generate fresh draft + verify
        draft = _print_case(
            title="CASE A  --  Generate new draft + verify (calls Gemini API)",
            source=SOURCE_CORRECT,
            brief=BRIEF,
        )

        if draft:
            # Case B: reuse generated draft against wrong source
            _print_case(
                title="CASE B  --  Re-verify SAME draft against UPDATED source data",
                source=SOURCE_WRONG,
                brief=BRIEF,
                draft_text=draft,
            )


if __name__ == "__main__":
    main()

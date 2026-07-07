"""Integration tests: full Vouch graph pipeline executed end-to-end.

Strategy:
  - Inject a pre-fabricated ``draft_text`` into session state so the draft_node
    bypass fires and the pipeline runs completely **deterministically** — no
    Gemini API call is needed.
  - Each test creates its own ``Runner`` + fresh ``InMemorySessionService`` to
    guarantee complete state isolation between test runs.
"""
import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import root_agent


# ── Fixed draft (hand-crafted — no LLM needed) ───────────────────────────────
FIXED_DRAFT = (
    "Q3 marketing spend increased by <<claim:q3_spend_diff|6,000|q2_spend,q3_spend>>, "
    "representing a <<claim:q3_spend_pct|15%|q2_spend,q3_spend>> rise from Q2. "
    "Lead generation grew by <<claim:q3_leads_diff|10|q2_leads,q3_leads>>, "
    "a <<claim:q3_leads_pct|5%|q2_leads,q3_leads>> improvement."
)

SOURCE_DATA_CORRECT = {
    "q2_spend": 40000,
    "q3_spend": 46000,
    "q2_leads": 200,
    "q3_leads": 210,
}

SOURCE_DATA_WRONG = {
    "q2_spend": 40000,
    "q3_spend": 50000,   # breaks the 15% / 6,000 spend claims
    "q2_leads": 200,
    "q3_leads": 210,
}

_APP_NAME = "vouch_integration_test"


async def _run_pipeline(source_data: dict, draft_text: str | None = None) -> dict:
    """Runs the full Vouch workflow and returns the final session state.

    Creates a fresh ``InMemorySessionService`` for every call to guarantee
    complete state isolation between test cases.
    """
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name=_APP_NAME,
    )

    state: dict = {"source_data": source_data, "brief": "Q3 marketing summary"}
    if draft_text is not None:
        state["draft_text"] = draft_text

    session = session_service.create_session_sync(
        app_name=_APP_NAME,
        user_id="integration_test",
        state=state,
    )

    # Consume all events synchronously (Runner.run is sync; wraps async internally)
    list(
        runner.run(
            user_id="integration_test",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text="run")]
            ),
        )
    )

    final = session_service.get_session_sync(
        app_name=_APP_NAME,
        user_id="integration_test",
        session_id=session.id,
    )
    return final.state


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_claims_pass_end_to_end():
    """Correct source data + correct draft → all 4 claims PASS."""
    state = await _run_pipeline(SOURCE_DATA_CORRECT, draft_text=FIXED_DRAFT)

    summary = state["summary"]
    assert summary["total_claims"] == 4
    assert summary["passed"] == 4
    assert summary["failed"] == 0

    final_output = state["final_output"]
    assert "[FLAGGED:" not in final_output
    assert "Claims checked: 4" in final_output
    assert "Passed: 4" in final_output


@pytest.mark.asyncio
async def test_spend_claims_flagged_when_source_data_changes():
    """Wrong source data → spend claims flagged, lead claims unaffected."""
    state = await _run_pipeline(SOURCE_DATA_WRONG, draft_text=FIXED_DRAFT)

    summary = state["summary"]
    assert summary["total_claims"] == 4
    assert summary["failed"] == 2     # spend diff + spend pct
    assert summary["passed"] == 2     # leads diff + leads pct unaffected

    final_output = state["final_output"]
    assert final_output.count("[FLAGGED:") == 2
    assert "value_mismatch" in final_output
    assert "Flagged: 2" in final_output


@pytest.mark.asyncio
async def test_claims_state_populated():
    """All expected intermediate state keys are set after a successful run."""
    state = await _run_pipeline(SOURCE_DATA_CORRECT, draft_text=FIXED_DRAFT)

    for key in ("draft_text", "claims", "draft_text_clean", "summary", "final_output"):
        assert key in state, f"Expected state key '{key}' is missing"

    assert isinstance(state["claims"], list)
    assert len(state["claims"]) == 4

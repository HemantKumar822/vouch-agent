"""Unit tests for output_node.py.

Tests the final report assembly step, including:
- PASS claims produce clean, inline stated values
- FAIL claims produce [FLAGGED: ...] annotations
- Audit summary block is appended correctly
- Percentage formatting in flagged values
- All claims flagged / all claims passing
"""
import pytest
from app.output_node import output_node
from unittest.mock import MagicMock


def _make_ctx():
    ctx = MagicMock()
    ctx.state = {}
    return ctx


DRAFT_TEXT = (
    "Q3 marketing spend increased by <<claim:q3_spend_diff|6,000|q2_spend,q3_spend>>, "
    "representing a <<claim:q3_spend_pct|15%|q2_spend,q3_spend>> rise from Q2."
)


def _make_claims(spend_diff_pass=True, spend_pct_pass=True):
    return [
        {
            "label": "q3_spend_diff",
            "stated_value": "6,000",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_diff|6,000|q2_spend,q3_spend>>",
            "verification": "PASS" if spend_diff_pass else "FAIL",
            "recomputed_value": 6000.0 if spend_diff_pass else 10000.0,
            **({"reason": "value_mismatch"} if not spend_diff_pass else {}),
        },
        {
            "label": "q3_spend_pct",
            "stated_value": "15%",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_pct|15%|q2_spend,q3_spend>>",
            "verification": "PASS" if spend_pct_pass else "FAIL",
            "recomputed_value": 15.0 if spend_pct_pass else 25.0,
            **({"reason": "value_mismatch"} if not spend_pct_pass else {}),
        },
    ]


class TestOutputNode:
    @pytest.mark.asyncio
    async def test_all_pass_produces_clean_text(self):
        ctx = _make_ctx()
        claims = _make_claims(spend_diff_pass=True, spend_pct_pass=True)
        summary = {"total_claims": 2, "passed": 2, "failed": 0}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        output = event.output

        assert "<<claim:" not in output
        assert "[FLAGGED:" not in output
        assert "6,000" in output
        assert "15%" in output

    @pytest.mark.asyncio
    async def test_fail_claim_produces_flagged_annotation(self):
        ctx = _make_ctx()
        claims = _make_claims(spend_diff_pass=True, spend_pct_pass=False)
        summary = {"total_claims": 2, "passed": 1, "failed": 1}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        output = event.output

        assert "[FLAGGED: stated 15%, verified value is 25.00%" in output
        assert "value_mismatch" in output
        # The passing claim should still be clean
        assert "6,000" in output
        assert "<<claim:q3_spend_diff" not in output

    @pytest.mark.asyncio
    async def test_audit_summary_appended(self):
        ctx = _make_ctx()
        claims = _make_claims(spend_diff_pass=True, spend_pct_pass=True)
        summary = {"total_claims": 2, "passed": 2, "failed": 0}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        output = event.output

        assert "---" in output
        assert "Claims checked: 2" in output
        assert "Passed: 2" in output
        assert "Flagged: 0" in output

    @pytest.mark.asyncio
    async def test_all_fail_audit_summary(self):
        ctx = _make_ctx()
        claims = _make_claims(spend_diff_pass=False, spend_pct_pass=False)
        summary = {"total_claims": 2, "passed": 0, "failed": 2}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        output = event.output

        assert "Passed: 0" in output
        assert "Flagged: 2" in output
        assert output.count("[FLAGGED:") == 2

    @pytest.mark.asyncio
    async def test_pct_flag_appends_percent_sign(self):
        ctx = _make_ctx()
        claims = _make_claims(spend_diff_pass=True, spend_pct_pass=False)
        summary = {"total_claims": 2, "passed": 1, "failed": 1}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        output = event.output
        # The verified value for a percentage should include the % sign
        assert "25.00%" in output

    @pytest.mark.asyncio
    async def test_state_contains_final_output(self):
        ctx = _make_ctx()
        claims = _make_claims()
        summary = {"total_claims": 2, "passed": 2, "failed": 0}
        event = await output_node(ctx, claims=claims, draft_text=DRAFT_TEXT, summary=summary)
        assert "final_output" in event.actions.state_delta
        assert event.actions.state_delta["final_output"] == event.output

    @pytest.mark.asyncio
    async def test_empty_claims_list(self):
        ctx = _make_ctx()
        summary = {"total_claims": 0, "passed": 0, "failed": 0}
        text = "No numeric claims in this report."
        event = await output_node(ctx, claims=[], draft_text=text, summary=summary)
        output = event.output

        assert "No numeric claims in this report." in output
        assert "Claims checked: 0" in output

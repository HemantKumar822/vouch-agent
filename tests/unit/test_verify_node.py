"""Unit tests for the deterministic helper functions in verify_node.py.

These tests cover:
- parse_numeric_value: clean string → float
- check_percentage_change: both permutations, tolerance, reporting canonical
- check_difference: both permutations, tolerance, canonical reporting
- check_sum: basic and tolerance edge cases
- verify_node: full claim list processing (PASS, FAIL, missing field, bad label)
"""
import pytest
from app.verify_node import (
    parse_numeric_value,
    check_percentage_change,
    check_difference,
    check_sum,
    verify_node,
)
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# parse_numeric_value
# ---------------------------------------------------------------------------

class TestParseNumericValue:
    def test_plain_integer(self):
        assert parse_numeric_value("10") == 10.0

    def test_plain_float(self):
        assert parse_numeric_value("15.5") == 15.5

    def test_percentage_stripped(self):
        assert parse_numeric_value("15%") == 15.0

    def test_currency_stripped(self):
        assert parse_numeric_value("$46,000") == 46000.0

    def test_commas_stripped(self):
        assert parse_numeric_value("6,000") == 6000.0

    def test_mixed_formatting(self):
        assert parse_numeric_value("  $1,234.56  ") == 1234.56

    def test_negative_value(self):
        assert parse_numeric_value("-5%") == -5.0

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_numeric_value("no numbers here")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_numeric_value("")


# ---------------------------------------------------------------------------
# check_percentage_change
# ---------------------------------------------------------------------------

class TestCheckPercentageChange:
    def test_exact_match(self):
        passed, recomputed = check_percentage_change(40000, 46000, 15.0, 1.0)
        assert passed is True
        assert abs(recomputed - 15.0) < 0.01

    def test_value_mismatch(self):
        passed, recomputed = check_percentage_change(40000, 46000, 25.0, 1.0)
        assert passed is False
        # canonical formula is still returned
        assert abs(recomputed - 15.0) < 0.01

    def test_reverse_order_fields_accepted(self):
        # LLM may emit (q3_spend, q2_spend) — reverse permutation guard
        passed, recomputed = check_percentage_change(46000, 40000, 15.0, 1.0)
        assert passed is True
        # Canonical (forward-order) recomputed is always reported
        assert abs(recomputed - (-13.04)) < 0.1  # forward = (40000-46000)/46000*100

    def test_within_tolerance(self):
        # 15.1% stated vs 15.0% actual — within 1% tolerance
        passed, _ = check_percentage_change(40000, 46000, 15.1, 1.0)
        assert passed is True

    def test_outside_tolerance(self):
        # 15.5% stated vs 15.0% actual — outside 1% relative tolerance
        # relative diff = |15.5 - 15.0| / 15.0 = 3.3% > 1%
        passed, _ = check_percentage_change(40000, 46000, 15.5, 1.0)
        assert passed is False

    def test_zero_denominator_returns_zero(self):
        passed, recomputed = check_percentage_change(0, 100, 50.0, 1.0)
        assert passed is False
        assert recomputed == 0.0


# ---------------------------------------------------------------------------
# check_difference
# ---------------------------------------------------------------------------

class TestCheckDifference:
    def test_exact_match(self):
        passed, recomputed = check_difference(200, 210, 10.0, 1.0)
        assert passed is True
        assert recomputed == 10.0

    def test_reverse_order_accepted(self):
        passed, recomputed = check_difference(210, 200, 10.0, 1.0)
        assert passed is True
        # canonical (forward) value returned: 200 - 210 = -10 — forward
        assert recomputed == -10.0

    def test_value_mismatch(self):
        passed, recomputed = check_difference(200, 210, 15.0, 1.0)
        assert passed is False
        assert recomputed == 10.0

    def test_tolerance_boundary(self):
        # stated = 10, actual = 10.05 — 0.5% relative diff < 1% tolerance → PASS
        passed, _ = check_difference(200, 210.05, 10.0, 1.0)
        assert passed is True

    def test_zero_stated(self):
        # Both permutations are 0; stated 0 should pass
        passed, recomputed = check_difference(100, 100, 0.0, 1.0)
        assert passed is True
        assert recomputed == 0.0


# ---------------------------------------------------------------------------
# check_sum
# ---------------------------------------------------------------------------

class TestCheckSum:
    def test_exact_sum(self):
        passed, total = check_sum([40000, 46000], 86000.0, 1.0)
        assert passed is True
        assert total == 86000.0

    def test_mismatch(self):
        passed, total = check_sum([40000, 46000], 90000.0, 1.0)
        assert passed is False
        assert total == 86000.0

    def test_single_field_sum(self):
        passed, total = check_sum([50000], 50000.0, 1.0)
        assert passed is True

    def test_three_fields(self):
        passed, total = check_sum([10, 20, 30], 60.0, 1.0)
        assert passed is True


# ---------------------------------------------------------------------------
# verify_node (integration of the full claim processing pipeline)
# ---------------------------------------------------------------------------

SOURCE_DATA = {
    "q2_spend": 40000,
    "q3_spend": 46000,
    "q2_leads": 200,
    "q3_leads": 210,
}


def _make_ctx():
    ctx = MagicMock()
    ctx.state = {}
    return ctx


@pytest.mark.asyncio
async def test_verify_node_all_pass():
    claims = [
        {
            "label": "q3_spend_pct",
            "stated_value": "15%",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_pct|15%|q2_spend,q3_spend>>",
        },
        {
            "label": "q3_spend_diff",
            "stated_value": "6,000",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_diff|6,000|q2_spend,q3_spend>>",
        },
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]
    summary = event.actions.state_delta["summary"]

    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert all(c["verification"] == "PASS" for c in result_claims)


@pytest.mark.asyncio
async def test_verify_node_fail_on_wrong_stated_value():
    claims = [
        {
            "label": "q3_spend_pct",
            "stated_value": "25%",  # wrong — actual is 15%
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_pct|25%|q2_spend,q3_spend>>",
        }
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]
    summary = event.actions.state_delta["summary"]

    assert summary["failed"] == 1
    assert result_claims[0]["verification"] == "FAIL"
    assert result_claims[0]["reason"] == "value_mismatch"
    assert abs(result_claims[0]["recomputed_value"] - 15.0) < 0.01


@pytest.mark.asyncio
async def test_verify_node_missing_source_field():
    claims = [
        {
            "label": "q4_spend_pct",
            "stated_value": "10%",
            "source_fields": ["q3_spend", "q4_spend"],  # q4_spend doesn't exist
            "raw_tag": "<<claim:q4_spend_pct|10%|q3_spend,q4_spend>>",
        }
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]

    assert result_claims[0]["verification"] == "FAIL"
    assert result_claims[0]["reason"] == "missing_source_field"


@pytest.mark.asyncio
async def test_verify_node_unknown_label_suffix():
    claims = [
        {
            "label": "q3_spend_ratio",  # unknown suffix
            "stated_value": "1.15",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_ratio|1.15|q2_spend,q3_spend>>",
        }
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]

    assert result_claims[0]["verification"] == "FAIL"
    assert result_claims[0]["reason"] == "unknown_claim_type"


@pytest.mark.asyncio
async def test_verify_node_invalid_stated_value():
    claims = [
        {
            "label": "q3_spend_pct",
            "stated_value": "N/A",  # cannot be parsed
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:q3_spend_pct|N/A|q2_spend,q3_spend>>",
        }
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]

    assert result_claims[0]["verification"] == "FAIL"
    assert result_claims[0]["reason"] == "invalid_stated_value"


@pytest.mark.asyncio
async def test_verify_node_sum_claim():
    claims = [
        {
            "label": "total_spend_sum",
            "stated_value": "$86,000",
            "source_fields": ["q2_spend", "q3_spend"],
            "raw_tag": "<<claim:total_spend_sum|$86,000|q2_spend,q3_spend>>",
        }
    ]
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=claims, source_data=SOURCE_DATA)
    result_claims = event.actions.state_delta["claims"]

    assert result_claims[0]["verification"] == "PASS"
    assert result_claims[0]["recomputed_value"] == 86000.0


@pytest.mark.asyncio
async def test_verify_node_empty_claims():
    ctx = _make_ctx()
    event = await verify_node(ctx, claims=[], source_data=SOURCE_DATA)
    summary = event.actions.state_delta["summary"]

    assert summary["total_claims"] == 0
    assert summary["passed"] == 0
    assert summary["failed"] == 0

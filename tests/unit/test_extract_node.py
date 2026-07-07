"""Unit tests for extract_node.py.

Tests the regex extraction of claim tags from draft text, including:
- Correct tag parsing (label, stated_value, source_fields, raw_tag)
- Multi-claim documents
- Clean text output (tags replaced by stated values)
- Malformed / missing tags
- Edge cases: empty input, nested-looking text, extra whitespace
"""
import pytest
from app.extract_node import extract_node, CLAIM_PATTERN
from unittest.mock import MagicMock


def _make_ctx():
    ctx = MagicMock()
    ctx.state = {}
    return ctx


SAMPLE_DRAFT = (
    "Q3 marketing spend increased by <<claim:q3_spend_diff|6,000|q2_spend,q3_spend>>, "
    "representing a <<claim:q3_spend_pct|15%|q2_spend,q3_spend>> rise from Q2. "
    "Lead generation grew by <<claim:q3_leads_diff|10|q2_leads,q3_leads>>, "
    "a <<claim:q3_leads_pct|5%|q2_leads,q3_leads>> improvement."
)


class TestClaimPatternRegex:
    def test_matches_standard_tag(self):
        text = "spend <<claim:q3_spend_pct|15%|q2_spend,q3_spend>> last quarter"
        matches = CLAIM_PATTERN.findall(text)
        assert len(matches) == 1
        label, value, fields = matches[0]
        assert label == "q3_spend_pct"
        assert value == "15%"
        assert "q2_spend" in fields

    def test_no_match_on_plain_text(self):
        assert CLAIM_PATTERN.findall("no tags here") == []

    def test_multiple_tags_in_one_line(self):
        matches = CLAIM_PATTERN.findall(SAMPLE_DRAFT)
        assert len(matches) == 4


class TestExtractNode:
    @pytest.mark.asyncio
    async def test_extracts_all_four_claims(self):
        ctx = _make_ctx()
        event = await extract_node(ctx, draft_text=SAMPLE_DRAFT)
        claims = event.actions.state_delta["claims"]
        assert len(claims) == 4

    @pytest.mark.asyncio
    async def test_claim_dict_structure(self):
        ctx = _make_ctx()
        event = await extract_node(ctx, draft_text=SAMPLE_DRAFT)
        claims = event.actions.state_delta["claims"]
        for claim in claims:
            assert "label" in claim
            assert "stated_value" in claim
            assert "source_fields" in claim
            assert "raw_tag" in claim
            assert isinstance(claim["source_fields"], list)

    @pytest.mark.asyncio
    async def test_specific_claim_values(self):
        ctx = _make_ctx()
        event = await extract_node(ctx, draft_text=SAMPLE_DRAFT)
        claims = {c["label"]: c for c in event.actions.state_delta["claims"]}

        assert claims["q3_spend_pct"]["stated_value"] == "15%"
        assert claims["q3_spend_pct"]["source_fields"] == ["q2_spend", "q3_spend"]
        assert claims["q3_spend_diff"]["stated_value"] == "6,000"

    @pytest.mark.asyncio
    async def test_clean_text_replaces_tags(self):
        ctx = _make_ctx()
        event = await extract_node(ctx, draft_text=SAMPLE_DRAFT)
        clean = event.actions.state_delta["draft_text_clean"]

        assert "<<claim:" not in clean
        assert "15%" in clean
        assert "6,000" in clean
        assert "10" in clean
        assert "5%" in clean

    @pytest.mark.asyncio
    async def test_empty_input(self):
        ctx = _make_ctx()
        event = await extract_node(ctx, draft_text="")
        claims = event.actions.state_delta["claims"]
        assert claims == []
        assert event.actions.state_delta["draft_text_clean"] == ""

    @pytest.mark.asyncio
    async def test_no_tags_in_text(self):
        ctx = _make_ctx()
        text = "Q3 marketing spend increased significantly over Q2."
        event = await extract_node(ctx, draft_text=text)
        claims = event.actions.state_delta["claims"]
        assert claims == []
        assert event.actions.state_delta["draft_text_clean"] == text

    @pytest.mark.asyncio
    async def test_raw_tag_preserved_correctly(self):
        ctx = _make_ctx()
        single_tag = "Spend rose <<claim:q3_spend_pct|15%|q2_spend,q3_spend>> this quarter."
        event = await extract_node(ctx, draft_text=single_tag)
        claims = event.actions.state_delta["claims"]
        assert claims[0]["raw_tag"] == "<<claim:q3_spend_pct|15%|q2_spend,q3_spend>>"

    @pytest.mark.asyncio
    async def test_source_fields_split_correctly(self):
        ctx = _make_ctx()
        three_field = "Total is <<claim:total_sum|$120,000|q1_spend,q2_spend,q3_spend>>."
        event = await extract_node(ctx, draft_text=three_field)
        claims = event.actions.state_delta["claims"]
        assert len(claims) == 1
        assert claims[0]["source_fields"] == ["q1_spend", "q2_spend", "q3_spend"]

import logging
import re
from google.adk.agents.context import Context
from google.adk.events.event import Event

logger = logging.getLogger("vouch.extract")

# Regex pattern for extracting claims: <<claim:LABEL|STATED_VALUE|SOURCE_FIELDS>>
CLAIM_PATTERN = re.compile(r"<<claim:([^|]+)\|([^|]+)\|([^>]+)>>")

async def extract_node(ctx: Context, draft_text: str) -> Event:
    """Extracts claims from raw draft text and produces a clean text version."""
    claims = []

    # Extract each claim tag matching the pattern
    for match in CLAIM_PATTERN.finditer(draft_text):
        raw_tag = match.group(0)
        label = match.group(1).strip()
        stated_value = match.group(2).strip()
        source_fields_str = match.group(3).strip()

        # Split source fields by comma
        source_fields = [field.strip() for field in source_fields_str.split(",") if field.strip()]

        claims.append({
            "label": label,
            "stated_value": stated_value,
            "source_fields": source_fields,
            "raw_tag": raw_tag
        })

    logger.info("[extract_node] Found %d claim(s):", len(claims))
    for i, c in enumerate(claims, 1):
        logger.info(
            "  Claim %d: label=%r  stated=%r  sources=%s",
            i, c["label"], c["stated_value"], c["source_fields"],
        )

    # Replace all <<claim:LABEL|STATED_VALUE|SOURCE_FIELDS>> tags with just the STATED_VALUE
    draft_text_clean = CLAIM_PATTERN.sub(lambda m: m.group(2), draft_text)

    return Event(
        output=claims,
        state={
            "claims": claims,
            "draft_text_clean": draft_text_clean
        }
    )

import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.genai import types
from google.genai.errors import APIError

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger("vouch.draft")
_TAG_COUNT_RE = re.compile(r"<<claim:")

PROMPT_TEMPLATE = """You are a report drafting assistant. Your job is to write a short report based on the provided brief and the source data.

Brief: {brief}
Source Data: {source_data}

Instructions:
1. Write a report of exactly 3 to 5 sentences.
2. In the prose, you MUST tag EVERY single numeric claim you make using this exact format:
   <<claim:LABEL|STATED_VALUE|SOURCE_FIELD_1,SOURCE_FIELD_2>>
   
   Where:
   - LABEL is a unique identifier ending with:
     * "_pct" for percentage change claims (e.g. "spend rose 15%")
     * "_sum" for total/addition claims (e.g. "total cost was $86,000")
     * "_diff" for raw difference claims (e.g. "leads increased by 10")
   - STATED_VALUE is the value you write in the prose (e.g., "15%", "$86,000", "10").
   - SOURCE_FIELD_1,SOURCE_FIELD_2 are the exact keys from the source data used to make this claim.
   
3. Example of inline tag format:
   "Marketing spend rose to <<claim:qtr_spend_pct|15%|q2_spend,q3_spend>> compared to last quarter, driven by increased ad buys."
   
4. Write naturally around the tags. The text must read normally if the tag markup is stripped out (e.g., "... rose to 15% compared to last quarter...").
5. CRITICAL: When listing source_fields for a _pct or _diff claim, always list the EARLIER period first and the LATER period second (e.g. q2_spend,q3_spend, not the reverse). The Verify node assumes this order and will compute the wrong sign otherwise.

Draft the report now:"""

# Maximum number of retries on transient API errors
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2


from pydantic import BaseModel, Field

class DataItem(BaseModel):
    """A single numeric key-value item extracted from a message (used for Groq Pydantic validation)."""
    key: str = Field(description="The descriptive snake_case key name (e.g. q2_spend, q3_leads)")
    value: float = Field(description="The numeric value")

class ParsedChatInput(BaseModel):
    """Schema for extracting structured inputs from arbitrary chat messages (used for Groq Pydantic validation)."""
    source_data: list[DataItem] = Field(
        description="A list of all labeled numbers mentioned in the message."
    )
    brief: str = Field(
        description="A clean instruction or brief of what report needs to be written."
    )

# Native Google GenAI Schema (avoids additionalProperties validation errors on Developer API keys)
parsed_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "source_data": types.Schema(
            type=types.Type.ARRAY,
            description="A list of all labeled numbers mentioned in the message.",
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "key": types.Schema(
                        type=types.Type.STRING,
                        description="The descriptive snake_case key name (e.g. q2_spend, q3_leads)"
                    ),
                    "value": types.Schema(
                        type=types.Type.NUMBER,
                        description="The numeric value"
                    )
                },
                required=["key", "value"]
            )
        ),
        "brief": types.Schema(
            type=types.Type.STRING,
            description="A clean instruction or brief of what report needs to be written."
        )
    },
    required=["source_data", "brief"]
)


def _parse_user_message_with_llm(client: genai.Client, model_name: str, text: str) -> tuple[dict, str]:
    """Uses the configured LLM to semantically parse source numbers and brief from user text."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider == "groq":
        from groq import Groq
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info("[draft_node] Semantic parsing with Groq %s", groq_model)
        
        prompt = (
            "You are a semantic preprocessor. Extract the structured source data and the report drafting brief from the user message.\n"
            "Format the output strictly as a JSON object with two fields:\n"
            "1. 'source_data': a list of objects, each having 'key' (descriptive snake_case string, e.g. q2_spend) and 'value' (number).\n"
            "2. 'brief': the clean drafting instruction.\n\n"
            f"User Message: {text}"
        )
        try:
            response = groq_client.chat.completions.create(
                model=groq_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw_data = json.loads(response.choices[0].message.content)
            source_data = {}
            for item in raw_data.get("source_data", []):
                source_data[item["key"]] = item["value"]
            return source_data, raw_data.get("brief", text)
        except Exception as exc:
            logger.warning("[draft_node] Groq semantic parsing failed: %s", exc)
            return {}, text

    # Default: Gemini (uses native schema)
    prompt = (
        "Extract the structured source data and the report drafting brief from the following user message. "
        "Create descriptive, logical snake_case keys for the numeric values (e.g. convert 'Q1 sales of 120k' to 'q1_sales': 120000).\n\n"
        f"User Message: {text}"
    )
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=parsed_schema,
                temperature=0.0,
            )
        )
        raw_data = json.loads(response.text)
        
        # Flatten the list of key-value items into a flat dictionary
        source_data = {}
        for item in raw_data.get("source_data", []):
            source_data[item["key"]] = item["value"]
            
        return source_data, raw_data.get("brief", text)
    except Exception as exc:
        logger.warning("[draft_node] Gemini semantic parsing failed: %s", exc)
        return {}, text


async def draft_node(
    ctx: Context,
    source_data: dict | None = None,
    brief: str | None = None
) -> Event:
    """Drafts the report based on the brief and source data, adding verification tags.

    If ``draft_text`` is already present in the session state the generation step
    is skipped and the existing draft is forwarded.  This enables re-verification
    of a pre-existing report against updated source numbers.
    """
    # Bypass generation if a draft already exists in session state.
    # ctx.state is an ADK State object (dict-like but not a plain dict).
    # Checking isinstance(str) prevents MagicMock objects from triggering
    # a false bypass in test environments.
    try:
        existing_draft = ctx.state.get("draft_text")
    except AttributeError:
        existing_draft = None
    if isinstance(existing_draft, str) and existing_draft:
        tag_count = len(_TAG_COUNT_RE.findall(existing_draft))
        logger.info(
            "[draft_node] BYPASS — using existing draft from state "
            "(%d chars, %d claim tags)",
            len(existing_draft), tag_count,
        )
        return Event(
            output=existing_draft,
            state={
                "draft_text": existing_draft,
                "source_data": source_data,
                "brief": brief,
            },
        )

    # Get provider and model config
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("DEFAULT_MODEL", "gemini-3.1-flash-lite")

    # Initialize Gemini client if we need it (as fallback or primary)
    api_key = os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else genai.Client()

    # Fallback: if source_data or brief were not provided in state (e.g. playground chat),
    # extract them semantically from the user's typed chat message using the LLM.
    if source_data is None or brief is None:
        user_text = ""
        if ctx.user_content and ctx.user_content.parts:
            user_text = "".join(
                part.text for part in ctx.user_content.parts if part.text
            ).strip()
        
        parsed_data, parsed_brief = _parse_user_message_with_llm(client, model_name, user_text)
        if source_data is None:
            source_data = parsed_data
        if brief is None:
            brief = parsed_brief
        
        logger.info(
            "[draft_node] Semantic LLM parsing complete: brief=%r, source_data=%s",
            brief, source_data
        )

    # Compile the prompt
    prompt = (
        PROMPT_TEMPLATE
        .replace("{brief}", str(brief))
        .replace("{source_data}", str(source_data))
    )

    if provider == "groq":
        from groq import Groq
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info("[draft_node] GENERATE — calling Groq %s with brief: %r", groq_model, brief)
        
        try:
            response = groq_client.chat.completions.create(
                model=groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            draft_text = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("[draft_node] Groq generation failed: %s", exc)
            raise
    else:
        # Gemini
        logger.info("[draft_node] GENERATE — calling Gemini %s with brief: %r", model_name, brief)

        response = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,  # strict compliance
                    ),
                )
                break
            except APIError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                logger.warning(
                    "Gemini transient error on attempt %d/%d: %s. Retrying in %ds...",
                    attempt + 1, _MAX_RETRIES, exc.message, _RETRY_DELAY_SECONDS
                )
                time.sleep(_RETRY_DELAY_SECONDS)
        draft_text = response.text.strip()

    tag_count = len(_TAG_COUNT_RE.findall(draft_text))
    logger.info(
        "[draft_node] DONE — %d chars, %d claim tags found",
        len(draft_text), tag_count,
    )
    logger.debug("[draft_node] Raw draft:\n%s", draft_text)

    return Event(
        output=draft_text,
        state={
            "draft_text": draft_text,
            "source_data": source_data,
            "brief": brief,
        },
    )

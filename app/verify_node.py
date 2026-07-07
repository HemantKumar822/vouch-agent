import json
import logging
import os
import re
from google.adk.agents.context import Context
from google.adk.events.event import Event
from google import genai
from google.genai import types

logger = logging.getLogger("vouch.verify")

# Regex to find the first numeric pattern (decimal, optional sign)
NUMERIC_RE = re.compile(r"[-+]?\d*\.?\d+")

# Resolution constant: the stated==0 absolute threshold (avoids unit mismatch on zero-claims)
_ZERO_STATED_ABS_THRESHOLD = 0.0001


def load_config() -> float:
    """Loads relative tolerance percentage from config/verify_config.json.

    Returns:
        Tolerance as a percentage float (e.g. 1.0 = 1%).
        Falls back to 1.0 on any read/parse error.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "verify_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return float(data.get("tolerance", 1.0))
    except Exception:
        return 1.0


def parse_numeric_value(val_str: str) -> float:
    """Robustly cleans and parses a float from a stated_value string.

    Strips currency symbols, commas, percentage signs, and surrounding
    whitespace before extracting the first numeric token.

    Raises:
        ValueError: If no numeric value can be extracted.
    """
    cleaned = val_str.replace(",", "").replace("$", "").replace("%", "").strip()
    match = NUMERIC_RE.search(cleaned)
    if not match:
        raise ValueError(f"Could not parse numeric value from '{val_str}'")
    return float(match.group(0))


def _within_tolerance(recomputed: float, stated: float, tolerance: float) -> bool:
    """Returns True if ``recomputed`` is within ``tolerance`` percent of ``stated``."""
    if stated == 0:
        # For zero-stated claims, use absolute comparison
        return abs(recomputed - stated) <= _ZERO_STATED_ABS_THRESHOLD
    return abs(recomputed - stated) / abs(stated) <= tolerance / 100.0


def check_percentage_change(
    val_a: float, val_b: float, stated: float, tolerance: float
) -> tuple[bool, float]:
    """Computes percentage change and validates against stated value.

    Always computes the canonical forward formula (val_b - val_a) / val_a * 100
    as the ``recomputed_value`` shown to the user.  A reverse-order permutation
    check is used only as a correctness guard (to tolerate LLM field ordering),
    but the recomputed value reported is always the canonical result.

    Returns:
        (is_match, canonical_recomputed_value)
    """
    canonical = (val_b - val_a) / val_a * 100.0 if val_a != 0 else 0.0

    # Check canonical permutation: (val_b - val_a) / val_a
    if val_a != 0 and _within_tolerance(canonical, stated, tolerance):
        return True, canonical

    # Check reverse permutation: (val_a - val_b) / val_b (guard for unordered LLM fields)
    if val_b != 0:
        reverse = (val_a - val_b) / val_b * 100.0
        if _within_tolerance(reverse, stated, tolerance):
            # Still report the canonical value so the user sees the correct direction
            return True, canonical

    return False, canonical


def check_difference(
    val_a: float, val_b: float, stated: float, tolerance: float
) -> tuple[bool, float]:
    """Computes difference val_b - val_a and validates against stated value.

    Like ``check_percentage_change``, uses a reverse permutation guard but
    always returns the canonical (forward) difference as ``recomputed_value``.

    Returns:
        (is_match, canonical_recomputed_value)
    """
    canonical = val_b - val_a

    if _within_tolerance(canonical, stated, tolerance):
        return True, canonical

    # Reverse permutation guard
    reverse = val_a - val_b
    if _within_tolerance(reverse, stated, tolerance):
        return True, canonical  # report canonical, not reversed

    return False, canonical


def check_sum(vals: list[float], stated: float, tolerance: float) -> tuple[bool, float]:
    """Computes the sum of fields and compares it to stated value.

    Returns:
        (is_match, recomputed_total)
    """
    total = sum(vals)
    if _within_tolerance(total, stated, tolerance):
        return True, total
    return False, total
semantic_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "results": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "label": types.Schema(type=types.Type.STRING),
                    "verification": types.Schema(type=types.Type.STRING),
                    "reason": types.Schema(type=types.Type.STRING),
                },
                required=["label", "verification", "reason"]
            )
        )
    },
    required=["results"]
)

def _semantic_llm_check(passed_claims: list[dict], draft_text: str) -> dict[str, dict]:
    """Uses the configured LLM to semantically verify mathematically passed claims.
    
    Returns a dict mapping label -> {"verification": "PASS"|"FAIL", "reason": str}
    """
    if not passed_claims:
        return {}

    claims_to_check = [{"label": c["label"], "source_fields": c["source_fields"]} for c in passed_claims]

    prompt = (
        "You are a strict semantic fact-checker. You are given a draft text and a list of numeric claims that have passed mathematical verification.\n"
        "Your job is to catch 'Semantic Hallucinations', where the LLM used a valid source field but applied it to the wrong context in the prose (e.g. using a 'q2_revenue' field to describe Q4 revenue).\n\n"
        f"Draft Text:\n{draft_text}\n\n"
        "Claims to check:\n"
        f"{json.dumps(claims_to_check, indent=2)}\n\n"
        "For each claim, return whether the semantic context in the text perfectly matches the semantic meaning of the source fields used.\n"
        "Output a JSON object containing a 'results' array. Each item in the array must have 'label', 'verification' ('PASS' or 'FAIL'), and 'reason' (if FAIL, explain why the source field semantically mismatches the text)."
    )
    
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    results_map = {}
    
    if provider == "groq":
        try:
            from groq import Groq
            groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            logger.info("[verify_node] Semantic verification with Groq %s on %d claims", groq_model, len(passed_claims))
            
            response = groq_client.chat.completions.create(
                model=groq_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw_data = json.loads(response.choices[0].message.content)
            for res in raw_data.get("results", []):
                results_map[res["label"]] = res
        except Exception as exc:
            logger.warning("[verify_node] Groq semantic verification failed: %s", exc)
            
    else:
        try:
            client = genai.Client()
            model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
            logger.info("[verify_node] Semantic verification with %s on %d claims", model_name, len(passed_claims))
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=semantic_schema,
                    temperature=0.0,
                )
            )
            raw_data = json.loads(response.text)
            for res in raw_data.get("results", []):
                results_map[res["label"]] = res
        except Exception as exc:
            logger.warning("[verify_node] Gemini semantic verification failed: %s", exc)

    return results_map


async def verify_node(ctx: Context, claims: list[dict], source_data: dict, draft_text: str = "") -> Event:
    """Verifies each extracted claim against the source numbers.

    For each claim, looks up source fields, parses the stated value, recomputes
    the expected result using the appropriate formula, and marks the claim as
    PASS or FAIL with a reason code.

    Returns an Event whose state contains:
        - ``claims``: updated list of claim dicts with verification results
        - ``summary``: dict with total_claims, passed, failed counts
    """
    tolerance = load_config()

    logger.info("[verify_node] Starting verification.")
    logger.info("  source_data parameter value: %s", source_data)
    try:
        logger.info("  ctx.state keys: %s", list(ctx.state.keys()))
        logger.info("  ctx.state['source_data']: %s", ctx.state.get("source_data"))
    except Exception as e:
        logger.info("  Could not read ctx.state: %s", e)

    passed_count = 0
    failed_count = 0
    updated_claims = []

    for claim in claims:
        claim_copy = dict(claim)

        # 1. Look up all source fields
        source_fields = claim_copy.get("source_fields", [])
        field_vals: list[float] = []
        missing_field = False

        for field in source_fields:
            if field not in source_data:
                missing_field = True
                break
            try:
                field_vals.append(float(source_data[field]))
            except (TypeError, ValueError):
                missing_field = True
                break

        if missing_field:
            claim_copy.update(
                verification="FAIL",
                recomputed_value=0.0,
                reason="missing_source_field",
            )
            failed_count += 1
            logger.info(
                "  [FAIL] %s | stated=%r | missing source field(s)",
                claim_copy["label"], claim_copy["stated_value"],
            )
            updated_claims.append(claim_copy)
            continue

        # 2. Parse stated_value
        stated_str = claim_copy.get("stated_value", "")
        try:
            stated_val = parse_numeric_value(stated_str)
        except ValueError:
            claim_copy.update(
                verification="FAIL",
                recomputed_value=0.0,
                reason="invalid_stated_value",
            )
            failed_count += 1
            logger.info(
                "  [FAIL] %s | stated=%r | cannot parse numeric value",
                claim_copy["label"], stated_str,
            )
            updated_claims.append(claim_copy)
            continue

        # 3. Recompute and compare based on label suffix
        label = claim_copy.get("label", "")

        if label.endswith("_pct"):
            if len(field_vals) < 2:
                claim_copy.update(
                    verification="FAIL",
                    recomputed_value=field_vals[0] if field_vals else 0.0,
                    reason="insufficient_source_fields_for_percentage",
                )
                failed_count += 1
                logger.info(
                    "  [FAIL] %s | stated=%r | need ≥2 fields, got %d",
                    label, claim_copy["stated_value"], len(field_vals),
                )
            else:
                passed, recomputed = check_percentage_change(
                    field_vals[0], field_vals[1], stated_val, tolerance
                )
                claim_copy["verification"] = "PASS" if passed else "FAIL"
                claim_copy["recomputed_value"] = recomputed
                verdict = "PASS" if passed else "FAIL"
                if passed:
                    passed_count += 1
                    logger.info(
                        "  [PASS] %s | stated=%r  recomputed=%.2f%%",
                        label, claim_copy["stated_value"], recomputed,
                    )
                else:
                    claim_copy["reason"] = "value_mismatch"
                    failed_count += 1
                    logger.info(
                        "  [FAIL] %s | stated=%r  recomputed=%.2f%%  (tolerance=%.1f%%)",
                        label, claim_copy["stated_value"], recomputed, tolerance,
                    )

        elif label.endswith("_diff"):
            if len(field_vals) < 2:
                claim_copy.update(
                    verification="FAIL",
                    recomputed_value=field_vals[0] if field_vals else 0.0,
                    reason="insufficient_source_fields_for_difference",
                )
                failed_count += 1
                logger.info(
                    "  [FAIL] %s | stated=%r | need ≥2 fields, got %d",
                    label, claim_copy["stated_value"], len(field_vals),
                )
            else:
                passed, recomputed = check_difference(
                    field_vals[0], field_vals[1], stated_val, tolerance
                )
                claim_copy["verification"] = "PASS" if passed else "FAIL"
                claim_copy["recomputed_value"] = recomputed
                if passed:
                    passed_count += 1
                    logger.info(
                        "  [PASS] %s | stated=%r  recomputed=%.2f",
                        label, claim_copy["stated_value"], recomputed,
                    )
                else:
                    claim_copy["reason"] = "value_mismatch"
                    failed_count += 1
                    logger.info(
                        "  [FAIL] %s | stated=%r  recomputed=%.2f  (tolerance=%.1f%%)",
                        label, claim_copy["stated_value"], recomputed, tolerance,
                    )

        elif label.endswith("_sum"):
            passed, recomputed = check_sum(field_vals, stated_val, tolerance)
            claim_copy["verification"] = "PASS" if passed else "FAIL"
            claim_copy["recomputed_value"] = recomputed
            if passed:
                passed_count += 1
                logger.info(
                    "  [PASS] %s | stated=%r  recomputed=%.2f",
                    label, claim_copy["stated_value"], recomputed,
                )
            else:
                claim_copy["reason"] = "value_mismatch"
                failed_count += 1
                logger.info(
                    "  [FAIL] %s | stated=%r  recomputed=%.2f  (tolerance=%.1f%%)",
                    label, claim_copy["stated_value"], recomputed, tolerance,
                )

        else:
            claim_copy.update(
                verification="FAIL",
                recomputed_value=0.0,
                reason="unknown_claim_type",
            )
            failed_count += 1
            logger.info(
                "  [FAIL] %s | stated=%r | unknown label suffix",
                label, claim_copy["stated_value"],
            )

        updated_claims.append(claim_copy)

    # --- Phase 2: Semantic Verification ---
    passed_claims = [c for c in updated_claims if c.get("verification") == "PASS"]
    if passed_claims and draft_text:
        semantic_results = _semantic_llm_check(passed_claims, draft_text)
        for claim in updated_claims:
            if claim.get("verification") == "PASS" and claim["label"] in semantic_results:
                s_res = semantic_results[claim["label"]]
                if s_res.get("verification") == "FAIL":
                    claim["verification"] = "FAIL"
                    claim["reason"] = s_res.get("reason", "Semantic Hallucination")
                    logger.info("  [FAIL-SEMANTIC] %s | %s", claim["label"], claim["reason"])

    # Re-calculate summary after semantic failures
    passed_count = sum(1 for c in updated_claims if c.get("verification") == "PASS")
    failed_count = len(updated_claims) - passed_count

    summary = {
        "total_claims": len(updated_claims),
        "passed": passed_count,
        "failed": failed_count,
    }
    logger.info(
        "[verify_node] Done — %d claim(s): %d PASS / %d FAIL",
        len(updated_claims), passed_count, failed_count,
    )

    return Event(
        output=updated_claims,
        state={
            "claims": updated_claims,
            "summary": summary,
        },
    )

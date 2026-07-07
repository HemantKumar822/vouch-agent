from google.adk.agents.context import Context
from google.adk.events.event import Event

async def output_node(ctx: Context, claims: list[dict], draft_text: str, summary: dict) -> Event:
    """Assembles the final output report text, replacing claim tags with verification annotations."""
    final_text = draft_text
    
    for claim in claims:
        raw_tag = claim["raw_tag"]
        stated_value = claim["stated_value"]
        verification = claim.get("verification", "FAIL")
        
        if verification == "PASS":
            replacement = stated_value
        else:
            recomputed = claim.get("recomputed_value", 0.0)
            reason = claim.get("reason", "unknown")
            
            # Format recomputed value nicely
            if isinstance(recomputed, (int, float)):
                recomputed_str = f"{recomputed:.2f}"
                # Append '%' if the stated value was represented as a percentage
                if stated_value.endswith("%"):
                    recomputed_str += "%"
            else:
                recomputed_str = str(recomputed)
                
            replacement = f"[FLAGGED: stated {stated_value}, verified value is {recomputed_str} — {reason}]"
            
        final_text = final_text.replace(raw_tag, replacement)
        
    # Append the audit summary at the bottom
    audit_block = (
        f"\n\n---\n"
        f"Claims checked: {summary.get('total_claims', 0)}\n"
        f"Passed: {summary.get('passed', 0)}\n"
        f"Flagged: {summary.get('failed', 0)}"
    )
    final_output = final_text + audit_block
    
    return Event(
        output=final_output,
        state={
            "final_output": final_output
        }
    )

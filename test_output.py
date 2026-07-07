import asyncio
from app.draft_node import draft_node
from app.extract_node import extract_node
from app.verify_node import verify_node
from app.output_node import output_node
from unittest.mock import MagicMock

async def test():
    ctx = MagicMock()
    
    source_data = {
        "q2_spend": 40000,
        "q3_spend": 46000,
        "q2_leads": 200,
        "q3_leads": 210
    }
    brief = "write a 3-sentence Q3 marketing summary"
    
    print("Step 4: Running draft_node...")
    draft_event = await draft_node(ctx, source_data=source_data, brief=brief)
    draft_text = draft_event.output
    
    print("\nStep 5: Running extract_node...")
    extract_event = await extract_node(ctx, draft_text=draft_text)
    claims = extract_event.actions.state_delta["claims"]
    
    print("\nStep 6: Running verify_node (Success Case)...")
    verify_event = await verify_node(ctx, claims=claims, source_data=source_data)
    verified_claims = verify_event.actions.state_delta["claims"]
    summary = verify_event.actions.state_delta["summary"]
    
    print("\nStep 7: Running output_node (Success Case)...")
    output_event = await output_node(ctx, claims=verified_claims, draft_text=draft_text, summary=summary)
    print("\n--- Final Output (Success Case) ---")
    print(output_event.output)
    
    print("\nStep 6: Running verify_node (Failure Case - breaking spend and leads increase claims to 25%)...")
    broken_claims = []
    for claim in claims:
        broken_claim = dict(claim)
        if "pct" in broken_claim["label"]:
            broken_claim["stated_value"] = "25%"
        broken_claims.append(broken_claim)
        
    broken_verify_event = await verify_node(ctx, claims=broken_claims, source_data=source_data)
    broken_verified_claims = broken_verify_event.actions.state_delta["claims"]
    broken_summary = broken_verify_event.actions.state_delta["summary"]
    
    print("\nStep 7: Running output_node (Failure Case)...")
    broken_output_event = await output_node(ctx, claims=broken_verified_claims, draft_text=draft_text, summary=broken_summary)
    print("\n--- Final Output (Failure Case) ---")
    print(broken_output_event.output)

if __name__ == "__main__":
    asyncio.run(test())

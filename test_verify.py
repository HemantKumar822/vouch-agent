import asyncio
from app.draft_node import draft_node
from app.extract_node import extract_node
from app.verify_node import verify_node
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
    
    print("\nStep 6 (Case A — Success Case): Running verify_node...")
    verify_event = await verify_node(ctx, claims=claims, source_data=source_data)
    verified_claims = verify_event.actions.state_delta["claims"]
    summary = verify_event.actions.state_delta["summary"]
    
    print("\n--- Verified Claims (Success Case) ---")
    for i, claim in enumerate(verified_claims, 1):
        print(f"Claim {i}:")
        print(f"  Label:        {claim['label']}")
        print(f"  Stated Value: {claim['stated_value']}")
        print(f"  Source:       {claim['source_fields']}")
        print(f"  Result:       {claim['verification']}")
        print(f"  Recomputed:   {claim['recomputed_value']:.2f}")
        if "reason" in claim:
            print(f"  Reason:       {claim['reason']}")
        print()
    print("Summary:", summary)
    
    # Check 46000 vs 40000 is actually 15%
    spend_pct = (46000 - 40000) / 40000 * 100
    print(f"\nManual Verification: 46000 vs 40000 percentage change is exactly {spend_pct:.1f}%")
    
    print("\nStep 6 (Case B — Failure Case): Intentionally breaking a claim (setting spend_increase_pct to 25%)...")
    broken_claims = []
    for claim in claims:
        broken_claim = dict(claim)
        if "pct" in broken_claim["label"]:
            broken_claim["stated_value"] = "25%"
        broken_claims.append(broken_claim)
        
    broken_verify_event = await verify_node(ctx, claims=broken_claims, source_data=source_data)
    broken_verified_claims = broken_verify_event.actions.state_delta["claims"]
    broken_summary = broken_verify_event.actions.state_delta["summary"]
    
    print("\n--- Verified Claims (Failure Case) ---")
    for i, claim in enumerate(broken_verified_claims, 1):
        print(f"Claim {i}:")
        print(f"  Label:        {claim['label']}")
        print(f"  Stated Value: {claim['stated_value']}")
        print(f"  Result:       {claim['verification']}")
        print(f"  Recomputed:   {claim['recomputed_value']:.2f}")
        if "reason" in claim:
            print(f"  Reason:       {claim['reason']}")
        print()
    print("Broken Summary:", broken_summary)

if __name__ == "__main__":
    asyncio.run(test())

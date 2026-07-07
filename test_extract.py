import asyncio
from app.draft_node import draft_node
from app.extract_node import extract_node
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
    draft_text_clean = extract_event.actions.state_delta["draft_text_clean"]
    
    print("\n--- Cleaned Draft Text ---")
    print(draft_text_clean)
    
    print("\n--- Extracted Claims ---")
    for i, claim in enumerate(claims, 1):
        print(f"Claim {i}:")
        print(f"  Raw Tag:      {claim['raw_tag']}")
        print(f"  Label:        {claim['label']}")
        print(f"  Stated Value: {claim['stated_value']}")
        print(f"  Source:       {claim['source_fields']}")
        print()
        
    print(f"Total claims extracted: {len(claims)}")

if __name__ == "__main__":
    asyncio.run(test())

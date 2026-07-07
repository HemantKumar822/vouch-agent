import asyncio
from app.draft_node import draft_node
from unittest.mock import MagicMock

async def test():
    # Mock the Context object
    ctx = MagicMock()
    
    source_data = {
        "q2_spend": 40000,
        "q3_spend": 46000,
        "q2_leads": 200,
        "q3_leads": 210
    }
    brief = "write a 3-sentence Q3 marketing summary"
    
    print("Running draft_node...")
    event = await draft_node(ctx, source_data=source_data, brief=brief)
    print("\n--- Event Output ---")
    print(event.output)

if __name__ == "__main__":
    asyncio.run(test())

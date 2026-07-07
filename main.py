import asyncio
import json
from google.adk.runners import InMemoryRunner
from google.genai import types
from app.agent import app

async def run_workflow(source_data: dict, brief: str, draft_text: str = None) -> tuple[str, str]:
    # Initialize the memory runner
    runner = InMemoryRunner(app=app)
    
    # Create session with initial state populated
    state = {
        "source_data": source_data,
        "brief": brief
    }
    if draft_text:
        state["draft_text"] = draft_text

    session = await runner.session_service.create_session(
        app_name="app",
        user_id="demo_user",
        state=state
    )
    
    # Run the workflow
    print(f"Starting Vouch workflow for brief: '{brief}'...")
    async for event in runner.run_async(
        user_id="demo_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
    ):
        if event.node_info.name:
            print(f"  [Node: {event.node_info.name}] finished.")
            
    # Retrieve final session state
    final_session = await runner.session_service.get_session(
        app_name="app",
        user_id="demo_user",
        session_id=session.id
    )
    
    return (
        final_session.state.get("final_output", "No output generated."),
        final_session.state.get("draft_text", "")
    )

async def main():
    # Test data
    source_data_success = {
        "q2_spend": 40000,
        "q3_spend": 46000,
        "q2_leads": 200,
        "q3_leads": 210
    }
    brief = "write a 3-sentence Q3 marketing summary"
    
    print("=" * 60)
    print(" CASE A: RUNNING VOUCH (SUCCESS CASE - ALL CLAIMS CORRECT)")
    print("=" * 60)
    print(f"Source Data: {json.dumps(source_data_success, indent=2)}")
    
    output_success, draft_text = await run_workflow(source_data_success, brief)
    print("\n--- Final Output ---")
    print(output_success)
    print("\n")
    
    print("=" * 60)
    print(" CASE B: RUNNING VOUCH (FAILURE CASE - VERIFYING OLD DRAFT AGAINST NEW NUMBERS)")
    print("=" * 60)
    # We change q3_spend to 50000 (which breaks the 15% increase claim and the 6,000 difference claim in Case A's draft)
    source_data_failure = {
        "q2_spend": 40000,
        "q3_spend": 50000,  # Changed from 46000, making spend increase 25% instead of 15%
        "q2_leads": 200,
        "q3_leads": 210
    }
    print(f"Source Data (with modified numbers): {json.dumps(source_data_failure, indent=2)}")
    print("Verifying the previous draft against the new source numbers...")
    
    output_failure, _ = await run_workflow(source_data_failure, brief, draft_text=draft_text)
    print("\n--- Final Output ---")
    print(output_failure)
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from main import run_workflow

async def main():
    success_data = {"q2_spend": 40000, "q3_spend": 46000, "q2_leads": 200, "q3_leads": 210}
    failure_data = {"q2_spend": 40000, "q3_spend": 50000, "q2_leads": 200, "q3_leads": 210}
    brief = "write a 3-sentence Q3 marketing summary"

    print("--- DEMO 1: ALL CLAIMS PASS ---")
    out_pass, draft = await run_workflow(success_data, brief)
    print(out_pass)

    print("\n--- DEMO 2: CLAIMS FLAGGED ---")
    out_fail, _ = await run_workflow(failure_data, brief, draft_text=draft)
    print(out_fail)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys
import os

# sys.path hacking removed - run via poetry run python ...

from kodiak.core.tools.definitions.network import NmapTool, NmapArgs

async def run_scan_simulation(agent_id: str, target: str):
    print(f"[{agent_id}] Requesting Nmap Scan for {target}...")
    tool = NmapTool()
    
    # Using REAL executor (Local)
    # Target scanme.nmap.org on port 80 for a quick, polite test
    result = await tool.run(NmapArgs(target=target, ports="80", fast_mode=True))
        
    print(f"[{agent_id}] Result: Success={result.success}, Cached={result.data.get('cached', False)}")
    if result.output:
        # Show a bit more output to prove it ran
        print(f"[{agent_id}] Output Preview:\n{result.output[:300]}...")
    elif result.error:
         print(f"[{agent_id}] Error: {result.error}")

async def main():
    print("--- Starting REAL Hive Mind Verification (Nmap) ---")
    
    target = "scanme.nmap.org"
    
    # Simulate two agents requesting the same scan simultaneously
    # Agent A starts first
    task1 = asyncio.create_task(run_scan_simulation("Agent_A", target))
    
    # Agent B starts 0.5s later (should catch the lock from Agent A and wait for its result)
    await asyncio.sleep(0.5)
    task2 = asyncio.create_task(run_scan_simulation("Agent_B", target))
    
    await asyncio.gather(task1, task2)
    print("--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Test Runner for All Web Agents

This script runs all available agents with a simple test task
and generates a comparison report.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

AGENTS = [
    # "browser-use-app",
    # "seeact-app", 
    # "crawl4ai-app",
    # "skyvern-app",
    # "nanobrowser-app",
    "open-manus-app",
]

TEST_TASK = "Open google.com"


def run_agent(agent_name: str, agent_dir: Path) -> Dict:
    """Run a single agent and capture results."""
    print(f"\n{'='*60}")
    print(f"Running: {agent_name}")
    print(f"{'='*60}")
    
    main_py = agent_dir / "main.py"
    
    if not main_py.exists():
        print(f"❌ {main_py} not found")
        return {
            "agent": agent_name,
            "status": "ERROR",
            "error": "main.py not found",
        }
    
    try:
        # Run agent
        result = subprocess.run(
            [sys.executable, str(main_py)],
            cwd=str(agent_dir),
            capture_output=True,
            text=True,
            timeout=300,
            env={
                "AGENT_TASK": TEST_TASK,
                "OPENAI_API_KEY": subprocess.os.environ.get("OPENAI_API_KEY", ""),
                "OPENAI_MODEL": subprocess.os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            }
        )
        
        print("STDOUT:")
        print(result.stdout[:500])
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr[:500])
        
        # Check for result file
        result_dir = agent_dir / "result"
        latest_result = None
        
        if result_dir.exists():
            json_files = sorted(result_dir.glob("*.json"), reverse=True)
            if json_files:
                latest_result = json_files[0]
                with open(latest_result) as f:
                    data = json.load(f)
                    return {
                        "agent": agent_name,
                        "status": "SUCCESS" if data.get("success") else "FAILED",
                        "run_time": data.get("run_time_seconds"),
                        "error": data.get("error"),
                        "result_file": str(latest_result),
                    }
        
        return {
            "agent": agent_name,
            "status": "COMPLETED",
            "return_code": result.returncode,
        }
    
    except subprocess.TimeoutExpired:
        return {
            "agent": agent_name,
            "status": "TIMEOUT",
            "error": "Execution timeout (300s)",
        }
    
    except Exception as e:
        return {
            "agent": agent_name,
            "status": "ERROR",
            "error": str(e),
        }


def main():
    """Run all agents and generate report."""
    print("="*60)
    print("WEB AGENTS TEST RUNNER")
    print("="*60)
    print(f"\nTest Task: {TEST_TASK}")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    # Verify API key
    if not subprocess.os.environ.get("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not set")
        print("   Run: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)
    
    # Run all agents
    results = []
    crawlers_path = Path(__file__).parent
    
    for agent_name in AGENTS:
        agent_dir = crawlers_path / agent_name
        
        if not agent_dir.exists():
            print(f"⚠ Skipping {agent_name} - directory not found")
            continue
        
        result = run_agent(agent_name, agent_dir)
        results.append(result)
    
    # Generate report
    print(f"\n{'='*60}")
    print("TEST REPORT")
    print(f"{'='*60}\n")
    
    print(f"{'Agent':<20} {'Status':<15} {'Time (s)':<15} {'Error':<20}")
    print("-" * 70)
    
    for result in results:
        agent = result["agent"][:20]
        status = result["status"]
        run_time = f"{result.get('run_time', 'N/A'):.2f}" if "run_time" in result else "N/A"
        error = result.get("error", "")[:20] if result.get("error") else "None"
        
        print(f"{agent:<20} {status:<15} {run_time:<15} {error:<20}")
    
    # Summary
    print("\n" + "="*60)
    successful = sum(1 for r in results if r["status"] == "SUCCESS")
    total = len(results)
    print(f"Summary: {successful}/{total} agents completed successfully\n")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_task": TEST_TASK,
        "total_agents": total,
        "successful_agents": successful,
        "results": results,
    }
    
    report_path = crawlers_path / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"Report saved to: {report_path}\n")


if __name__ == "__main__":
    main()

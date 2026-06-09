"""
SeeAct Agent - UI-Grounded Web Task Automation

SeeAct uses visual grounding and language models to interpret UI elements
and perform complex web interactions. This implementation provides a simple
pipeline for running web automation tasks.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

try:
    from seeact import Agent as SeeActAgent
    from seeact.llm import ChatOpenAI as SeeActChatOpenAI
except ImportError:
    print("Warning: seeact not installed. Install with: pip install seeact")
    SeeActAgent = None
    SeeActChatOpenAI = None

AGENT_RUN_TIMEOUT_SECONDS = 600
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def _build_llm():
    """Build LLM client for SeeAct agent."""
    api_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY).strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    
    model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
    
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except ImportError:
        raise ImportError("openai package required: pip install openai")


def _to_jsonable(value):
    """Convert any value to JSON-serializable format."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        try:
            return _to_jsonable(vars(value))
        except Exception:
            return str(value)
    return str(value)


def _save_run_result(task, result, run_time_seconds, error=None, timed_out=False):
    """Save execution result to JSON file."""
    result_dir = Path(__file__).resolve().parent / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": str(uuid4()),
        "agent": "SeeAct",
        "task": task,
        "success": error is None and not timed_out,
        "timed_out": timed_out,
        "error": error,
        "run_time_seconds": round(run_time_seconds, 6),
        "result_preview": str(result)[:500] if result else None,
    }

    filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + ".json"
    output_path = result_dir / filename

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Saved result to: {output_path}")


async def run_task(task_description: str = "Navigate to google.com"):
    """
    Run a web task using SeeAct agent.
    
    Args:
        task_description: Natural language description of the task
    """
    if SeeActAgent is None:
        print("ERROR: SeeAct not installed. Install with: pip install seeact")
        return
    
    print(f"Starting SeeAct agent with task: {task_description}")
    
    try:
        llm_client = _build_llm()
        
        # Create async browser context for SeeAct
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            # Initialize SeeAct agent
            agent = SeeActAgent(
                page=page,
                llm_client=llm_client,
                model="gpt-4o",
            )
            
            run_start = perf_counter()
            result = None
            error = None
            timed_out = False
            
            try:
                # Run the task
                result = await asyncio.wait_for(
                    agent.run(task_description),
                    timeout=AGENT_RUN_TIMEOUT_SECONDS
                )
                print(f"Task completed successfully: {result}")
                
            except asyncio.TimeoutError:
                timed_out = True
                error = f"Timeout after {AGENT_RUN_TIMEOUT_SECONDS}s"
                print(f"ERROR: {error}")
                
            except Exception as e:
                error = str(e)
                print(f"ERROR: {error}")
            
            finally:
                run_time_seconds = perf_counter() - run_start
                await browser.close()
                
                _save_run_result(
                    task_description,
                    result,
                    run_time_seconds,
                    error=error,
                    timed_out=timed_out
                )
    
    except Exception as e:
        print(f"Failed to initialize SeeAct: {e}")
        _save_run_result(task_description, None, 0, error=str(e))


def main():
    """Main entry point for SeeAct agent."""
    # Get task from command line args, environment, or use default
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = os.getenv(
            "AGENT_TASK",
            "Open google.com and check that the page loaded"
        )
    
    print("=" * 60)
    print("SeeAct Web Agent")
    print("=" * 60)
    print(f"Task: {task}")
    print("=" * 60)
    
    asyncio.run(run_task(task))


if __name__ == "__main__":
    main()

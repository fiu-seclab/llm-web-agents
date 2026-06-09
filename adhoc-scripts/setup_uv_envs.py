#!/usr/bin/env python3
"""
UV Environment Setup for All Web Agents

This script sets up isolated UV environments for each web agent.
UV is a fast, modern replacement for pip and venv combined.

Installation:
    pip install uv

Then run:
    python setup_uv_envs.py
"""

import subprocess
import sys
from pathlib import Path

AGENTS = {
    "browser-use-app": {
        "description": "Browser-Use: Open-source, highly customizable browser agent",
        "python_version": "3.11",
    },
    "seeact-app": {
        "description": "SeeAct: UI-grounded agent with visual understanding",
        "python_version": "3.11",
    },
    "crawl4ai-app": {
        "description": "Crawl4AI: Lightweight, fast web crawler with AI",
        "python_version": "3.11",
    },
    "nanobrowser-app": {
        "description": "NanoBrowser: Lightweight browser navigation agent",
        "python_version": "3.11",
    },
}


def check_uv_installed():
    """Check if UV is installed."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
        )
        print(f"✓ UV installed: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("❌ UV not found. Install with: pip install uv")
        return False


def setup_agent_env(agent_name: str, agent_info: dict) -> bool:
    """Setup UV environment for a single agent."""
    print(f"\n{'='*60}")
    print(f"Setting up: {agent_name.upper()}")
    print(f"{'='*60}")
    print(agent_info["description"])
    print(f"Python version: {agent_info['python_version']}")
    
    agent_path = Path(__file__).parent / agent_name
    
    if not agent_path.exists():
        print(f"⚠ Path not found: {agent_path}")
        return False
    
    print(f"Path: {agent_path}")
    
    # Create .python-version file if it doesn't exist
    python_version_file = agent_path / ".python-version"
    if not python_version_file.exists():
        print(f"Creating .python-version file...")
        python_version_file.write_text(agent_info["python_version"] + "\n")
        print(f"✓ Created .python-version")
    else:
        print(f"✓ .python-version exists")
    
    # Run uv sync
    print(f"\nSyncing dependencies with UV...")
    try:
        # Clean up any existing venv if needed
        venv_path = agent_path / ".venv"
        if venv_path.exists():
            print(f"  Removing existing .venv...")
            import shutil
            shutil.rmtree(venv_path)
        
        result = subprocess.run(
            ["uv", "sync"],
            cwd=str(agent_path),
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print(f"✓ UV sync completed successfully")
            
            # Show venv path
            venv_path = agent_path / ".venv"
            if venv_path.exists():
                print(f"✓ Virtual environment: {venv_path}")
                print(f"  Activate with: source {venv_path}/bin/activate")
            
            return True
        else:
            print(f"❌ UV sync failed:")
            print(result.stderr)
            return False
            
    except FileNotFoundError:
        print("❌ Command not found: uv")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main setup flow."""
    print("="*60)
    print("UV ENVIRONMENT SETUP FOR WEB AGENTS")
    print("="*60)
    print("\nThis script sets up isolated Python environments")
    print("using UV for each web agent.\n")
    
    # Check UV installation
    if not check_uv_installed():
        print("\nPlease install UV first:")
        print("  pip install uv")
        sys.exit(1)
    
    # Ask what to install
    print(f"\n{'='*60}")
    print("Available agents:")
    print(f"{'='*60}")
    
    agent_list = list(AGENTS.keys())
    for i, agent_name in enumerate(agent_list, 1):
        print(f"  {i}. {agent_name}")
    
    print("\nOptions:")
    print("  a) Setup all environments")
    print("  n) Setup new agents (seeact, crawl4ai)")
    print("  q) Quit")
    
    choice = input("\nSelect option (a/n/q): ").strip().lower()
    
    agents_to_setup = []
    if choice == "a":
        agents_to_setup = agent_list
    elif choice == "n":
        agents_to_setup = ["seeact-app", "crawl4ai-app"]
    elif choice == "q":
        print("Exiting...")
        return
    else:
        print("Invalid choice")
        return
    
    # Setup selected agents
    results = {}
    for agent_name in agents_to_setup:
        if agent_name in AGENTS:
            results[agent_name] = setup_agent_env(agent_name, AGENTS[agent_name])
    
    # Summary
    print(f"\n{'='*60}")
    print("SETUP SUMMARY")
    print(f"{'='*60}\n")
    
    successful = sum(1 for v in results.values() if v)
    total = len(results)
    
    for agent_name, success in results.items():
        status = "✓" if success else "❌"
        print(f"{status} {agent_name}")
    
    print(f"\nTotal: {successful}/{total} environments ready\n")
    
    # Next steps
    print(f"{'='*60}")
    print("NEXT STEPS")
    print(f"{'='*60}\n")
    
    if successful > 0:
        print("1. Verify Python version in each environment:")
        for agent_name in agents_to_setup:
            if results.get(agent_name):
                agent_path = Path(__file__).parent / agent_name
                print(f"   source {agent_path}/.venv/bin/activate")
                print(f"   python --version")
        
        print("\n2. Set API key:")
        print("   export OPENAI_API_KEY='sk-...'")
        
        print("\n3. Run an agent:")
        for agent_name in agents_to_setup:
            if results.get(agent_name):
                agent_path = Path(__file__).parent / agent_name
                print(f"   cd {agent_path}")
                print(f"   uv run python main.py")
                break
        
        print("\n4. Or run all agents:")
        print("   python test_all_agents.py")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()

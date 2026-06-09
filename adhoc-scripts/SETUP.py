#!/usr/bin/env python3
"""
Setup and Installation Guide for All Web Agents

This script helps set up all 6 web agents for CAPTCHA research.
Run this to verify your environment and install dependencies.
"""

import subprocess
import sys
from pathlib import Path

AGENTS = {
    "browser-use": {
        "path": "browser-use-app",
        "description": "Browser-Use: Open-source, highly customizable browser agent",
        "deps": ["browser-use>=0.11.9"],
    },
    "skyvern": {
        "path": "skyvern-app",  # Assumed to exist or be linked
        "description": "Skyvern: Proprietary cloud agent with built-in solving",
        "deps": ["skyvern"],
    },
    "nanobrowser": {
        "path": "nanobrowser-app",
        "description": "NanoBrowser: Lightweight browser navigation agent",
        "deps": [],  # Custom setup
    },
    "openmanus": {
        "path": "open-manus-app",
        "description": "OpenManus: Vision-based web automation",
        "deps": ["openmanus"],
    },
    "seeact": {
        "path": "seeact-app",
        "description": "SeeAct: UI-grounded agent with visual understanding",
        "deps": ["seeact>=0.1.0", "playwright>=1.40.0"],
    },
    "crawl4ai": {
        "path": "crawl4ai-app",
        "description": "Crawl4AI: Lightweight, fast web crawler with AI",
        "deps": ["crawl4ai>=0.4.0"],
    },
}

COMMON_DEPS = [
    "openai>=1.0.0",
    "python-dotenv>=1.0.0",
]


def check_python_version():
    """Verify Python version."""
    if sys.version_info < (3, 11):
        print(f"⚠ Python 3.11+ recommended (found {sys.version.split()[0]})")
        print("  Current Python may work, but prefer Python 3.11+")
    else:
        print(f"✓ Python {sys.version.split()[0]} OK")
    return True


def check_uv_installed():
    """Check if UV is installed."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
        )
        print(f"✓ UV installed: {result.stdout.strip()}\n")
        print("💡 Tip: Use UV for faster setup!")
        print("   Run: python setup_uv_envs.py")
        return True
    except FileNotFoundError:
        print("⚠ UV not installed (optional but recommended)")
        print("  Install with: pip install uv")
        print("  Learn more: UV_SETUP.md\n")
        return False


def check_openai_api_key():
    """Check if OpenAI API key is set."""
    import os
    if os.getenv("OPENAI_API_KEY"):
        print("✓ OPENAI_API_KEY is set")
        return True
    print("⚠ OPENAI_API_KEY not set. Set it before running agents:")
    print("  export OPENAI_API_KEY='your-key-here'")
    return False


def install_agent(agent_name: str, agent_info: dict) -> bool:
    """Install a single agent."""
    print(f"\n{'='*60}")
    print(f"Setting up: {agent_name.upper()}")
    print(f"{'='*60}")
    print(agent_info["description"])
    
    agent_path = Path(__file__).parent / agent_info["path"]
    
    if not agent_path.exists():
        print(f"⚠ Path not found: {agent_path}")
        print(f"  Skipping {agent_name}")
        return False
    
    print(f"Path: {agent_path}")
    
    # Install dependencies
    all_deps = agent_info["deps"] + COMMON_DEPS
    
    if all_deps:
        print(f"Installing dependencies...")
        for dep in all_deps:
            print(f"  - {dep}")
        
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install"] + all_deps,
                check=True,
                capture_output=True,
            )
            print(f"✓ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            return False
    
    return True


def verify_setup():
    """Verify all agents are accessible."""
    print(f"\n{'='*60}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*60}")
    
    crawlers_path = Path(__file__).parent
    available_agents = []
    
    for agent_name, agent_info in AGENTS.items():
        agent_path = crawlers_path / agent_info["path"]
        main_py = agent_path / "main.py"
        
        if main_py.exists():
            print(f"✓ {agent_name:15} - main.py found")
            available_agents.append(agent_name)
        else:
            print(f"⚠ {agent_name:15} - main.py not found")
    
    print(f"\n{'='*60}")
    print(f"Total agents configured: {len(available_agents)}/6")
    print(f"Ready agents: {', '.join(available_agents)}")
    
    return len(available_agents)


def main():
    """Main setup flow."""
    print("="*60)
    print("WEB AGENTS SETUP WIZARD")
    print("="*60)
    print("\nThis script will help you set up all web agents for")
    print("CAPTCHA detection and bypassing research.\n")
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    check_openai_api_key()
    
    # Ask what to install
    print(f"\n{'='*60}")
    print("INSTALLATION OPTIONS")
    print(f"{'='*60}")
    print("\nAvailable agents:")
    for i, (agent_name, agent_info) in enumerate(AGENTS.items(), 1):
        print(f"  {i}. {agent_name:15} - {agent_info['description']}")
    
    print("\nOptions:")
    print("  a) Install all agents")
    print("  s) Install SeeAct and Crawl4AI only (new agents)")
    print("  q) Quit")
    
    choice = input("\nSelect option (a/s/q): ").strip().lower()
    
    agents_to_install = []
    if choice == "a":
        agents_to_install = list(AGENTS.keys())
    elif choice == "s":
        agents_to_install = ["seeact", "crawl4ai"]
    elif choice == "q":
        print("Exiting...")
        return
    else:
        print("Invalid choice")
        return
    
    # Install selected agents
    installed_count = 0
    for agent_name in agents_to_install:
        if agent_name in AGENTS:
            if install_agent(agent_name, AGENTS[agent_name]):
                installed_count += 1
    
    # Verify
    verify_setup()
    
    print(f"\n{'='*60}")
    print("NEXT STEPS")
    print(f"{'='*60}")
    print("\n1. Set your OpenAI API key:")
    print("   export OPENAI_API_KEY='sk-...'")
    print("\n2. Run a test task:")
    print("   cd seeact-app && python main.py")
    print("   cd crawl4ai-app && python main.py")
    print("\n3. Check results in result/ directories")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()

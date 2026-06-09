#!/bin/bash
#
# QUICK START: UV Environment Setup
# 
# This script sets up UV environments for SeeAct and Crawl4AI agents
# Run from the crawlers/ directory
#

set -e

echo "=========================================="
echo "UV Environment Setup for Web Agents"
echo "=========================================="
echo ""

# Check UV installation
if ! command -v uv &> /dev/null; then
    echo "❌ UV not found. Installing..."
    pip install uv
fi

echo "✓ UV version:"
uv --version
echo ""

# Function to setup agent
setup_agent() {
    local agent_name=$1
    local agent_dir=$2
    
    echo "Setting up $agent_name..."
    cd "$agent_dir"
    
    # Clean up any existing venv
    if [ -d ".venv" ]; then
        echo "  Removing existing .venv..."
        rm -rf .venv
    fi
    
    echo "  Running: uv sync"
    uv sync
    
    echo "✓ $agent_name ready"
    echo "  Activate: source .venv/bin/activate"
    echo "  Run: uv run python main.py"
    cd ..
    echo ""
}

# Setup SeeAct
setup_agent "SeeAct" "seeact-app"

# Setup Crawl4AI
setup_agent "Crawl4AI" "crawl4ai-app"

echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Export API key:"
echo "     export OPENAI_API_KEY='sk-...'"
echo ""
echo "  2. Activate an agent environment:"
echo "     cd seeact-app && source .venv/bin/activate"
echo ""
echo "  3. Run the agent:"
echo "     python main.py"
echo ""
echo "  4. Or run all tests:"
echo "     python test_all_agents.py"
echo ""

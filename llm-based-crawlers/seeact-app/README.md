# SeeAct - UI-Grounded Web Agent

**SeeAct** is a UI-grounded agent framework that uses visual grounding and language models to interpret and interact with web interfaces. It's particularly effective for complex UI interactions and visual CAPTCHA challenges.

## Features

- **Visual Grounding**: Interprets UI elements from screenshots
- **Multi-modal Understanding**: Combines vision and language models
- **Complex Interactions**: Handles sophisticated workflows
- **UI Element Detection**: Accurate bounding box detection for web elements

## Setup

### Prerequisites

- Python 3.11+
- OpenAI API key
- UV (fast Python package manager) - [Install UV](https://docs.astral.sh/uv/getting-started/)

### Installation with UV (Recommended)

```bash
# Install UV first (if not already installed)
pip install uv

# Create UV environment (automatically uses Python 3.11)
uv sync

# Or manually with specific Python version
uv venv --python 3.11
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync
```

### Installation with pip

```bash
# Ensure Python 3.11+
python --version

# Install dependencies
pip install -e .

# Or manually
pip install seeact playwright openai python-dotenv
```

### Configuration

Set environment variables:

```bash
export OPENAI_API_KEY="your-api-key-here"
export OPENAI_MODEL="gpt-4o"  # or gpt-4o-mini for faster/cheaper
export AGENT_TASK="Your task description here"
```

## Usage

### Basic Example: Navigate to Google

```bash
python main.py
```

### Custom Task via Environment Variable

```bash
export AGENT_TASK="Open google.com and search for 'web agents'"
python main.py
```

### Programmatic Usage

```python
import asyncio
from main import run_task

async def example():
    await run_task("Navigate to example.com and extract the title")

asyncio.run(example())
```

## Task Examples

### CAPTCHA Testing

```bash
export AGENT_TASK="Navigate to the login page, identify the CAPTCHA, and solve it"
python main.py
```

### Form Submission

```bash
export AGENT_TASK="Fill out a contact form with provided information and submit"
python main.py
```

### Data Extraction

```bash
export AGENT_TASK="Extract all product titles and prices from the page"
python main.py
```

## Output

Results are saved in `result/` directory as JSON files with:

- Timestamp and run ID
- Task description
- Success/failure status
- Execution time
- Any errors encountered

## Architecture

### Components

1. **LLM Backend**: GPT-4o for reasoning and planning
2. **Browser Controller**: Playwright for browser automation
3. **Visual Grounding**: Screenshot-based UI understanding
4. **Action Space**: Click, type, scroll, navigate actions

### Workflow

1. Receive task description
2. Take screenshot of current page
3. Use LLM to interpret UI and plan actions
4. Execute planned actions
5. Repeat until task completion or timeout

## Performance Characteristics

- **Strength**: Visual element detection, complex multi-step workflows
- **Best For**: Image-based CAPTCHAs, complex UI navigation
- **Timeout**: 600 seconds (configurable)
- **Cost**: ~$0.02-0.10 per task (depends on steps)

## Troubleshooting

### playwright not found
```bash
playwright install chromium
```

### OpenAI API errors
- Check API key is valid
- Check account has credits
- Check rate limits

### Browser not launching
```bash
# Ensure headless mode is disabled for custom tasks
# Update Playwright
pip install --upgrade playwright
```

## References

- [SeeAct GitHub](https://github.com/OSU-NLP-Group/SeeAct)
- [SeeAct Paper](https://arxiv.org/abs/2403.12886)

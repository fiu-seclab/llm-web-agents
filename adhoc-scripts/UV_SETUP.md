# UV Environment Setup Guide

This guide explains how to set up isolated Python environments for each web agent using UV.

## Why UV?

UV is a modern, fast replacement for pip and venv combined:
- ⚡ 10-100x faster than pip
- 🔒 Creates isolated environments automatically
- 📦 Manages dependencies and Python versions
- 🔄 Reproducible builds with `uv.lock`

## Installation

### Install UV

```bash
# Option 1: With pip (recommended)
pip install uv

# Option 2: With brew (macOS)
brew install uv

# Option 3: With curl
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version
```

## Setup for All Agents

### Automatic Setup (Recommended)

```bash
cd crawlers/
python setup_uv_envs.py
# Select 'a' for all or 'n' for new agents
```

### Manual Setup by Agent

#### SeeAct

```bash
cd crawlers/seeact-app

# Create and sync environment
uv sync

# Activate
source .venv/bin/activate

# Run
python main.py
```

#### Crawl4AI

```bash
cd crawlers/crawl4ai-app

# Create and sync environment
uv sync

# Activate
source .venv/bin/activate

# Run
python main.py
```

#### Browser-Use

```bash
cd crawlers/browser-use-app

# Create and sync environment
uv sync

# Activate
source .venv/bin/activate

# Run
python main.py
```

## UV Commands Reference

### Create/Update Environment

```bash
# Create .venv and install dependencies
uv sync

# Sync with specific Python version
uv sync --python 3.11

# Upgrade all dependencies
uv sync --upgrade
```

### Run Commands Without Activation

```bash
# Run Python directly
uv run python main.py

# Run a script
uv run python script.py

# Run with specific Python version
uv run --python 3.11 python main.py
```

### Add Dependencies

```bash
# Add a package
uv pip install package-name

# Add multiple packages
uv pip install package1 package2

# Add with version constraint
uv pip install "package>=1.0.0"
```

### Environment Management

```bash
# Show Python version
uv python list

# Show installed packages
uv pip list

# Show environment info
uv venv

# Remove environment
rm -rf .venv
```

## Environment Structure

After running `uv sync`, each agent has:

```
agent-app/
├── .python-version      # Specifies Python 3.11
├── pyproject.toml       # Dependencies and metadata
├── uv.lock              # Locked dependency versions (if using uv pip freeze)
└── .venv/               # Virtual environment (created by uv sync)
    ├── bin/
    │   ├── python
    │   ├── pip
    │   └── ... (other executables)
    ├── lib/
    │   └── python3.11/site-packages/
    └── pyvenv.cfg
```

## Troubleshooting

### Issue: "uv: command not found"

```bash
# Install UV
pip install uv

# Or use full path
/path/to/.local/bin/uv sync
```

### Issue: Python 3.11 not found

```bash
# UV will try to download it automatically
# Or install system-wide
# macOS:
brew install python@3.11

# Ubuntu/Debian:
sudo apt install python3.11

# Then specify version
uv sync --python 3.11
```

### Issue: "Version 3.11 not available"

```bash
# Check available Python versions
uv python list

# Download specific version
uv python install 3.11

# Then use it
uv sync --python 3.11
```

### Issue: Dependency conflicts

```bash
# Clear cache and resync
rm -rf .venv uv.lock
uv sync

# Or try different approach
uv sync --python 3.11 --fresh
```

### Issue: "Permission denied" on activation

```bash
# Make activation script executable
chmod +x .venv/bin/activate

# Or use uv run instead
uv run python main.py
```

## Quick Comparison: pip vs UV

| Task | pip | uv |
|------|-----|-----|
| Install dependencies | `pip install -r requirements.txt` | `uv sync` |
| Run script | `python script.py` | `uv run python script.py` |
| Add package | `pip install pkg` | `uv pip install pkg` |
| Create venv | `python -m venv .venv` | `uv venv` |
| Activate | `source .venv/bin/activate` | Same (venv compatible) |
| Show packages | `pip list` | `uv pip list` |

## With Multiple Agents

```bash
# Setup all agents
for agent in seeact-app crawl4ai-app browser-use-app; do
  cd $agent
  uv sync
  cd ..
done

# Run all in parallel
for agent in seeact-app crawl4ai-app browser-use-app; do
  (cd $agent && uv run python main.py &)
done
wait
```

## CI/CD Integration

```yaml
# Example GitHub Actions
- name: Setup Python with UV
  run: |
    pip install uv
    uv sync --python 3.11

- name: Run tests
  run: uv run pytest
```

## References

- [UV Documentation](https://docs.astral.sh/uv/)
- [UV on GitHub](https://github.com/astral-sh/uv)
- [pyproject.toml Guide](https://docs.astral.sh/uv/concepts/projects/)

---

**Next Step**: Run `python setup_uv_envs.py` to automatically set up all agents!

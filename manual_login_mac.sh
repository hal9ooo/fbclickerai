#!/bin/bash
# Manual Login for FBClicker on M1 Mac
# Use this for the first login to save session cookies

cd "$(dirname "$0")"

# Activate the Mac-specific virtual environment
source .venv_mac/bin/activate

# Set PYTHONPATH
export PYTHONPATH="$(pwd)"

# Override Docker paths with local directories
export DATA_DIR="$(pwd)/data"
export SCREENSHOTS_DIR="$(pwd)/data/screenshots"
export SESSIONS_DIR="$(pwd)/data/sessions"

# Create directories if they don't exist
mkdir -p "$DATA_DIR" "$SCREENSHOTS_DIR" "$SESSIONS_DIR"

# Run in visible (non-headless) mode for manual login
export HEADLESS=false

echo "🔐 FBClicker - Manual Login (M1 Mac)"
echo "📁 Session will be saved to: $SESSIONS_DIR"
echo ""

python manual_login.py "$@"

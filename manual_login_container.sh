#!/bin/bash
# Manual Facebook login INSIDE the container, against the running Xvfb display.
# Run this from a terminal inside the noVNC desktop (or directly with
# DISPLAY=:99 bash manual_login_container.sh).
#
# Saves facebook_session.json + fingerprint.json to the same path the bot
# loads on startup, so no transfer/copy is needed.
set -e

cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)"

# Use the container's X display (set by start_vnc.sh)
export DISPLAY="${DISPLAY:-:99}"

# Local data paths (same defaults as the bot)
export DATA_DIR="${DATA_DIR:-$(pwd)/data}"
export SCREENSHOTS_DIR="${SCREENSHOTS_DIR:-$(pwd)/data/screenshots}"
export SESSIONS_DIR="${SESSIONS_DIR:-$(pwd)/data/sessions}"
mkdir -p "$DATA_DIR" "$SCREENSHOTS_DIR" "$SESSIONS_DIR"

# Force visible browser
export HEADLESS=false

echo "🔐 FBClicker - Manual Login (in-container, X display=$DISPLAY)"
echo "📁 Session will be saved to: $SESSIONS_DIR/facebook_session.json"
echo "👤 Fingerprint will be saved to: $SESSIONS_DIR/fingerprint.json"
echo ""

# Reuse the existing script (it uses StealthBrowser, same as the bot)
exec python -m src.manual_login

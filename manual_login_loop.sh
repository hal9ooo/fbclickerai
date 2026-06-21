#!/bin/bash
# Wrapper that runs the manual login script in a loop.
# After each attempt (success, error, or quit) the user can
# press ENTER to retry without needing to restart xterm or
# the container. Press Ctrl+C to exit.
set -u

cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)"
export DISPLAY="${DISPLAY:-:99}"
export DATA_DIR="${DATA_DIR:-$(pwd)/data}"
export SCREENSHOTS_DIR="${SCREENSHOTS_DIR:-$(pwd)/data/screenshots}"
export SESSIONS_DIR="${SESSIONS_DIR:-$(pwd)/data/sessions}"
mkdir -p "$DATA_DIR" "$SCREENSHOTS_DIR" "$SESSIONS_DIR"
export HEADLESS=false

while true; do
    # Sanitize: kill any leftover Chromium / Playwright processes from a
    # previous attempt (crashed browser, defunct zombies, etc).
    pkill -9 -f "ms-playwright/chromium" 2>/dev/null || true
    pkill -9 -f "chrome_crashpad" 2>/dev/null || true
    pkill -9 -f "playwright/driver" 2>/dev/null || true
    sleep 1

    clear
    echo "================================================================"
    echo "  FBClicker - Manual Login (in-container)"
    echo "  Session:  $SESSIONS_DIR/facebook_session.json"
    echo "================================================================"
    if [ -f "$SESSIONS_DIR/facebook_session.json" ]; then
        age=$(stat -c %Y "$SESSIONS_DIR/facebook_session.json")
        now=$(date +%s)
        days=$(( (now - age) / 86400 ))
        echo "  Existing session: $days day(s) old"
    fi
    echo "  Starting Chromium + login flow..."
    echo "================================================================"
    echo ""

    ./manual_login_container.sh
    rc=$?

    echo ""
    echo "================================================================"
    if [ "$rc" -eq 0 ]; then
        echo "  Session saved. Verify it from the server with:"
        echo "      docker cp verify_session.py fbclicker:/app/  (first time only)"
        echo "      docker exec fbclicker python /app/verify_session.py"
    else
        echo "  Login attempt finished with errors (rc=$rc)."
    fi
    echo "================================================================"
    echo ""
    echo "  Press ENTER to start a new manual login"
    echo "  Press Ctrl+C to close this terminal"
    echo ""
    # Read a single line; if the user hits Ctrl+C, the loop exits
    read -r _ || break
done

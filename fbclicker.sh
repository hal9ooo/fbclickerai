#!/bin/bash
# FBClicker - one-stop interactive menu for every common operation.
#
# Usage:  ./fbclicker.sh
#
# Covers: SSH tunnel, manual login, session verify, bot start/stop, logs, rebuild.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && ppwd 2>/dev/null || cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

COMPOSE_BASE=(docker compose -f docker-compose.yml)
COMPOSE_MANUAL=(docker compose --profile manual -f docker-compose.yml)
SESSION_FILE="data/sessions/facebook_session.json"
VNC_PASSWORD="${VNC_PASSWORD:-fbclicker}"

# ---------- helpers ----------

pick_host_ip() {
    if [[ -n "${REMOTE_HOST:-}" ]]; then echo "$REMOTE_HOST"; return; fi
    if [[ -n "${SSH_CONNECTION:-}" ]]; then echo "${SSH_CONNECTION%% *}"; return; fi
    local hi
    hi=$(hostname -I 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i !~ /^127\./) {print $i; exit}}')
    [[ -n "$hi" ]] && { echo "$hi"; return; }
    hostname
}

service_running() {
    docker ps --format '{{.Names}}' | grep -q "^$1$"
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -q "^$1$"
}

session_age() {
    if [[ ! -f "$SESSION_FILE" ]]; then echo "no session"; return; fi
    python3 -c "
import os, time
p='$SESSION_FILE'
age=int(time.time()-os.path.getmtime(p))
if age < 60: print(f'{age} seconds ago')
elif age < 3600: print(f'{age//60} minutes ago')
else: print(f'{age//3600} hours ago')
"
}

session_valid() {
    if [[ ! -f "$SESSION_FILE" ]]; then return 1; fi
    python3 -c "
import json
try:
    with open('$SESSION_FILE') as f: d=json.load(f)
except Exception: exit(1)
names={c['name'] for c in d.get('cookies',[])}
exit(0 if ('c_user' in names and 'xs' in names) else 1)
"
}

wait_manual() {
    local tries=30
    echo -n "Waiting for noVNC to be ready"
    for _ in $(seq 1 $tries); do
        if docker exec fbclicker-manual bash -c "echo > /dev/tcp/127.0.0.1/6080" 2>/dev/null; then
            echo " up"; return 0
        fi
        echo -n .
        sleep 1
    done
    echo " TIMEOUT"; return 1
}

print_header() {
    local host_ip session_status bot_status manual_status
    host_ip=$(pick_host_ip)
    if session_valid 2>/dev/null; then
        session_status="OK ($(session_age))"
    elif [[ -f "$SESSION_FILE" ]]; then
        session_status="EXPIRED ($(session_age))"
    else
        session_status="MISSING"
    fi
    service_running fbclicker        && bot_status="RUNNING"     || bot_status="stopped"
    service_running fbclicker-manual && manual_status="RUNNING"  || manual_status="stopped"

    echo "================================================================"
    echo "  FBClicker - control panel"
    echo "================================================================"
    echo "  Project:   $PROJECT_DIR"
    echo "  Host IP:   $host_ip"
    echo "  Session:   $session_status"
    echo "  Bot:       $bot_status"
    echo "  Manual:    $manual_status"
    echo "================================================================"
}

ssh_tunnel_hint() {
    local host_ip user="${REMOTE_USER:-${USER:-vscode}}"
    host_ip=$(pick_host_ip)
    echo "  On your Windows machine (PowerShell or cmd):"
    echo "      ssh -L 6080:localhost:6080 ${user}@${host_ip}"
    echo "  Then open:  http://localhost:6080/vnc.html"
    echo "  Password:  ${VNC_PASSWORD}"
}

# ---------- actions ----------

do_ssh_tunnel() {
    print_header
    echo ""
    echo "SSH tunnel command for noVNC:"
    echo ""
    ssh_tunnel_hint
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_manual_login() {
    print_header
    echo ""
    if service_running fbclicker; then
        echo "  NOTE: the bot container is running. Stop it first if you want"
        echo "        to avoid resource contention (option 4)."
    fi
    echo ""
    if container_exists fbclicker-manual; then
        if service_running fbclicker-manual; then
            echo "  fbclicker-manual already running, restarting xterm to be safe..."
            docker exec fbclicker-manual bash -c 'pkill -f "xterm" 2>/dev/null; pkill -f "manual_login" 2>/dev/null; sleep 1; pkill -9 -f "ms-playwright/chromium" 2>/dev/null; pkill -9 -f "chrome_crashpad" 2>/dev/null; true' >/dev/null 2>&1
        else
            "${COMPOSE_MANUAL[@]}" rm -f fbclicker-manual >/dev/null
        fi
    fi
    echo "  Starting fbclicker-manual container..."
    "${COMPOSE_MANUAL[@]}" up -d fbclicker-manual
    wait_manual
    echo ""
    echo "  noVNC is up. Connect with:"
    echo ""
    ssh_tunnel_hint
    echo ""
    echo "  In the desktop: a terminal opens automatically with"
    echo "  manual_login_loop.sh already running. Just log into Facebook"
    echo "  in the Chromium window that appears, then press ENTER in the"
    echo "  terminal. To redo the login, press ENTER again (the loop will"
    echo "  clean up the old browser and start fresh)."
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_verify() {
    print_header
    echo ""
    if [[ ! -f "$SESSION_FILE" ]]; then
        echo "  No session file yet: $SESSION_FILE"
        echo "  Run option 1 first."
        return 0
    fi
    if service_running fbclicker; then
        echo "  Verifying inside the running bot container..."
        docker cp "$PROJECT_DIR/verify_session.py" fbclicker:/app/verify_session.py 2>/dev/null || true
        docker exec fbclicker python /app/verify_session.py || true
    elif service_running fbclicker-manual; then
        echo "  Verifying inside the manual container..."
        docker cp "$PROJECT_DIR/verify_session.py" fbclicker-manual:/app/verify_session.py 2>/dev/null || true
        docker exec fbclicker-manual python /app/verify_session.py || true
    else
        echo "  No container running. Use option 1 or 4 first."
    fi
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_start_bot() {
    print_header
    echo ""
    if ! session_valid 2>/dev/null; then
        echo "  WARNING: session is missing or expired. The bot will likely fail."
        echo "  Run option 1 first to log in."
        echo ""
        read -rp "Continue anyway? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || return 0
    fi
    echo "  Starting bot container..."
    "${COMPOSE_BASE[@]}" up -d fbclicker
    sleep 2
    echo ""
    echo "  Bot started. Tail logs with option 7."
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_stop_all() {
    print_header
    echo ""
    read -rp "  Stop bot AND manual containers? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        "${COMPOSE_BASE[@]}" down
        "${COMPOSE_MANUAL[@]}" down
        echo "  All stopped."
    else
        echo "  Cancelled."
    fi
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_logs() {
    print_header
    echo ""
    echo "  1) bot logs (fbclicker)"
    echo "  2) manual logs (fbclicker-manual)"
    echo "  3) bot, last 100 lines (no follow)"
    read -rp "  Choice [1-3]: " c
    case "${c:-1}" in
        1) "${COMPOSE_BASE[@]}" logs -f fbclicker ;;
        2) "${COMPOSE_MANUAL[@]}" logs -f fbclicker-manual ;;
        3) "${COMPOSE_BASE[@]}" logs --tail=100 fbclicker
           read -rp "Press ENTER to continue..." _ ;;
        *) echo "  Invalid." ;;
    esac
}

do_rebuild() {
    print_header
    echo ""
    read -rp "  Rebuild both images (fbclicker + fbclicker-manual)? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        "${COMPOSE_BASE[@]}" build
        "${COMPOSE_MANUAL[@]}" build
        echo "  Done."
    else
        echo "  Cancelled."
    fi
    echo ""
    read -rp "Press ENTER to continue..." _
}

do_session_info() {
    print_header
    echo ""
    if [[ ! -f "$SESSION_FILE" ]]; then
        echo "  No session file at $SESSION_FILE"
    else
        echo "  Path:     $SESSION_FILE"
        echo "  Size:     $(stat -c %s "$SESSION_FILE") bytes"
        echo "  Age:      $(session_age)"
        echo "  Cookies:  $(python3 -c "import json; print(len(json.load(open('$SESSION_FILE')).get('cookies',[])))")"
        if session_valid 2>/dev/null; then
            echo "  Status:   VALID (c_user + xs present)"
        else
            echo "  Status:   INVALID / EXPIRED"
        fi
    fi
    echo ""
    read -rp "Press ENTER to continue..." _
}

# ---------- main loop ----------

while true; do
    print_header
    echo ""
    echo "  1) Show SSH tunnel command (for noVNC)"
    echo "  2) Start manual login (opens noVNC, xterm auto-launched)"
    echo "  3) Verify saved session"
    echo "  4) Start bot (production)"
    echo "  5) Stop all containers"
    echo "  6) Show logs"
    echo "  7) Rebuild images"
    echo "  8) Session info"
    echo ""
    echo "  q) Quit"
    echo ""
    read -rp "  Choice: " choice
    case "$choice" in
        1) do_ssh_tunnel ;;
        2) do_manual_login ;;
        3) do_verify ;;
        4) do_start_bot ;;
        5) do_stop_all ;;
        6) do_logs ;;
        7) do_rebuild ;;
        8) do_session_info ;;
        q|Q) echo "  Bye."; exit 0 ;;
        *)   echo "  Invalid choice."; sleep 1 ;;
    esac
done

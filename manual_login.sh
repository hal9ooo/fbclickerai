#!/bin/bash
# FBClicker - Manual Login orchestrator
#
# One-shot script that:
#   1. (re)builds the image if needed
#   2. starts the fbclicker-manual container (Xvfb + noVNC) on port 6080
#   3. detects the best host IP to give to the user
#   4. prints a ready-to-run SSH tunnel command for Windows
#   5. tails the container logs so you can see when the desktop is ready
#
# Usage:
#   ./manual_login.sh                  # use defaults
#   ./manual_login.sh --rebuild        # force image rebuild
#   ./manual_login.sh --no-tunnel      # skip auto-tunnel (you're already on the host)
#   ./manual_login.sh --user vscode    # remote SSH user for the printed tunnel command
#
# Run this from the project root (where docker-compose.yml lives).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

REBUILD=0
AUTO_TUNNEL=1
FOLLOW_LOGS=0
REMOTE_USER="${REMOTE_USER:-${USER:-vscode}}"
REMOTE_HOST_HINT="${REMOTE_HOST:-}"
NOVNC_PORT=6080
COMPOSE=(docker compose --profile manual -f docker-compose.yml)

# ---------- args ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rebuild)       REBUILD=1 ;;
        --no-tunnel)     AUTO_TUNNEL=0 ;;
        --follow-logs)   FOLLOW_LOGS=1 ;;
        --user)          REMOTE_USER="$2"; shift ;;
        --host)          REMOTE_HOST_HINT="$2"; shift ;;
        -h|--help)
            sed -n '2,18p' "$0"
            exit 0 ;;
        *)
            echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
    shift
done

# ---------- helpers ----------
pick_host_ip() {
    # 1) explicit override wins
    [[ -n "$REMOTE_HOST_HINT" ]] && { echo "$REMOTE_HOST_HINT"; return; }

    # 2) the IP that the SSH connection actually came from (when invoked via ssh user@host)
    local ssh_ip
    ssh_ip="${SSH_CONNECTION:-}"
    if [[ -n "$ssh_ip" ]]; then
        echo "${ssh_ip%% *}"
        return
    fi

    # 3) hostname -I: first non-loopback, routable
    local hi
    hi=$(hostname -I 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i !~ /^127\./) {print $i; exit}}')
    if [[ -n "$hi" ]]; then echo "$hi"; return; fi

    # 4) last resort
    hostname
}

is_port_open() {
    local port="$1" host="${2:-127.0.0.1}"
    (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1
}

ensure_container() {
    if [[ "$REBUILD" -eq 1 ]]; then
        echo ">>> Rebuilding image..."
        "${COMPOSE[@]}" build fbclicker-manual
    fi

    # If a previous manual container is up but unhealthy, recycle it
    if docker ps -a --format '{{.Names}}' | grep -q '^fbclicker-manual$'; then
        if ! docker ps --format '{{.Names}}' | grep -q '^fbclicker-manual$'; then
            echo ">>> Removing stopped fbclicker-manual container"
            "${COMPOSE[@]}" rm -f fbclicker-manual >/dev/null
        fi
    fi

    if ! docker ps --format '{{.Names}}' | grep -q '^fbclicker-manual$'; then
        echo ">>> Starting fbclicker-manual container"
        "${COMPOSE[@]}" up -d fbclicker-manual
    else
        echo ">>> fbclicker-manual already running"
    fi
}

wait_noVNC() {
    local tries=30
    echo -n ">>> Waiting for noVNC to be ready"
    for _ in $(seq 1 $tries); do
        if is_port_open "$NOVNC_PORT" 127.0.0.1; then
            echo " up"
            return 0
        fi
        echo -n .
        sleep 1
    done
    echo " TIMEOUT"
    return 1
}

read_password() {
    # Read from running container; fall back to file
    docker exec fbclicker-manual cat /tmp/fbclicker_vnc_passwd 2>/dev/null \
        || cat /tmp/fbclicker_vnc_passwd 2>/dev/null \
        || echo "(unknown - check container logs)"
}

read_password_source() {
    # Detect whether VNC_PASSWORD is configured in the project .env file.
    # The value in the .env is what start_vnc.sh (run inside the container)
    # uses to decide between fixed and auto-generated.
    local envfile="$PROJECT_DIR/.env"
    if [[ -f "$envfile" ]] && grep -E '^[[:space:]]*VNC_PASSWORD[[:space:]]*=' "$envfile" >/dev/null; then
        local val
        val=$(grep -E '^[[:space:]]*VNC_PASSWORD[[:space:]]*=' "$envfile" \
              | head -1 | sed -E 's/^[[:space:]]*VNC_PASSWORD[[:space:]]*=[[:space:]]*//' \
              | sed -E "s/^['\"]|['\"]$//g" | tr -d '\r')
        if [[ -n "$val" ]]; then echo "fixed:'$val'"; else echo "auto"; fi
    else
        echo "auto"
    fi
}

# ---------- main ----------
ensure_container
wait_noVNC

HOST_IP=$(pick_host_ip)
VNC_PASS=$(read_password)
VNC_SRC=$(read_password_source)

echo ""
echo "============================================================"
echo "  FBClicker noVNC desktop is ready"
echo "============================================================"
echo "  noVNC URL:     http://localhost:${NOVNC_PORT}/vnc.html"
echo "  Direct IP URL: http://${HOST_IP}:${NOVNC_PORT}/vnc.html"
echo "  noVNC port:    ${NOVNC_PORT}"
echo "  VNC password:  ${VNC_PASS}  (${VNC_SRC})"
echo "  Host IP:       ${HOST_IP}"
echo "============================================================"
echo ""
echo "  >>> From your Windows machine, run this in PowerShell or cmd:"
echo ""
echo "      ssh -L ${NOVNC_PORT}:localhost:${NOVNC_PORT} ${REMOTE_USER}@${HOST_IP}"
echo ""
echo "  Then open:   http://localhost:${NOVNC_PORT}/vnc.html"
echo "  Password:    ${VNC_PASS}"
echo ""
echo "  >>> Inside the noVNC desktop:"
echo "      1. Right-click the desktop -> Terminal (xterm)"
echo "      2. Run:"
echo "             cd /app && ./manual_login_container.sh"
echo "      3. Log into Facebook in the Chromium window that opens"
echo "      4. Press ENTER in the xterm when done (session is saved)"
echo ""
echo "  >>> When finished:"
echo "      docker compose --profile manual -f docker-compose.yml down"
echo "      docker compose up -d fbclicker"
echo "============================================================"
echo ""
echo "Tailing container logs (Ctrl-C to detach; container keeps running):"
echo "----------------------------------------------------------------"
if [[ "$FOLLOW_LOGS" -eq 1 ]]; then
    "${COMPOSE[@]}" logs -f fbclicker-manual
else
    "${COMPOSE[@]}" logs --tail=20 fbclicker-manual
    echo ""
    echo "(container still running; attach logs with: ${COMPOSE[*]} logs -f fbclicker-manual)"
fi

#!/bin/bash
# Start Xvfb + fluxbox + x11vnc + noVNC inside the container.
# Exposes a browser-based desktop at http://<host>:6080/vnc.html
# Used to perform the manual Facebook login (CAPTCHA, 2FA) without
# transferring cookies between machines.
set -e

DISPLAY_NUM=${DISPLAY_NUM:-99}
VNC_PORT=${VNC_PORT:-5900}
NOVNC_PORT=${NOVNC_PORT:-6080}
VNC_DISPLAY=":${DISPLAY_NUM}"
VNC_PASSWD_FILE=/tmp/fbclicker_vnc_passwd
LOG_DIR=/tmp/fbclicker_vnc_logs
PID_DIR=/tmp/fbclicker_vnc_pids

mkdir -p "$LOG_DIR" "$PID_DIR"

# Pick a password if none provided, and store it for the user to read
# Pick a password and store it using x11vnc's own format (DES-encrypted)
if [ -n "$VNC_PASSWORD" ]; then
    EFFECTIVE_PASSWORD="$VNC_PASSWORD"
else
    EFFECTIVE_PASSWORD=$(cat /proc/sys/kernel/random/uuid 2>/dev/null | cut -c1-8 || echo "fbclicker")
fi
x11vnc -storepasswd "$EFFECTIVE_PASSWORD" "$VNC_PASSWD_FILE" >/dev/null 2>&1
chmod 600 "$VNC_PASSWD_FILE"
# Keep the env var consistent for any process that needs to display the password
export VNC_PASSWORD="$EFFECTIVE_PASSWORD"

# Helper: is pid in pidfile still running?
is_running() {
    local pidfile="$1"
    [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

wait_port() {
    local port="$1" name="$2" tries=50
    for _ in $(seq 1 $tries); do
        if nc -z localhost "$port" 2>/dev/null; then
            echo "[vnc] $name listening on $port"
            return 0
        fi
        sleep 0.2
    done
    echo "[vnc] WARNING: $name did not start listening on $port"
    return 1
}

# 1. Xvfb
if ! is_running "$PID_DIR/xvfb.pid"; then
    echo "[vnc] Starting Xvfb on $VNC_DISPLAY"
    Xvfb "$VNC_DISPLAY" -screen 0 1920x1080x24 -ac \
        > "$LOG_DIR/xvfb.log" 2>&1 &
    echo $! > "$PID_DIR/xvfb.pid"
    sleep 1
fi

# 2. Window manager (fluxbox) so xterm/playwright windows have chrome
if ! is_running "$PID_DIR/fluxbox.pid"; then
    echo "[vnc] Starting fluxbox"
    DISPLAY="$VNC_DISPLAY" fluxbox \
        > "$LOG_DIR/fluxbox.log" 2>&1 &
    echo $! > "$PID_DIR/fluxbox.pid"
    sleep 1
fi

# 3. x11vnc
if ! is_running "$PID_DIR/x11vnc.pid"; then
    echo "[vnc] Starting x11vnc on port $VNC_PORT"
    x11vnc -display "$VNC_DISPLAY" \
        -rfbport "$VNC_PORT" \
        -forever \
        -shared \
        -rfbauth "$VNC_PASSWD_FILE" \
        -noxrecord \
        -noxfixes \
        -noxdamage \
        > "$LOG_DIR/x11vnc.log" 2>&1 &
    echo $! > "$PID_DIR/x11vnc.pid"
    wait_port "$VNC_PORT" x11vnc
fi

# 4. noVNC (websockify bridge)
if ! is_running "$PID_DIR/novnc.pid"; then
    echo "[vnc] Starting noVNC on port $NOVNC_PORT"
    websockify --web /opt/novnc "$NOVNC_PORT" "localhost:$VNC_PORT" \
        > "$LOG_DIR/novnc.log" 2>&1 &
    echo $! > "$PID_DIR/novnc.pid"
    wait_port "$NOVNC_PORT" noVNC
fi

# 5. Auto-launch xterm with manual_login_container.sh running
# Set AUTO_XTERM=0 in the container env to disable.
if [[ "${AUTO_XTERM:-1}" -eq 1 ]] && ! is_running "$PID_DIR/xterm.pid"; then
    echo "[vnc] Auto-launching xterm with manual_login_container.sh"
    # Wait a bit for the WM to register
    sleep 1
    DISPLAY="$VNC_DISPLAY" xterm \
        -fa Monospace -fs 11 \
        -geometry 130x42+30+30 \
        -title "FBClicker - manual login" \
        -bg "#101418" -fg "#d0d7de" \
        -e "bash -c 'cd /app && exec ./manual_login_loop.sh'" \
        > "$LOG_DIR/xterm.log" 2>&1 &
    echo $! > "$PID_DIR/xterm.pid"
    # Bring xterm to the foreground so the user can see output and reach the
    # "Press ENTER" prompt after logging into Facebook.
    sleep 1
    DISPLAY="$VNC_DISPLAY" xdotool search --name "FBClicker - manual login" \
        windowactivate --sync 2>/dev/null || true
fi

echo ""
echo "============================================================"
echo "  FBClicker noVNC desktop is up"
echo "============================================================"
echo "  noVNC URL:  http://localhost:${NOVNC_PORT}/vnc.html"
echo "  VNC port:   ${VNC_PORT}  (raw VNC, e.g. for TightVNC)"
echo "  Password:   ${VNC_PASSWORD}"
echo "============================================================"
echo "  Open the URL from your browser (tunnel the port if remote):"
echo "      ssh -L ${NOVNC_PORT}:localhost:${NOVNC_PORT} user@host"
echo "  A terminal with manual_login_container.sh is auto-launched."
echo "  Just log into Facebook in the Chromium window that opens,"
echo "  then press ENTER in the xterm to save the session."
echo "============================================================"

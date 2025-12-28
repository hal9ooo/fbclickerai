#!/bin/bash
set -e

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x800x24 &
export DISPLAY=:99
sleep 2

# Start Window Manager (Fluxbox)
echo "Starting Fluxbox..."
fluxbox &
sleep 1

# Start VNC Server
# -forever: keep listening after client disconnects
# -nopw: no password required (safe for local network)
# -shared: allow multiple clients
# -bg: run in background
echo "Starting x11vnc..."
x11vnc -display :99 -forever -nopw -shared -bg

echo "Starting manual_login.py in xterm..."
# Run the Python script inside xterm so user can interact with it
xterm -fa 'Monospace' -fs 12 -geometry 100x30 -e python manual_login.py

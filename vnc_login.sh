#!/bin/bash
set -e

# Cleanup existing processes if any
echo "Cleaning up existing VNC/Xvfb processes..."
pkill -9 Xvfb || true
pkill -9 fluxbox || true
pkill -9 x11vnc || true
pkill -9 xterm || true
rm -f /tmp/.X99-lock || true

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
sleep 2

# Set Italian keyboard layout
echo "Setting keyboard layout to Italian..."
setxkbmap it

# Start Window Manager (Fluxbox)
echo "Starting Fluxbox..."
fluxbox &
sleep 1

# Start x11vnc on a fixed port
echo "Starting x11vnc on port 5900..."
x11vnc -display :99 -forever -nopw -shared -bg -rfbport 5900

echo "Starting manual_login.py in centered xterm..."
echo "DISPLAY is: $DISPLAY"
# Use the virtual environment's python and keep the window open if it crashes/ends
# Adding -hold for extra safety
xterm -hold -fa 'Monospace' -fs 12 -geometry 140x45+250+100 -e bash -l -c "./venv/bin/python3 manual_login.py; echo; echo '[Processo terminato. Premi INVIO per chiudere questa finestra]'; read"

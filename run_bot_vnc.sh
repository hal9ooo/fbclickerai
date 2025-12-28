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
echo "Starting x11vnc..."
x11vnc -display :99 -forever -nopw -shared -bg

echo "Starting FBClicker Bot (Visual Mode)..."
# Run the main bot script
# Ensure HEADLESS=false is set in environment for this to show the browser
python src/main.py

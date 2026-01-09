#!/bin/bash
# Start the gallery server in the background
python -u -m src.gallery_server &

# Start the main bot
exec python -m src.main

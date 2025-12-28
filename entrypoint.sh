#!/bin/bash
# Start the gallery server in the background
python -m src.gallery_server &

# Start the main bot
exec python -m src.main

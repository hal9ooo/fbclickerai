#!/bin/bash
# FBClicker - Unified Refresh Session Script
# This script automates the process of:
# 1. Stopping the production bot
# 2. Starting the VNC manual login environment
# 3. Restarting the production bot with the new session

set -e

cd "$(dirname "$0")"

echo "🛑 Fermata del bot in produzione (se attivo)..."
docker compose down

echo ""
echo "🔐 Avvio dell'ambiente di login manuale via VNC..."
echo "----------------------------------------------------"
echo "1. Apri il tuo client VNC e connettiti a: $(hostname -I | awk '{print $1}'):5900"
echo "2. Effettua il login su Facebook nel browser che apparirà."
echo "3. Quando hai finito, premi INVIO nella finestra xterm (o chiudi il browser)."
echo "----------------------------------------------------"
echo ""

# Run the existing VNC login script
# This script will block until the user finishes the login in xterm
./vnc_login.sh

echo ""
echo "✅ Sessione salvata! Riavvio del bot in produzione..."
docker compose up -d

echo ""
echo "🚀 Bot riavviato! Controlla i log con:"
echo "docker compose logs -f"

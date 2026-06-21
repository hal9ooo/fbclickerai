#!/bin/bash
# Server-side helper: install the public key you copied from Windows,
# and verify the SSH server accepts key-based auth.
#
# Usage (run on the SERVER, via SSH or local console):
#   ./setup_ssh_key.sh "ssh-ed25519 AAAA...fbclicker-windows-vscode"
#
# If you prefer: just paste the key when prompted.

set -euo pipefail

PUBKEY_LINE="${1:-}"
AUTH_KEYS="${HOME}/.ssh/authorized_keys"
SSH_DIR="${HOME}/.ssh"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
touch "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

install_key() {
    local key="$1"
    # Idempotency: skip if the same key line is already there
    if grep -Fqx "$key" "$AUTH_KEYS" 2>/dev/null; then
        echo "[ssh] key already installed, skipping"
    else
        echo "$key" >> "$AUTH_KEYS"
        echo "[ssh] key appended to $AUTH_KEYS"
    fi
}

if [ -n "$PUBKEY_LINE" ]; then
    install_key "$PUBKEY_LINE"
else
    echo "Paste your public key (one line, starts with 'ssh-ed25519 ...'):"
    read -r PUBKEY_LINE
    [ -z "$PUBKEY_LINE" ] && { echo "No key provided, aborting." >&2; exit 1; }
    install_key "$PUBKEY_LINE"
fi

# Verify sshd config
SSHD_CFG=/etc/ssh/sshd_config
echo ""
echo ">>> Checking sshd config..."
if [ -r "$SSHD_CFG" ]; then
    for opt in PubkeyAuthentication AuthorizedKeysFile; do
        if grep -E "^[#[:space:]]*${opt}\b" "$SSHD_CFG" >/dev/null; then
            grep -E "^[#[:space:]]*${opt}\b" "$SSHD_CFG" | sed 's/^/  /'
        else
            echo "  $opt  (default)"
        fi
    done
else
    echo "  (cannot read $SSHD_CFG, skipping)"
fi

# Test
echo ""
echo ">>> Test from your Windows machine:"
echo "    ssh -i \$env:USERPROFILE\\.ssh\\id_ed25519 $USER@$(hostname -I | awk '{print $1}') 'whoami && echo OK'"
echo ""
echo "If you have an alias 'fbclicker' set up, just:"
echo "    ssh fbclicker 'whoami && echo OK'"

# FBClicker — Runbook

Everything you need to operate FBClicker on the Linux server. Hand this
file to an agent (or read it yourself) to remember the steps.

---

## TL;DR (cheat sheet)

```bash
# On the server (via SSH):
./fbclicker.sh                        # interactive menu (recommended)
./manual_login.sh                     # one-shot: starts manual-login container, prints tunnel command

# On Windows (PowerShell or cmd), every time you want to use noVNC:
ssh -L 6080:localhost:6080 vscode@<server-ip>
# then open http://localhost:6080/vnc.html  (password: fbclicker)

# In the noVNC desktop:
#   - An xterm opens automatically with manual_login_loop.sh already running
#   - A Chromium window opens with facebook.com login
#   - Log into Facebook (CAPTCHA / 2FA if asked)
#   - Switch back to xterm (Alt+Tab) and press ENTER
#   - Session is saved to data/sessions/facebook_session.json
#   - To redo the login, press ENTER again (loop restarts Chromium)
#   - Ctrl+C closes xterm
```

---

## Environment

- **Server**: Linux box with Docker + Docker Compose, accessed via SSH
- **Workstation**: Windows 10/11 with built-in OpenSSH (`ssh -V`)
- **Project dir on server**: `~/progetti/dev/fbclicker/` (or wherever you cloned it)
- **Container profiles**:
  - `fbclicker` — the bot (production, headless)
  - `fbclicker-manual` (profile `manual`) — desktop with noVNC for manual login

---

## First-time setup (one time per Windows machine)

If you have not set up the SSH config / key yet:

```powershell
# On Windows, in PowerShell, from the project directory
.\setup_ssh_tunnel.ps1 -KeyOnly
#   - creates %USERPROFILE%\.ssh\config with Host 'fbclicker'
#   - generates ed25519 key, prints the public key

# On the server, paste the printed public key:
./setup_ssh_key.sh
#   - appends the key to ~/.ssh/authorized_keys
```

After this you can do just `ssh fbclicker` and the tunnel is opened
automatically. If you also want key-only auth (no password prompt), the
last line of `setup_ssh_tunnel.ps1` output tells you the exact command.

---

## Procedure A — First login / re-login (session expired)

1. **On the server** (via SSH):
   ```bash
   cd ~/progetti/dev/fbclicker
   ./fbclicker.sh
   ```
   Or directly:
   ```bash
   ./manual_login.sh
   ```
   This:
   - Detects the server IP
   - (Re)starts the `fbclicker-manual` container if not running
   - Prints the SSH tunnel command and the noVNC password (`fbclicker`)

2. **On Windows**, open a new PowerShell/cmd window and run the printed command:
   ```bash
   ssh -L 6080:localhost:6080 vscode@<server-ip>
   ```
   Keep this terminal open while you work.

3. **In any browser** open: `http://localhost:6080/vnc.html`
   - A yellow banner says "Credentials are required"
   - A modal "Credentials" pops up → enter password `fbclicker` → click "Send credentials"
   - The noVNC desktop appears

4. **In the noVNC desktop**:
   - A terminal (xterm) opens automatically with the message banner
   - A Chromium window opens with `facebook.com` login
   - Log into Facebook (CAPTCHA / 2FA if asked) — this is the **only** manual step
   - Switch back to the xterm (Alt+Tab or click in the taskbar)
   - Press **ENTER** when prompted → session is saved
   - You see: "Session saved. Verify it from the server..."
   - Press **ENTER** again to redo the login (the loop kills the old Chromium and restarts a clean one)
   - **Ctrl+C** closes xterm when done

5. **Stop the manual container and start the bot**:
   ```bash
   # On the server
   docker compose --profile manual -f docker-compose.yml down
   docker compose up -d fbclicker
   ```
   Or in the menu: option 5 (stop all), then option 4 (start bot).

---

## Procedure B — Daily operation

The bot runs headless. To check on it:

```bash
# Status of both containers
docker ps --format 'table {{.Names}}\t{{.Status}}'

# Tail logs
docker compose -f docker-compose.yml logs -f fbclicker

# Restart the bot
docker compose -f docker-compose.yml restart fbclicker
```

To interact with the bot (Telegram commands), use the Telegram bot
configured in `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`).

---

## Procedure C — Verify the session is valid

Before starting the bot, or to debug a "session not recognized" error:

```bash
# Option A: use the menu (option 3) which copies verify_session.py into the container
./fbclicker.sh

# Option B: manually
docker cp verify_session.py fbclicker:/app/    # one-time, then
docker exec fbclicker python /app/verify_session.py
```

Expected output for a healthy session:
```
[..]   cookies:     8 total, names=[..., 'c_user', ..., 'xs', ...]
[OK]   cookie 'c_user' present
[OK]   cookie 'xs' present
[OK]   facebook.com reachable without login redirect
[OK]   /me reachable (session alive)
[OK]   group page loaded with member-requests content
[OK]   session looks healthy
```

Exit codes:
- `0` — healthy
- `1` — no session file (run manual login)
- `2` — auth cookies missing in the file (re-login)
- `3` — Facebook redirected to /login (session expired, re-login)
- `4`/`5` — technical error (check logs)

---

## Key files

| Path | What it is |
|---|---|
| `docker-compose.yml` | `fbclicker` (bot) + `fbclicker-manual` (profile) services |
| `Dockerfile` | Image with Python, Playwright, Tesseract, xvfb, x11vnc, fluxbox, xdotool, noVNC |
| `start_vnc.sh` | Launches Xvfb + fluxbox + x11vnc + noVNC + auto-xterm |
| `manual_login_container.sh` | One-shot manual login (lives inside the container) |
| `manual_login_loop.sh` | Loop wrapper that retries without restarting the terminal |
| `src/manual_login.py` | Python entry point for the manual login flow |
| `src/browser/stealth_browser.py` | The same StealthBrowser the bot uses — kept consistent on purpose |
| `verify_session.py` | Loads the saved session and confirms it works against facebook.com |
| `data/sessions/facebook_session.json` | **The** session file (Playwright storage_state) |
| `data/sessions/fingerprint.json` | Persistent fingerprint (UA, viewport, WebGL) |
| `data/screenshots/` | Bot screenshots, used for Telegram previews |
| `.env` | All credentials and runtime config (NEVER commit) |

---

## Troubleshooting

### "noVNC asks for a password, mine doesn't work"
The password is set in `.env` (`VNC_PASSWORD=fbclicker`). The container must be **rebuilt and restarted** after editing `.env`:
```bash
docker compose --profile manual -f docker-compose.yml down
docker compose --profile manual -f docker-compose.yml build fbclicker-manual
docker compose --profile manual -f docker-compose.yml up -d fbclicker-manual
```
The file in the container is at `/tmp/fbclicker_vnc_passwd` (8 bytes, DES-encrypted).

### "I see the desktop but no browser opens"
There are usually leftover Chromium zombies. The loop already kills them, but if it still fails, on the server:
```bash
docker exec fbclicker-manual bash -c 'pkill -9 -f ms-playwright; pkill -9 -f chrome_crashpad; pkill -9 -f playwright/driver'
```
Then in xterm press ENTER to restart the loop.

### "noVNC shows a 'Disconnected' / black screen"
Hard-reload the noVNC page (Ctrl+Shift+R) or open in a private window. The page caches the old WebSocket.

### "Session saved but the bot says 'not logged in'"
Run `verify_session.py` (procedure C). If it returns exit 3, Facebook invalidated the session — redo the manual login. The most common cause is a fingerprint mismatch (UA, viewport, etc.) between the machine that created the session and the one using it. **Always do the manual login inside the container** (`fbclicker-manual`), not on a different machine — this is what `data/sessions/fingerprint.json` is for.

### "Cannot connect to the Docker daemon"
Make sure you are on the server (or your user is in the `docker` group). SSH tunnel alone is not enough; docker commands must run on the server.

### "Port 6080 already in use"
```bash
ss -tlnp | grep 6080
# then either change NOVNC_PORT in the env or stop the conflicting process
```

---

## Composition / architecture (for an agent)

- **Why this is different from the old `manual_login_mac.sh` workflow**: the old script ran Chromium locally on macOS, then copied `facebook_session.json` to the Linux server via `scp`. The new flow runs Chromium **inside the same Docker container** that later runs the bot. No `scp`, no fingerprint mismatch, no path surprises.

- **Why `x11vnc -storepasswd` instead of `echo >`**: x11vnc expects the file in the same DES-encrypted format that `vncpasswd` produces. Plain text is silently accepted but authentication always fails. The Dockerfile has `x11vnc` installed; the `start_vnc.sh` script uses `-storepasswd` to write the file correctly.

- **Why a "loop" wrapper**: the user can redo the login many times without restarting xterm or the container. The loop kills leftover Chromium processes before each attempt, so a crashed browser from a previous attempt does not block the next one.

- **Why `xdotool`**: when Chromium is focused, the xterm in the background is invisible. `xdotool windowraise` brings xterm back in front so the "Press ENTER" prompt is visible. Called once in `start_vnc.sh` and once in `src/manual_login.py` after the browser has loaded Facebook.

---

## Quick reference: the `fbclicker.sh` menu

```
1) Show SSH tunnel command (for noVNC)
2) Start manual login (opens noVNC, xterm auto-launched)
3) Verify saved session
4) Start bot (production)
5) Stop all containers
6) Show logs
7) Rebuild images
8) Session info
q) Quit
```

Every option shows context and tells you what's next. Use this as the
primary interface; the individual shell scripts are for advanced /
scripted use.

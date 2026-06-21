"""
Manual Facebook login module - run from manual_login_container.sh.

Opens a visible browser inside the container's Xvfb display so the user
can solve CAPTCHA / 2FA, then saves the session and fingerprint to the
same paths the bot loads on startup.

Avoids the brittleness of exporting/importing storage_state between
machines: same Python, same fingerprint, same files.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.browser.stealth_browser import StealthBrowser
from src.config import settings


GROUP_URL_TEMPLATE = "https://www.facebook.com/groups/{gid}/participant_requests?orderby=chronological"


async def main() -> int:
    print("=" * 60)
    print("FBClicker - Manual Login (in-container)")
    print("=" * 60)
    print()

    settings.headless = False
    browser = StealthBrowser()

    try:
        print("Starting stealth browser (loading existing session if any)...")
        page = await browser.start()

        ua = browser._fingerprint.get("user_agent", "")
        vp = browser._fingerprint.get("viewport", {})
        print(f"User-Agent: {ua}")
        print(f"Viewport:   {vp.get('width')}x{vp.get('height')}")
        print()

        print("Opening Facebook...")
        await page.goto("https://www.facebook.com/")
        await asyncio.sleep(3)
        await page.keyboard.press("Escape")

        gid = settings.fb_group_id
        group_url = GROUP_URL_TEMPLATE.format(gid=gid) if gid else None

        print()
        print("-" * 60)
        print("Please complete these steps in the browser window:")
        print("  1. Log into Facebook (CAPTCHA / 2FA if asked)")
        print("  2. Make sure your name is visible top-right")
        if group_url:
            print(f"  3. Navigate to: {group_url}")
        print("-" * 60)
        print()

        # Bring the xterm to the foreground so the user can see the
        # "Press ENTER" prompt after the browser steals focus.
        try:
            import subprocess
            subprocess.run(
                ["xdotool", "search", "--name", "FBClicker - manual login",
                 "windowactivate", "--sync"],
                env={**__import__("os").environ, "DISPLAY": os.environ.get("DISPLAY", ":99")},
                check=False, timeout=5, capture_output=True,
            )
        except Exception:
            pass

        # Loop so the user can retry cookie check after solving 2FA
        cookies = []
        for attempt in (1, 2):
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(
                    f"Press ENTER when logged in (attempt {attempt}/2)..."
                )
            )

            context = browser._context
            cookies = await context.cookies()
            names = [c["name"] for c in cookies]
            has_c_user = "c_user" in names
            has_xs = "xs" in names
            print(f"  Found {len(cookies)} cookies")
            print(f"  c_user: {'OK' if has_c_user else 'MISSING'}")
            print(f"  xs:     {'OK' if has_xs else 'MISSING'}")
            if has_c_user and has_xs:
                break
            print("  Auth cookies missing, please complete login then retry.")

        if "c_user" not in [c["name"] for c in cookies] or \
           "xs"     not in [c["name"] for c in cookies]:
            print()
            print("ERROR: auth cookies still missing. Aborting save.")
            return 1

        # Force=True: we are explicitly saving a user-confirmed session
        await browser.save_session(force=True)

        with open(browser._session_path) as f:
            saved = json.load(f)
        saved_names = [c["name"] for c in saved.get("cookies", [])]
        print()
        print(f"Saved {len(saved_names)} cookies: {sorted(set(saved_names))}")

        print()
        print("=" * 60)
        print("Session saved. You can now:")
        print("  1. Close this terminal window")
        print("  2. Stop the VNC container:  docker compose --profile manual down")
        print("  3. Start the bot normally:  docker compose up -d fbclicker")
        print("=" * 60)

        await asyncio.get_event_loop().run_in_executor(
            None, lambda: input("Press ENTER to close the browser...")
        )
        return 0
    finally:
        await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""
Verify a saved FBClicker Facebook session.

Loads data/sessions/facebook_session.json (and the matching fingerprint.json)
using the same StealthBrowser the bot uses, navigates to Facebook, and
reports whether the session is still valid (logged in, group page
reachable). Does NOT modify the session file.

Usage:
    python verify_session.py
    python verify_session.py --visible        # headed mode (for debugging)
    python verify_session.py --data-dir data  # custom data dir
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow running from project root or from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.browser.stealth_browser import StealthBrowser
from src.config import settings


PASS = "[OK]   "
FAIL = "[FAIL] "
INFO = "[..]   "


def _override_settings(args) -> None:
    if args.data_dir:
        settings.data_dir = args.data_dir
        settings.sessions_dir = str(Path(args.data_dir) / "sessions")
        settings.screenshots_dir = str(Path(args.data_dir) / "screenshots")
    settings.headless = not args.visible


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a saved FB session")
    parser.add_argument("--visible", action="store_true",
                        help="Run browser in headed mode (for debugging)")
    parser.add_argument("--data-dir", default=None,
                        help="Override settings.data_dir")
    args = parser.parse_args()

    _override_settings(args)

    session_path = Path(settings.sessions_dir) / "facebook_session.json"
    fingerprint_path = Path(settings.sessions_dir) / "fingerprint.json"
    print(f"{INFO}data dir:    {settings.data_dir}")
    print(f"{INFO}session:     {session_path}")
    print(f"{INFO}fingerprint: {fingerprint_path}")

    if not session_path.exists():
        print(f"{FAIL}session file missing: {session_path}")
        print("       Run ./manual_login.sh first.")
        return 1

    # Quick static checks
    with open(session_path) as f:
        state = json.load(f)
    cookies = state.get("cookies", [])
    origins = state.get("origins", [])
    names = {c["name"] for c in cookies}
    print(f"{INFO}cookies:     {len(cookies)} total, names={sorted(names)[:10]}{'...' if len(names) > 10 else ''}")
    print(f"{INFO}origins:     {len(origins)}")

    for required in ("c_user", "xs"):
        mark = PASS if required in names else FAIL
        print(f"{mark}cookie {required!r} present")

    has_c_user = "c_user" in names
    has_xs = "xs" in names
    if not (has_c_user and has_xs):
        print(f"{FAIL}auth cookies missing -> session is not usable")
        print("       re-run ./manual_login.sh and complete the login")
        return 2

    # Live check via the actual browser
    print(f"{INFO}launching browser to verify against facebook.com...")
    browser = StealthBrowser()
    page = None
    exit_code = 0
    try:
        page = await browser.start()

        # 1. facebook.com - should land on the home feed, not /login
        print(f"{INFO}navigating to https://www.facebook.com/ ...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)
        url = page.url
        print(f"{INFO}landed at: {url}")
        if "/login" in url or "checkpoint" in url or "/recover" in url:
            print(f"{FAIL}redirected to {url} - session is not valid")
            exit_code = 3
        else:
            print(f"{PASS}facebook.com reachable without login redirect")

        # 2. /me - lightweight liveness probe
        if exit_code == 0:
            print(f"{INFO}navigating to https://www.facebook.com/me ...")
            try:
                await page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                me_url = page.url
                print(f"{INFO}landed at: {me_url}")
                if "/login" in me_url or "checkpoint" in me_url:
                    print(f"{FAIL}/me redirected to login - session expired")
                    exit_code = 3
                else:
                    print(f"{PASS}/me reachable (session alive)")
            except Exception as e:
                print(f"{FAIL}/me navigation failed: {e}")
                exit_code = 4

        # 3. group page - the real test
        if exit_code == 0 and settings.fb_group_id:
            group_url = f"https://www.facebook.com/groups/{settings.fb_group_id}/participant_requests?orderby=chronological"
            print(f"{INFO}navigating to group: {group_url}")
            try:
                await page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3)
                g_url = page.url
                print(f"{INFO}landed at: {g_url}")
                if "/login" in g_url or "checkpoint" in g_url:
                    print(f"{FAIL}group page redirected to login")
                    exit_code = 3
                else:
                    # Best-effort content check
                    body = (await page.content()).lower()
                    if "partecipanti" in body or "richieste" in body or "participant" in body or "requests" in body:
                        print(f"{PASS}group page loaded with member-requests content")
                    else:
                        print(f"{INFO}group page loaded but expected content not detected (may need scroll)")
            except Exception as e:
                print(f"{FAIL}group page navigation failed: {e}")
                exit_code = 4
        elif not settings.fb_group_id:
            print(f"{INFO}fb_group_id not set - skipping group check")

        # Screenshot for the user
        shot = await browser.screenshot("verify_session")
        print(f"{INFO}screenshot: {shot}")

    except Exception as e:
        print(f"{FAIL}exception: {type(e).__name__}: {e}")
        exit_code = 5
    finally:
        if page is not None:
            try:
                await browser.close()
            except Exception:
                pass

    if exit_code == 0:
        print(f"{PASS}session looks healthy")
    else:
        print(f"{FAIL}session verification failed (exit={exit_code})")
    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""
Manual Login Script for FBClicker

This script opens a visible browser window so you can:
1. Log into Facebook manually (handling CAPTCHA, 2FA, etc.)
2. Navigate to the group
3. The session will be saved for the bot to use later

Run this ONCE before starting the bot in Docker.
Uses the SAME StealthBrowser class as the bot for consistency.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.browser.stealth_browser import StealthBrowser
from src.config import settings

GROUP_URL = f"https://www.facebook.com/groups/{settings.fb_group_id}/participant_requests?orderby=chronological"


async def main():
    print("=" * 60)
    print("FBClicker - Manual Login Script")
    print("=" * 60)
    print()
    print("Using the SAME StealthBrowser as the bot for consistency.")
    print()
    
    # Override headless to False for manual login
    settings.headless = False
    
    # Create StealthBrowser - same as bot uses
    browser = StealthBrowser()
    
    try:
        # Start browser - loads existing session/fingerprint if available
        print("Starting browser (loading existing session if available)...")
        page = await browser.start()
        
        print(f"Fingerprint hash: {browser.fingerprint.get('user_agent', '')[:50]}...")
        print()
        
        print("A browser window will open. Please:")
        print("1. Log into Facebook with your account (if not already)")
        print("2. Complete any CAPTCHA or 2FA verification")
        print("3. Navigate to the group member requests page")
        print("4. Press ENTER in this console when ready to save session")
        print()
        
        # Navigate to Facebook
        print("Opening Facebook...")
        await page.goto("https://www.facebook.com/")
        
        # Wait a bit for page to load
        await asyncio.sleep(3)
        
        # Dismiss any Messenger popups (same as bot does)
        print("Dismissing any popups...")
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        
        print()
        print("-" * 60)
        print("Browser opened! Please log in manually if needed.")
        print("After logging in, try navigating to:")
        print(f"  {GROUP_URL}")
        print("-" * 60)
        print()
        
        # Wait for user input
        await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: input("Press ENTER when you have successfully logged in and are on the group page...")
        )
        
        # Save session using StealthBrowser's method
        print()
        print("Saving session...")
        await browser.save_session()
        print(f"✅ Session saved!")
        print()
        
        # Ask if user wants to close
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: input("Press ENTER to close the browser...")
        )
        
    finally:
        # Close browser
        await browser.close()
    
    print()
    print("=" * 60)
    print("Done! You can now start the bot with:")
    print("  docker compose up -d")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

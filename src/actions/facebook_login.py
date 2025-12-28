"""Facebook login handler with session persistence - ASYNC version."""
import os
from playwright.async_api import Page
import structlog

from src.config import settings
from src.browser.human_behavior import HumanBehavior
from src.vision.screenshot_analyzer import ScreenshotAnalyzer

logger = structlog.get_logger()


class FacebookLogin:
    """Handles Facebook login with human-like behavior - ASYNC version."""
    
    FB_LOGIN_URL = "https://www.facebook.com/"
    
    def __init__(self, page: Page, analyzer: ScreenshotAnalyzer):
        self.page = page
        self.human = HumanBehavior(page)
        self.analyzer = analyzer
    
    async def is_logged_in(self) -> bool:
        """Check if already logged in to Facebook."""
        try:
            # Navigate to Facebook
            await self.page.goto(self.FB_LOGIN_URL)
            await self.human.random_delay(2, 4)
            
            # Take screenshot and analyze
            screenshot = await self._take_screenshot("login_check")
            page_type = await self.analyzer.detect_page_type(screenshot)
            
            if page_type == "login":
                logger.info("Not logged in, login required")
                return False
            elif page_type in ["group_home", "member_requests", "post_approval"]:
                logger.info("Already logged in")
                return True
            else:
                # Check for common logged-in indicators via URL
                current_url = self.page.url
                if "login" in current_url or "checkpoint" in current_url:
                    return False
                return True
                
        except Exception as e:
            logger.error("Login check failed", error=str(e))
            return False
    
    async def login(self) -> bool:
        """Perform Facebook login with credentials."""
        logger.info("Starting Facebook login")
        
        try:
            # Go to login page
            await self.page.goto(self.FB_LOGIN_URL)
            await self.human.random_delay(2, 3)
            
            # Accept cookies if dialog appears
            await self._handle_cookie_dialog()
            
            # Look around like a human
            await self.human.look_around()
            
            # Find and fill email field
            logger.info("Entering email")
            email_field = self.page.locator('input[name="email"]')
            if await email_field.is_visible():
                await email_field.click()
                await self.human.random_delay(0.3, 0.6)
                await self.human.human_type('input[name="email"]', settings.fb_email)
            
            await self.human.random_delay(0.5, 1.0)
            
            # Find and fill password field
            logger.info("Entering password")
            password_field = self.page.locator('input[name="pass"]')
            if await password_field.is_visible():
                await password_field.click()
                await self.human.random_delay(0.3, 0.6)
                await self.human.human_type('input[name="pass"]', settings.fb_password)
            
            await self.human.random_delay(0.5, 1.5)
            
            # Click login button
            logger.info("Clicking login button")
            login_button = self.page.locator('button[name="login"]')
            if await login_button.is_visible():
                await login_button.click()
            else:
                # Try alternative login button selector
                await self.page.locator('input[type="submit"]').click()
            
            # Wait for navigation
            await self.human.random_delay(3, 5)
            
            # Check result
            screenshot = await self._take_screenshot("post_login")
            page_type = await self.analyzer.detect_page_type(screenshot)
            
            if page_type == "2fa":
                logger.warning("2FA required - manual intervention needed")
                return await self._handle_2fa()
            elif page_type == "challenge":
                logger.warning("Security challenge detected - manual intervention needed")
                return False
            elif page_type == "login":
                logger.error("Login failed - still on login page")
                return False
            else:
                logger.info("Login successful")
                return True
                
        except Exception as e:
            logger.error("Login failed", error=str(e))
            return False
    
    async def _handle_cookie_dialog(self):
        """Handle cookie consent dialog if present."""
        try:
            # Common cookie button selectors for Facebook
            cookie_selectors = [
                'button[data-cookiebanner="accept_button"]',
                'button[title="Consenti tutti i cookie"]',
                'button[title="Allow all cookies"]',
                '[aria-label="Allow all cookies"]',
                '[aria-label="Consenti tutti i cookie"]',
            ]
            
            for selector in cookie_selectors:
                button = self.page.locator(selector)
                if await button.is_visible(timeout=2000):
                    logger.info("Accepting cookies")
                    await button.click()
                    await self.human.random_delay(1, 2)
                    return
                    
        except Exception:
            # No cookie dialog, continue
            pass
    
    async def _handle_2fa(self) -> bool:
        """Handle 2FA - requires manual input via Telegram."""
        logger.warning("2FA handling requires manual intervention via Telegram")
        return False
    
    async def _take_screenshot(self, name: str) -> str:
        """Take a screenshot for analysis."""
        os.makedirs(settings.screenshots_dir, exist_ok=True)
        path = f"{settings.screenshots_dir}/{name}.png"
        await self.page.screenshot(path=path)
        return path

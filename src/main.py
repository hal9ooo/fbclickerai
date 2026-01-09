"""Main entry point for FBClicker bot - Async approval with cache."""
import asyncio
import signal
import random
from datetime import datetime
from typing import Optional
import structlog

from src.config import settings
from src.browser.stealth_browser import StealthBrowser
from src.vision.screenshot_analyzer import ScreenshotAnalyzer
from src.actions.facebook_login import FacebookLogin
from src.actions.group_moderator import GroupModerator
from src.browser.human_behavior import HumanBehavior
from src.telegram.bot import TelegramBot
from src.cache import cache

# Configure logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)

logger = structlog.get_logger()


class FBClickerBot:
    """Main bot class with async approval workflow."""
    
    def __init__(self):
        self.browser: Optional[StealthBrowser] = None
        self.analyzer: Optional[ScreenshotAnalyzer] = None
        self.login_handler: Optional[FacebookLogin] = None
        self.moderator: Optional[GroupModerator] = None
        self.moderator: Optional[GroupModerator] = None
        self.telegram: Optional[TelegramBot] = None
        self.human: Optional[HumanBehavior] = None
        
        self._running = False
        self._night_mode = False  # Track if browser is closed for night
    
    async def start(self):
        """Start all bot components."""
        logger.info("Starting FBClicker bot")
        
        # Initialize components
        self.browser = StealthBrowser()
        page = await self.browser.start()
        self.human = HumanBehavior(page)
        
        self.analyzer = ScreenshotAnalyzer()
        self.login_handler = FacebookLogin(page, self.analyzer)
        self.moderator = GroupModerator(page, self.analyzer)
        
        # Initialize Telegram bot
        self.telegram = TelegramBot()
        self.telegram.start()  # Starts in background thread
        
        # Check if logged in
        if not await self.login_handler.is_logged_in():
            logger.warning("Not logged in - session may be expired")
            self.telegram.send_message(
                "⚠️ Sessione Facebook scaduta!\n\n"
                "Esegui di nuovo `manual_login.py` per fare il login."
            )
            while not await self.login_handler.is_logged_in():
                logger.info("Waiting for valid session...")
                await asyncio.sleep(30)
        
        self.telegram.send_message("✅ Connesso a Facebook! Avvio moderazione...")
        
        self._running = True
        await self._main_loop()
    
    def _get_jittered_interval(self) -> int:
        """Calculate poll interval with random jitter for stealth."""
        base = settings.poll_interval
        jitter = settings.poll_jitter
        # Random variation within ±jitter range
        variation = random.uniform(-jitter, jitter)
        interval = int(base * (1 + variation))
        return max(60, interval)  # Minimum 1 minute
    
    def _cleanup_old_screenshots(self, max_age_hours: int = 360):
        """Delete screenshots older than max_age_hours (default: 360h = 15 days)."""
        import os
        from pathlib import Path
        import time
        
        screenshots_dir = Path(settings.screenshots_dir)
        if not screenshots_dir.exists():
            return
        
        cutoff_time = time.time() - (max_age_hours * 3600)
        deleted_count = 0
        
        for file in screenshots_dir.glob("*.png"):
            try:
                if file.stat().st_mtime < cutoff_time:
                    file.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete old screenshot {file.name}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old screenshots")
    
    async def _main_loop(self):
        """Main moderation loop with unified workflow and stealth timing."""
        logger.info("Starting moderation loop", base_interval=settings.poll_interval, jitter=settings.poll_jitter)
        
        while self._running:
            try:
                if self.telegram.is_paused:
                    await asyncio.sleep(5)
                    continue
                
                # Check working hours (06:00 - 22:00)
                now = datetime.now()
                current_hour = now.hour
                if not (6 <= current_hour < 22):
                    # Entering night mode - close browser to save session
                    if not self._night_mode:
                        logger.info("Entering night mode - closing browser to preserve session")
                        self.telegram.send_message("🌙 Pausa notturna (22:00-06:00) - Chiudo browser per preservare sessione")
                        
                        if self.browser:
                            await self.browser.close()
                        
                        self._night_mode = True
                    
                    sleep_time = self._get_jittered_interval()
                    logger.info("Outside working hours (06:00-22:00), sleeping...", current_hour=current_hour, sleep_seconds=sleep_time)
                    await asyncio.sleep(sleep_time)
                    continue
                
                # Returning from night mode - restart browser
                if self._night_mode:
                    logger.info("Exiting night mode - restarting browser")
                    self.telegram.send_message("☀️ Fine pausa notturna - Riavvio browser...")
                    
                    # Reinitialize browser and components
                    self.browser = StealthBrowser()
                    page = await self.browser.start()
                    
                    self.login_handler = FacebookLogin(page, self.analyzer)
                    self.moderator = GroupModerator(page, self.analyzer)
                    
                    # Check if still logged in
                    if not await self.login_handler.is_logged_in():
                        logger.warning("Not logged in after restart - session may have expired")
                        self.telegram.send_message(
                            "⚠️ Sessione Facebook scaduta dopo la pausa notturna!\\n\\n"
                            "Esegui di nuovo `manual_login.py` per fare il login."
                        )
                        while not await self.login_handler.is_logged_in():
                            logger.info("Waiting for valid session...")
                            await asyncio.sleep(30)
                    
                    self.telegram.send_message("✅ Browser riavviato e connesso!")
                    self._night_mode = False

                # Cleanup old cache entries (15 days)
                cache.cleanup_old(max_age_hours=360)
                
                # Cleanup old screenshots (older than 15 days)
                self._cleanup_old_screenshots(max_age_hours=360)
                
                # Navigate to requests page
                if not await self.moderator.navigate_to_member_requests():
                    logger.warning("Failed to navigate, skipping this poll")
                    await asyncio.sleep(30)
                    continue
                
                # Get pending decisions as a dict {name: decision}
                pending = cache.get_pending_decisions()
                decision_dict = {req.name: req.decision for req in pending}
                
                logger.info(f"Pending decisions: {len(decision_dict)}")
                
                # Run start notification
                run_start_time = datetime.now()
                run_time_str = run_start_time.strftime("%H:%M")
                self.telegram.send_message(f"🔄 Run delle ore {run_time_str} iniziato")
                
                # UNIFIED WORKFLOW: process decisions AND send notifications in one pass
                async def notification_callback(name: str, screenshot_path: str, extra_info: str = None, 
                                              preview_path: str = None, card_hash: str = None,
                                              action_buttons: dict = None):
                    """Callback to send notification - add to cache first, then send."""
                    # Add to cache so we can track the decision (with hash and preview for future matching)
                    cache.add_notification(name, extra_info, card_hash, preview_path, action_buttons)
                    self.telegram.send_member_request(
                        name=name,
                        extra_info=extra_info,
                        screenshot_path=screenshot_path,
                        preview_path=preview_path
                    )
                    logger.info(f"Sent notification for: {name}" + (" [with preview]" if preview_path else ""))
                
                actions = await self.moderator.process_and_notify(
                    pending_decisions=decision_dict,
                    telegram_callback=notification_callback
                )
                
                if actions:
                    logger.info(f"Executed {len(actions)} actions")
                    # Mark all processed decisions as executed
                    for name in actions:
                        cache.mark_executed(name)
                        self.telegram.send_message(f"✅ Eseguito: <b>{name}</b>")
                    
                    # If actions were taken, recycle immediately (don't wait for full interval)
                    logger.info("Actions taken - restarting poll immediately to process remaining items")
                    await self.human.random_delay(5, 15)
                    continue
                
                # Run end notification with duration
                run_end_time = datetime.now()
                run_duration = (run_end_time - run_start_time).total_seconds() / 60
                self.telegram.send_message(f"✅ Run delle ore {run_time_str} terminato - durata: {run_duration:.1f} minuti")
                
                # Wait for next poll with jitter for stealth
                sleep_time = self._get_jittered_interval()
                logger.info("Waiting for next poll", seconds=sleep_time, base=settings.poll_interval)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error("Error in main loop", error=str(e))
                self.telegram.send_message(f"⚠️ Errore: {str(e)}")
                await asyncio.sleep(30)
    
    async def _execute_pending_decisions(self):
        """DEPRECATED: Now handled by process_and_notify."""
        pass
    
    async def _scan_and_notify(self):
        """DEPRECATED: Now handled by process_and_notify."""
        pass
    
    async def stop(self):
        """Stop all components gracefully."""
        logger.info("Stopping FBClicker bot")
        self._running = False
        
        if self.telegram:
            self.telegram.stop()
        
        if self.analyzer:
            await self.analyzer.close()
        
        if self.browser:
            await self.browser.close()
        
        logger.info("Bot stopped")


async def main():
    """Main async entry point."""
    bot = FBClickerBot()
    
    def signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.stop())
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

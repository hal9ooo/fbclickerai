"""Facebook group moderation actions - ASYNC version with scroll and cache support."""
import os
from pathlib import Path
from typing import List, Optional, Dict
from playwright.async_api import Page
from datetime import datetime
import structlog
import cv2
import numpy as np
from PIL import Image

from src.vision.ocr_adapter import OCREngine
from src.config import settings
from src.browser.human_behavior import HumanBehavior
from src.vision.screenshot_analyzer import ScreenshotAnalyzer, MemberRequest
from src.vision.card_detector import CardDetector

logger = structlog.get_logger()

class GroupModerator:
    """Handles Facebook group moderation tasks - ASYNC version."""
    
    def __init__(self, page: Page, analyzer: ScreenshotAnalyzer):
        self.page = page
        self.human = HumanBehavior(page)
        self.analyzer = analyzer
        self.group_id = settings.fb_group_id
        self.screenshot_counter = 0
        self.decision_cache = {}
        
        # Initialize CardDetector
        self.card_detector = CardDetector(settings.screenshots_dir)

        # Initialize RapidOCR (via Adapter)
        logger.info("Loading RapidOCR (CPU mode)...")
        self.ocr_engine = OCREngine()
        logger.info("RapidOCR loaded.")
    
    @property
    def member_requests_url(self) -> str:
        """URL for member requests page."""
        return f"https://www.facebook.com/groups/{self.group_id}/participant_requests?orderby=chronological"
    
    @property
    def group_home_url(self) -> str:
        """URL for group home page."""
        return f"https://www.facebook.com/groups/{self.group_id}"
    
    async def navigate_to_member_requests(self) -> bool:
        """Navigate to the member requests page."""
        logger.info("Navigating to member requests page", group_id=self.group_id)
        
        try:
            await self.page.goto(self.member_requests_url)
            await self.human.random_delay(3, 5)
            
            # Dismiss any Messenger popups that might interfere
            await self._dismiss_messenger_popup()
            
            # Verify we're on the right page
            screenshot = await self._take_screenshot("member_requests")
            page_type = await self.analyzer.detect_page_type(screenshot)
            
            if page_type == "member_requests":
                logger.info("Successfully navigated to member requests")
                return True
            elif page_type == "login":
                logger.warning("Session expired, login required")
                return False
            else:
                logger.warning("Unexpected page type", page_type=page_type)
                # Continue anyway - might still work
                return True
                
        except Exception as e:
            logger.error("Navigation failed", error=str(e))
            return False
    
    async def _dismiss_messenger_popup(self):
        """Dismiss Messenger notification popup if present."""
        try:
            # Wait for Messenger popup to fully load before trying to dismiss it
            await self.human.random_delay(2, 3)
            
            # Method 1: Press Escape to close any popup
            await self.page.keyboard.press("Escape")
            await self.human.random_delay(0.5, 0.8)
            
            # Method 2: Try to click the close button on Messenger popup
            # The popup usually has a close (X) button or can be dismissed by clicking outside
            close_selectors = [
                '[aria-label="Chiudi"]',
                '[aria-label="Close"]', 
                '[aria-label="Close chat"]',
                '[aria-label="Chiudi chat"]',
                'div[role="dialog"] [aria-label="Chiudi"]',
                'div[role="dialog"] [aria-label="Close"]',
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = await self.page.query_selector(selector)
                    if close_btn and await close_btn.is_visible():
                        await close_btn.click()
                        logger.info(f"Dismissed Messenger popup via {selector}")
                        await self.human.random_delay(0.3, 0.5)
                        break
                except Exception:
                    continue
            
            # Method 3: Click on the main content area to dismiss popups
            # Click somewhere in the main content, not on sidebar
            try:
                await self.page.mouse.click(700, 400)
                await self.human.random_delay(0.2, 0.3)
            except Exception:
                pass
            
            # Final Escape to make sure
            await self.page.keyboard.press("Escape")
            await self.human.random_delay(0.2, 0.3)
            
        except Exception as e:
            logger.debug(f"Error dismissing Messenger popup (non-critical): {e}")
    
    async def process_and_notify(self, pending_decisions: dict, telegram_callback) -> list:
        """
        UNIFIED WORKFLOW: Process pending decisions AND send notifications.
        
        Re-screenshots after each click to handle page reflow when cards disappear.
        
        Args:
            pending_decisions: Dict of {name: "approve"/"decline"} for pending decisions
            telegram_callback: async function(name, screenshot_path) to send notifications
            
        Returns:
            List of names for which actions were taken (approvals + declines)
        """
        actions_taken = []
        notifications_to_send = []  # [(name, screenshot_path), ...]
        processed_names = set()  # Track names we've already seen
        
        logger.info("=" * 60)
        logger.info(f"UNIFIED SCAN: {len(pending_decisions)} pending decisions")
        logger.info("=" * 60)
        
        while True:
            # 1. Scroll down to load all content first
            logger.info("Scrolling to load all content...")
            for i in range(3):
                await self.human.human_scroll("down", 800)
                await self.human.random_delay(0.5, 0.8)
            
            # 2. Scroll back to top
            logger.info("Scrolling to top...")
            await self.page.evaluate("window.scrollTo(0, 0)")
            await self.human.random_delay(2, 3)  # Longer delay to ensure page renders
            
            # 3. Take full-page screenshot
            fullpage_path = f"{settings.screenshots_dir}/fullpage_scan.png"
            await self.page.screenshot(path=fullpage_path, full_page=True)
            
            # 3. Detect cards
            logger.info("Detecting cards...")
            cards = self.card_detector.detect_cards(fullpage_path)
            
            if not cards:
                logger.warning("No cards detected on page!")
                break
            
            logger.info(f"Detected {len(cards)} cards")
            
            click_performed = False
            
            # Import cache and imagehash for hash checking
            from src.cache import cache
            import imagehash
            
            # 4. Process each card
            for card in cards:
                try:
                    # Load image first (needed for hash AND OCR)
                    image = Image.open(card.image_path)
                    img_width, img_height = image.size
                    
                    # OPTIMIZATION: Check perceptual hash BEFORE expensive OCR
                    card_hash = str(imagehash.average_hash(image))
                    
                    if settings.card_hash_threshold > 0:
                        matched_name = cache.is_hash_similar(card_hash, settings.card_hash_threshold)
                        if matched_name:
                            # CRITICAL: Check if a decision is pending
                            if matched_name in pending_decisions:
                                # Try to get cached button coordinates
                                cached_req = cache.get_request(matched_name)
                                decision = pending_decisions[matched_name]
                                
                                # If we have cached buttons, we can click without OCR!
                                if cached_req and cached_req.action_buttons:
                                    logger.info(f"Card {card.card_index}: Hash match '{matched_name}' with PENDING DECISION")
                                    logger.info(f"  Cached buttons available - executing WITHOUT OCR")
                                    
                                    target = "approve" if decision == "approve" else "decline"
                                    coords = cached_req.action_buttons.get(target)
                                    
                                    if coords:
                                        x, y = coords
                                        
                                        # RESTORED: Calculate absolute page coordinates (handles sidebar/header offset)
                                        abs_x, abs_y = self.card_detector.get_absolute_coords(card, x, y)
                                        
                                        # RESTORED: Scroll to element to ensure visibility
                                        viewport_height = 864
                                        scroll_to_y = max(0, abs_y - viewport_height // 2)
                                        # logger.info(f"Scrolling to Y={scroll_to_y}")
                                        await self.page.evaluate(f"window.scrollTo(0, {scroll_to_y})")
                                        await self.human.random_delay(0.5, 0.8)
                                        
                                        # Get ACTUAL scroll position
                                        actual_scroll_y = await self.page.evaluate("window.scrollY")
                                        viewport_y = abs_y - actual_scroll_y
                                        
                                        logger.info(f"Clicking cached button at absolute ({abs_x}, {abs_y}) -> viewport ({abs_x}, {viewport_y})")
                                        
                                        # Save debug overlay before click
                                        await self._save_click_overlay(abs_x, viewport_y, decision, card.card_index)
                                        
                                        await self.human.human_click(abs_x, viewport_y)
                                        
                                        # For DECLINE: longer delay for Facebook to respond
                                        if decision == "decline":
                                            await self.human.random_delay(2.0, 3.0)
                                        
                                        actions_taken.append(matched_name)
                                        click_performed = True
                                        
                                        await self.human.random_delay(2, 3)
                                        break  # Exit card loop, re-screenshot needed
                                        
                                logger.info(f"Card {card.card_index}: Hash match '{matched_name}' but decision pending (no cached buttons) - forcing OCR")
                                # Fall through to OCR
                            else:
                                logger.info(f"Card {card.card_index}: hash matches cached '{matched_name}' - skipping OCR")
                                # Retrieve cached preview and extra_info
                                cached_request = cache.get_request(matched_name)
                                cached_extra = cached_request.extra_info if cached_request else None
                                cached_preview = cached_request.preview_path if cached_request else None
                                # Retrieve cached buttons if any (for future use?)
                                cached_buttons = cached_request.action_buttons if cached_request else None
                                # Retrieve cached cropped path - use it instead of raw card image
                                cached_cropped = cached_request.cropped_path if cached_request else None
                                # Retrieve cached is_unanswered status
                                cached_unanswered = cached_request.is_unanswered if cached_request else False
                                
                                # Use cached cropped path if available, otherwise fall back to raw card image
                                screenshot_to_send = cached_cropped if cached_cropped else card.image_path
                                
                                logger.info(f"  Queuing notification with cached data (cropped: {cached_cropped is not None}, unanswered: {cached_unanswered})")
                                # For cached matches, we can't determine is_unanswered without OCR, default to False
                                notifications_to_send.append((matched_name, screenshot_to_send, cached_extra, cached_preview, card_hash, cached_buttons, cached_unanswered, cached_cropped))
                                continue
                    
                    # RapidOCR (only for new/unknown cards)
                    logger.info("=" * 50)
                    logger.info(f"OCR PROCESSING CARD {card.card_index}")
                    logger.info(f"  Image path: {card.image_path}")
                    logger.info(f"  Card Y range: {card.y_start}-{card.y_end}")
                    logger.info(f"  Image dimensions: {img_width}x{img_height}")
                    
                    predictions = self.ocr_engine.run_ocr(image)
                    prediction = predictions[0]
                    
                    # Extract text and identify name
                    valid_texts = []
                    logger.info(f"  OCR found {len(prediction.text_lines)} text lines:")
                    for idx, line in enumerate(prediction.text_lines):
                        text_content = line.text
                        box = line.bbox
                        y1, y2 = box[1], box[3]
                        x1, x2 = box[0], box[2]
                        center_y = (y1 + y2) // 2
                        center_x = (x1 + x2) // 2
                        logger.info(f"    [{idx}] '{text_content}' @ bbox={box}")
                        valid_texts.append({
                            'text': text_content, 
                            'y': center_y, 
                            'x': center_x,
                            'bbox': box
                        })
                    
                    valid_texts.sort(key=lambda x: x['y'])
                    candidates = [t['text'] for t in valid_texts if len(t['text']) >= 2]
                    detected_name = candidates[0] if candidates else ""
                    
                    if not detected_name:
                        logger.warning(f"No name detected on card {card.card_index}")
                        continue
                    
                    # Extract extra info (all text except name)
                    extra_texts = [t['text'] for t in valid_texts if t['text'] != detected_name and len(t['text']) >= 2]
                    # Filter out common UI elements
                    filtered_extra = [t for t in extra_texts if not any(ui in t.lower() for ui in ['approva', 'rifiuta', 'invia messaggio', 'richiesta'])]
                    extra_info = "\n".join(filtered_extra) if filtered_extra else None
                    
                    # Check for "Anteprima" link and capture preview if present
                    preview_screenshot_path = None
                    has_preview = any('anteprima' in t['text'].lower() for t in valid_texts)
                    if has_preview:
                        preview_screenshot_path = await self._capture_post_preview(card, valid_texts)
                        # Crop preview to just the modal content
                        if preview_screenshot_path:
                            cropped_modal = self.card_detector.crop_preview_modal(preview_screenshot_path)
                            if cropped_modal:
                                preview_screenshot_path = cropped_modal
                    
                    # EXTRACT ACTION BUTTONS
                    action_buttons = {}
                    for t in valid_texts:
                        txt_lower = t['text'].lower()
                        if 'approva' in txt_lower or 'approve' in txt_lower:
                            bbox = t.get('bbox')
                            if bbox:
                                cx = int((bbox[0] + bbox[2]) / 2)
                                cy = int((bbox[1] + bbox[3]) / 2)
                                action_buttons['approve'] = [cx, cy]
                        elif 'rifiuta' in txt_lower or 'decline' in txt_lower:
                            bbox = t.get('bbox')
                            if bbox:
                                cx = int((bbox[0] + bbox[2]) / 2)
                                cy = int((bbox[1] + bbox[3]) / 2)
                                action_buttons['decline'] = [cx, cy]
                    
                    logger.info(f"Card {card.card_index}: '{detected_name}'"  + (" [has preview]" if preview_screenshot_path else ""))
                    if extra_info:
                        logger.debug(f"Extra info: {extra_info}")
                    
                    # Skip if already processed this session
                    if detected_name in processed_names:
                        continue
                    processed_names.add(detected_name)
                    
                    # CHECK 1: Is this name in pending decisions?
                    decision = None
                    for pending_name, pending_decision in pending_decisions.items():
                        if self._names_match(detected_name, pending_name):
                            decision = pending_decision
                            matched_name = pending_name
                            break
                    
                    if decision:
                        # Execute the decision (click approve/decline)
                        logger.info(f"EXECUTING: {decision.upper()} for '{detected_name}'")
                        
                        # Find button coordinates from OCR bbox (more accurate than hardcoded %)
                        button_coords = None
                        target_text = "approva" if decision == "approve" else "rifiuta"
                        
                        for t in valid_texts:
                            if target_text in t['text'].lower():
                                bbox = t.get('bbox')
                                if bbox:
                                    # Click at center of bbox
                                    center_x = int((bbox[0] + bbox[2]) / 2)
                                    center_y = int((bbox[1] + bbox[3]) / 2)
                                    button_coords = (center_x, center_y)
                                    logger.info(f"Found '{target_text}' via OCR bbox: {bbox} -> center ({center_x}, {center_y})")
                                    break
                        
                        # Fallback to hardcoded percentages if OCR didn't find button
                        if not button_coords:
                            # Use action_buttons if found earlier
                            target = "approve" if decision == "approve" else "decline"
                            if target in action_buttons:
                                button_coords = tuple(action_buttons[target])
                                logger.info(f"Using found button coords for {target}: {button_coords}")
                        
                        if not button_coords:
                            # Ultimate fallback: hardcoded estimates
                            if decision == "approve":
                                # Approx location for Approve button (bottom leftish)
                                button_coords = (int(img_width * 0.15), int(img_height * 0.85))
                                logger.warning(f"OCR missed approve button, using fallback coords: {button_coords}")
                            else:
                                # Approx location for Decline button (bottom rightish)
                                button_coords = (int(img_width * 0.65), int(img_height * 0.85))
                                logger.warning(f"OCR missed decline button, using fallback coords: {button_coords}")

                        # Execute click
                        # valid_texts coords are relative to the CROPPED CARD image
                        # We need absolute page coordinates
                        
                        # card.y_start is absolute Y on page? NO, it's relative to viewport top at capture time?
                        # Let's check _capture_visible_cards: 
                        # cards = self.card_detector.detect_cards(screenshot_path)
                        # And screenshot is FULL PAGE screenshot?
                        # No, usually viewport screenshot.
                        # "screenshot_path = ... screenshot.png"
                        # "cards = ..."
                        
                        # If screenshot is viewport, then detected Y is relative to VIEWPORT TOP (0).
                        # But we might have scrolled.
                        # We have 'actual_scroll_y' from beginning of loop.
                        
                        # self.human.human_click takes (x, y) in VIEWPORT coordinates.
                        
                        # So:
                        # btn_x_rel = button_coords[0]
                        # btn_y_rel = button_coords[1]
                        
                        # card_x_rel = card.bbox[0] (but card object might just have y range)
                        # Check Card object: y_start, y_end. x is assumed 0? Or do we have bbox?
                        # In card_detector.py, Card dataclass has bbox?
                        # No, Card has 'image_path', 'y_start', 'y_end'. x is implicit (full width or cropped?)
                        
                        # Wait, the OCR image IS the card image.
                        # Card image is created in detect_cards by cropping:
                        # crop = image[y_start:y_end, 0:width]
                        # So x is 0 relative to page left.
                        # y is 0 relative to card top.
                        
                        # So absolute viewport X = button_coords[0]
                        # Absolute viewport Y = card.y_start + button_coords[1]
                        
                        # Calculate absolute page coordinates
                        abs_x, abs_y = self.card_detector.get_absolute_coords(card, button_coords[0], button_coords[1])
                        
                        # SCROLL the card into viewport before clicking
                        viewport_height = 864  # Typical viewport height
                        scroll_to_y = max(0, abs_y - viewport_height // 2)  # Center the button in viewport
                        # logger.info(f"Scrolling page to Y={scroll_to_y}")
                        await self.page.evaluate(f"window.scrollTo(0, {scroll_to_y})")
                        await self.human.random_delay(0.5, 0.8)
                        
                        # Get ACTUAL scroll position (browser clamps if page is shorter than requested)
                        actual_scroll_y = await self.page.evaluate("window.scrollY")
                        
                        # Now click at VIEWPORT coordinates using ACTUAL scroll position
                        viewport_y = abs_y - actual_scroll_y
                        logger.info(f"Clicking at viewport coords ({abs_x}, {viewport_y})")
                        
                        # Save debug overlay before click
                        await self._save_click_overlay(abs_x, viewport_y, decision, card.card_index)
                        
                        await self.human.human_click(abs_x, viewport_y)
                        
                        # For DECLINE: longer delay for Facebook to respond
                        if decision == "decline":
                            await self.human.random_delay(2.0, 3.0)
                        
                        # Remove from pending decisions (optional, but good for local loop if logic changes)
                        # del pending_decisions[matched_name] - REMOVED: main.py uses return value
                        actions_taken.append(matched_name)
                        click_performed = True
                        
                        await self.human.random_delay(2, 3)
                        break  # Exit card loop, re-screenshot needed
                    
                    # CHECK 2: Queue for notification (if not clicking)
                    # Check if user hasn't answered questions
                    is_unanswered = self._is_unanswered_question(valid_texts)
                    if not is_unanswered:
                        # Debug log to see what text we actually found
                        logger.info(f"detected_texts: {[t['text'] for t in valid_texts]}")
                    
                    # Crop card to text content only (using OCR bbox)
                    cropped_card_path = self._crop_card_to_text_bbox(card.image_path, valid_texts)
                    # Tuple: (name, screenshot_path, extra_info, preview_path, card_hash, action_buttons, is_unanswered, cropped_path)
                    notifications_to_send.append((detected_name, cropped_card_path, extra_info, preview_screenshot_path, card_hash, action_buttons, is_unanswered, cropped_card_path))
                    
                except Exception as e:
                    logger.error(f"Error processing card {card.card_index}", error=str(e))
                    continue
            
            # 5. If no click performed, we're done scanning
            if not click_performed:
                logger.info("No more actions to take, finishing scan")
                break
            
            # If click WAS performed: Facebook changes page layout after approve/decline
            # Must exit and restart entire poll cycle for next decision
            logger.info("Click performed - exiting scan (layout changed, restart poll for next decision)")
            break
        
        # 6. Send all accumulated notifications
        # 6. Send all accumulated notifications
        if notifications_to_send:
            logger.info(f"Sending {len(notifications_to_send)} potential notifications...")
            for name, screenshot_path, extra_info, preview_path, card_hash, action_buttons, is_unanswered, cropped_path in notifications_to_send:
                try:
                    await telegram_callback(name, screenshot_path, extra_info, preview_path, card_hash, action_buttons, is_unanswered, cropped_path)
                except Exception as e:
                    logger.error(f"Failed to send notification for {name}", error=str(e))
        
        logger.info(f"Unified scan complete: {len(actions_taken)} actions, {len(notifications_to_send)} notifications queued")
        return actions_taken
    
    # Keep scan_all_requests as a simpler wrapper for backward compatibility
    async def scan_all_requests(self) -> List[MemberRequest]:
        """Legacy method - now just returns empty list, use process_and_notify instead."""
        logger.warning("scan_all_requests is deprecated, use process_and_notify instead")
        return []
    
    async def find_request_on_page(self, target_name: str) -> Optional[MemberRequest]:
        """Find a specific member request by name using vision."""
        logger.info("Searching for member on page", name=target_name)
        
        # First check current view
        screenshot = await self._take_screenshot("find_target")
        result = await self.analyzer.analyze_member_requests(screenshot)
        
        for req in result.member_requests:
            if self._names_match(req.name, target_name):
                logger.info("Found target member", name=target_name)
                return req
        
        # Try scrolling to find them
        for scroll_num in range(MAX_SCROLLS):
            await self.human.human_scroll("down", 400)
            await self.human.random_delay(1, 2)
            
            screenshot = await self._take_screenshot(f"find_scroll_{scroll_num}")
            result = await self.analyzer.analyze_member_requests(screenshot)
            
            for req in result.member_requests:
                if self._names_match(req.name, target_name):
                    logger.info("Found target member after scroll", name=target_name, scroll=scroll_num)
                    return req
        
        logger.warning("Could not find member on page", name=target_name)
        return None
    
    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two names match (case-insensitive, normalized)."""
        n1 = name1.strip().lower()
        n2 = name2.strip().lower()
        return n1 == n2 or n1 in n2 or n2 in n1
    
    def _is_unanswered_question(self, valid_texts: list) -> bool:
        """Check if OCR text indicates user hasn't answered questions.
        
        Returns True if text contains 'non ha ancora risposto' or 'in attesa della risposta'.
        """
        unanswered_phrases = [
            "non ha ancora risposto",
            "in attesa della risposta"
        ]
        
        for t in valid_texts:
            text_lower = t['text'].lower()
            for phrase in unanswered_phrases:
                if phrase in text_lower:
                    return True
        return False
    
    async def approve_member(self, request: MemberRequest) -> bool:
        """Approve a member request by finding it on screen and clicking directly.
        
        NEW APPROACH: Don't use pre-calculated coordinates. Instead:
        1. The card should already be on screen (find_request_on_page found it)
        2. Take a viewport screenshot
        3. Find the approve button position directly on this screenshot
        4. Click at that viewport position
        """
        logger.info("Approving member", name=request.name)
        
        try:
            # Take a screenshot of current viewport
            await self._take_screenshot("before_click")
            current_path = Path(self.analyzer.screenshots_dir) / "before_click.png"
            
            # Load the screenshot and find approve button
            import cv2
            viewport_img = cv2.imread(str(current_path))
            if viewport_img is None:
                logger.error("Failed to load viewport screenshot")
                return False
            
            viewport_h, viewport_w = viewport_img.shape[:2]
            logger.info("Viewport size", width=viewport_w, height=viewport_h)
            
            # The card should be visible. Find ALL blue approve buttons on screen
            # and click the one that's most likely ours (based on expected position)
            hsv = cv2.cvtColor(viewport_img, cv2.COLOR_BGR2HSV)
            
            # Blue button detection (same as card_detector)
            lower_blue = np.array([100, 150, 150])
            upper_blue = np.array([120, 255, 255])
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
            
            kernel = np.ones((5,5), np.uint8)
            mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find all approve buttons IN THE CONTENT AREA
            # Exclude buttons in sidebar (x < 360) and header (y < 276)
            SIDEBAR_WIDTH = 360
            HEADER_HEIGHT = 276
            
            buttons = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                area = w * h
                ar = w / float(h) if h > 0 else 0
                center_x = x + w // 2
                center_y = y + h // 2
                
                # Button criteria: 
                # 1. Reasonable size and aspect ratio
                # 2. In content area (not sidebar, not header where "Approve All" is)
                if (area > 1000 and w > 50 and h > 25 and 1.5 < ar < 6.0 and
                    center_x > SIDEBAR_WIDTH and center_y > HEADER_HEIGHT):
                    buttons.append((center_x, center_y, area))
                    logger.debug("Found approve button in content", x=center_x, y=center_y, area=area)
            
            if not buttons:
                logger.error("No approve buttons found in content area!")
                return False
            
            # Sort by Y position (topmost first) - this is the card we scrolled to
            buttons.sort(key=lambda b: b[1])
            click_x, click_y, _ = buttons[0]
            
            logger.info("Clicking approve button", 
                       x=click_x, y=click_y,
                       buttons_found=len(buttons))
            
            # Perform the click
            await self.page.mouse.move(click_x, click_y, steps=10)
            await self.human.random_delay(0.2, 0.5)
            await self.page.mouse.click(click_x, click_y)
            
            logger.info("Clicked approve button", x=click_x, y=click_y)
            
            await self.human.random_delay(2, 3)
            await self._take_screenshot("after_click")
            return True
            
        except Exception as e:
            logger.error("Failed to approve member", name=request.name, error=str(e))
            return False
    
    async def decline_member(self, request: MemberRequest) -> bool:
        """Decline a member request by finding it on screen and clicking directly.
        
        Same approach as approve_member but detecting GRAY decline button.
        """
        logger.info("Declining member", name=request.name)
        
        try:
            # Take a screenshot of current viewport
            await self._take_screenshot("before_decline")
            current_path = Path(self.analyzer.screenshots_dir) / "before_decline.png"
            
            # Load the screenshot and find decline button
            viewport_img = cv2.imread(str(current_path))
            if viewport_img is None:
                logger.error("Failed to load viewport screenshot")
                return False
            
            viewport_h, viewport_w = viewport_img.shape[:2]
            hsv = cv2.cvtColor(viewport_img, cv2.COLOR_BGR2HSV)
            
            # Gray button detection (low saturation, high value)
            lower_gray = np.array([0, 0, 210])
            upper_gray = np.array([180, 25, 248])
            mask_gray = cv2.inRange(hsv, lower_gray, upper_gray)
            
            kernel = np.ones((5,5), np.uint8)
            mask_gray = cv2.morphologyEx(mask_gray, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter buttons in content area
            SIDEBAR_WIDTH = 360
            HEADER_HEIGHT = 276
            
            buttons = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                area = w * h
                ar = w / float(h) if h > 0 else 0
                center_x = x + w // 2
                center_y = y + h // 2
                
                # Button criteria: reasonable size, in content area
                if (area > 1000 and w > 50 and h > 25 and 1.5 < ar < 6.0 and
                    center_x > SIDEBAR_WIDTH and center_y > HEADER_HEIGHT):
                    buttons.append((center_x, center_y, area))
                    logger.debug("Found decline button", x=center_x, y=center_y, area=area)
            
            if not buttons:
                logger.error("No decline buttons found in content area!")
                return False
            
            # Sort by Y position (topmost first)
            buttons.sort(key=lambda b: b[1])
            click_x, click_y, _ = buttons[0]
            
            logger.info("Clicking decline button", 
                       x=click_x, y=click_y,
                       buttons_found=len(buttons))
            
            # Perform the click
            await self.page.mouse.move(click_x, click_y, steps=10)
            await self.human.random_delay(0.2, 0.5)
            await self.page.mouse.click(click_x, click_y)
            
            await self.human.random_delay(1, 2)
            
            # Handle confirmation dialog if any
            await self._handle_decline_confirmation()
            
            logger.info("Member declined", name=request.name, x=click_x, y=click_y)
            await self._take_screenshot("after_decline")
            return True
            
        except Exception as e:
            logger.error("Failed to decline member", name=request.name, error=str(e))
            return False
    
    async def execute_decision(self, name: str, decision: str) -> bool:
        """Execute a pending decision for a member by finding them on page."""
        logger.info("Executing decision", name=name, decision=decision)
        
        # Navigate to page first
        if not await self.navigate_to_member_requests():
            return False
        
        # Find the member
        request = await self.find_request_on_page(name)
        if not request:
            logger.warning("Member not found, may have been processed already", name=name)
            return True  # Consider it done
        
        # Execute action
        if decision == "approve":
            return await self.approve_member(request)
        elif decision == "decline":
            return await self.decline_member(request)
        else:
            logger.error("Unknown decision", decision=decision)
            return False
    
    async def _handle_decline_confirmation(self):
        """Handle any confirmation dialog after declining."""
        try:
            await self.human.random_delay(0.5, 1)
            
            screenshot = await self._take_screenshot("decline_confirm")
            coords = await self.analyzer.find_element(
                screenshot, 
                "Confirm or Conferma button in a dialog"
            )
            
            if coords:
                # Save debug overlay before click
                await self._save_click_overlay(coords[0], coords[1], "confirm_decline")
                
                await self.human.human_click(coords[0], coords[1])
                await self.human.random_delay(1, 2)
                
        except Exception:
            pass
    
    async def refresh_requests(self):
        """Refresh the member requests page."""
        logger.info("Refreshing requests page")
        await self.page.reload()
        await self.human.random_delay(3, 5)
    
    async def _take_screenshot(self, name: str) -> str:
        """Take a screenshot with timestamp for uniqueness."""
        from datetime import datetime
        os.makedirs(settings.screenshots_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        path = f"{settings.screenshots_dir}/{name}_{timestamp}.png"
        await self.page.screenshot(path=path)
        return path
    
    async def _save_click_overlay(self, click_x: int, click_y: int, step_name: str, card_index: int = -1) -> Optional[str]:
        """
        Save a debug image showing where the click will happen.
        
        Args:
            click_x: X coordinate of the click (viewport coordinates)
            click_y: Y coordinate of the click (viewport coordinates)
            step_name: Description of the step (e.g., 'approve', 'decline', 'anteprima')
            card_index: Index of the card being processed (-1 if not applicable)
            
        Returns:
            Path to the saved overlay image, or None if debug is disabled
        """
        if not settings.debug_click_overlay:
            return None
        
        try:
            # Timestamp for unique filename
            timestamp = datetime.now().strftime("%H%M%S")
            
            # Build descriptive filename
            if card_index >= 0:
                filename = f"debug_click_{timestamp}_card{card_index}_{step_name}.png"
            else:
                filename = f"debug_click_{timestamp}_{step_name}.png"
            
            filepath = f"{settings.screenshots_dir}/{filename}"
            
            # Take current viewport screenshot
            await self.page.screenshot(path=filepath)
            
            # Load and draw overlay
            img = cv2.imread(filepath)
            if img is None:
                return None
            
            # Draw large cross at click position
            cross_size = 30
            color = (0, 0, 255)  # Red in BGR
            thickness = 3
            
            # Horizontal line
            cv2.line(img, (int(click_x - cross_size), int(click_y)), 
                     (int(click_x + cross_size), int(click_y)), color, thickness)
            # Vertical line
            cv2.line(img, (int(click_x), int(click_y - cross_size)), 
                     (int(click_x), int(click_y + cross_size)), color, thickness)
            # Circle around click point
            cv2.circle(img, (int(click_x), int(click_y)), cross_size, color, 2)
            
            # NO TEXT LABELS - just the marker to avoid AI confusion
            
            # Save
            cv2.imwrite(filepath, img)
            logger.info(f"Debug overlay saved: {filename}")
            
            # AI validation of click position
            await self._validate_click_with_ai(filepath, step_name, card_index)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save click overlay: {e}")
            return None
    
    async def _validate_click_with_ai(self, overlay_path: str, expected_target: str, card_index: int):
        """
        Use OpenRouter vision model to validate if the click overlay is correctly positioned.
        
        Args:
            overlay_path: Path to the overlay image with red cross marker
            expected_target: What we expect to click ('approve', 'decline', 'anteprima', 'confirm_decline')
            card_index: Index of the card being processed
        """
        # Skip if AI validation is disabled
        if not settings.debug_ai_validation:
            return
        import base64
        import httpx
        
        try:
            # Read and encode image
            with open(overlay_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Build prompt based on expected target
            target_descriptions = {
                "approve": "the blue 'Approva' (Approve) button",
                "decline": "the gray 'Rifiuta' (Decline) button",
                "anteprima": "the 'Anteprima' (Preview) link text",
                "confirm_decline": "the confirmation button in a dialog"
            }
            expected_desc = target_descriptions.get(expected_target, expected_target)
            
            prompt = f"""Look at this Facebook screenshot. There is a RED CROSS/CIRCLE marker showing where a click will happen.

Is the red marker positioned correctly on {expected_desc}?

Answer with:
1. YES or NO - is the marker on the correct element?
2. What element the marker is ACTUALLY positioned on (describe what you see under the red cross)
3. If NO, describe where the {expected_desc} actually is

Be very brief and direct."""

            # Debug logging
            api_key = settings.openrouter_api_key
            logger.info(f"AI Validation - API Key prefix: {api_key[:10]}... (len={len(api_key)})")
            logger.info(f"AI Validation - URL: {settings.openrouter_base_url}/chat/completions")
            logger.info(f"AI Validation - Model: {settings.openrouter_model}")

            # Call OpenRouter
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": settings.openrouter_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_data}"
                                        }
                                    }
                                ]
                            }
                        ],
                        "max_tokens": 200
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    ai_answer = result["choices"][0]["message"]["content"]
                    
                    # Log AI validation result
                    logger.info("=" * 50)
                    logger.info(f"AI CLICK VALIDATION - Card {card_index} - Target: {expected_target}")
                    logger.info(f"AI Response: {ai_answer}")
                    logger.info("=" * 50)
                else:
                    logger.warning(f"AI validation failed: HTTP {response.status_code}")
                    logger.warning(f"Response body: {response.text[:500]}")
                    
        except Exception as e:
            logger.warning(f"AI validation error (non-blocking): {e}")
    
    async def _capture_post_preview(self, card, ocr_texts: list) -> Optional[str]:
        """
        Click on 'Anteprima' link to open post/comment preview popup,
        capture screenshot, and close it.
        
        Args:
            card: The DetectedCard containing position info
            ocr_texts: List of {'text': str, 'y': int, 'x': int, 'bbox': tuple} from OCR
            
        Returns:
            Path to preview screenshot, or None if failed
        """
        try:
            # Find "Anteprima" text position from OCR
            # Strategy: First look for STANDALONE "Anteprima" (better), then fall back to text containing it
            anteprima_item = None
            standalone_match = None
            contains_match = None
            
            for t in ocr_texts:
                text_lower = t['text'].lower().strip()
                
                # Priority 1: Standalone "Anteprima" (exact or nearly exact match)
                if text_lower == 'anteprima' or text_lower in ['anteprima', 'anteprima.']:
                    standalone_match = t
                    logger.info(f"Found STANDALONE 'Anteprima': {t}")
                    break
                
                # Priority 2: Text containing "Anteprima"
                if 'anteprima' in text_lower and not contains_match:
                    contains_match = t
                    logger.info(f"Found text CONTAINING 'Anteprima': {t['text']}")
            
            anteprima_item = standalone_match or contains_match
            
            if not anteprima_item:
                return None
            
            logger.info("Found 'Anteprima' link, capturing preview...")
            
            # Get click coordinates from OCR bbox
            # bbox is (x1, y1, x2, y2)
            # IMPORTANT: "Anteprima" is at the END of the text like "Ha inviato un post. Anteprima"
            # So we need to click on the RIGHT side of the bbox, not the center!
            bbox = anteprima_item.get('bbox')
            logger.info(f"Anteprima OCR bbox: {bbox}")
            logger.info(f"Anteprima text: '{anteprima_item.get('text')}'")
            
            # Check if this is a standalone or contained match
            is_standalone = (standalone_match is not None)
            logger.info(f"Match type: {'STANDALONE' if is_standalone else 'CONTAINED'}")
            
            if bbox:
                # Click on the RIGHT part of the bbox where "Anteprima" word is
                # X: 35px from right edge (5px left of original 30)
                rel_x = int(bbox[2]) - 35
                
                # Y: center of bbox (no offset - both standalone and contained)
                rel_y = (bbox[1] + bbox[3]) // 2
                logger.info(f"Using center Y of bbox")
                
                logger.info(f"Using RIGHT side of bbox: x={bbox[2]} - 35 = {rel_x}")
            else:
                # Fallback: use approximate position
                rel_x = int(card.width * 0.35)  # Anteprima is typically left-center
                rel_y = anteprima_item['y']
            
            logger.info(f"Card dimensions: {card.width}x{card.height}")
            logger.info(f"Relative coords in card: ({rel_x}, {rel_y})")
            
            # Convert to absolute page coordinates using same method as buttons
            # This uses SIDEBAR_WIDTH (360) which is correct for fullpage coordinate system
            abs_x, abs_y = self.card_detector.get_absolute_coords(card, rel_x, rel_y)
            logger.info(f"Absolute page coords: ({abs_x}, {abs_y})")
            
            # Get viewport dimensions for scroll calculation
            viewport = self.page.viewport_size
            viewport_height = viewport["height"] if viewport else 864
            
            # Scroll card into view if needed
            scroll_to_y = max(0, abs_y - viewport_height // 2)
            await self.page.evaluate(f"window.scrollTo(0, {scroll_to_y})")
            await self.human.random_delay(0.3, 0.5)
            
            # Get ACTUAL scroll position (browser clamps if page is shorter than requested)
            actual_scroll_y = await self.page.evaluate("window.scrollY")
            
            # Adjust Y for viewport using ACTUAL scroll position
            viewport_y = abs_y - actual_scroll_y
            
            logger.info(f"Scroll requested: {scroll_to_y}, actual: {actual_scroll_y}")
            logger.info(f"After scroll: viewport coords ({abs_x}, {viewport_y})")
            
            # Save debug overlay before click
            await self._save_click_overlay(abs_x, viewport_y, "anteprima", card.card_index)
            
            await self.human.human_click(abs_x, viewport_y)
            
            # Wait for popup to appear - give it enough time!
            logger.info("Waiting for popup to appear...")
            await self.human.random_delay(5.0, 6.0)
            
            # Take screenshot of the popup with unique name
            preview_path = await self._take_screenshot(f"preview_card_{card.card_index}")
            logger.info(f"Preview captured: {preview_path}")
            
            # Close popup - try multiple methods
            # Method 1: Press Escape multiple times
            await self.page.keyboard.press("Escape")
            await self.human.random_delay(0.5, 0.8)
            await self.page.keyboard.press("Escape")
            await self.human.random_delay(0.5, 0.8)
            
            # Method 2: Click outside the popup (far left of page)
            await self.page.mouse.click(50, 400)
            await self.human.random_delay(1.0, 1.5)
            
            logger.info("Popup closed, returning to cards")
            return preview_path
            
        except Exception as e:
            logger.error("Failed to capture post preview", error=str(e))
            # Try to close any open popup
            try:
                await self.page.keyboard.press("Escape")
                await self.page.keyboard.press("Escape")
                await self.page.mouse.click(50, 400)
            except:
                pass
            return None
    
    def _crop_card_to_text_bbox(self, card_image_path: str, ocr_texts: list, padding: int = 20) -> str:
        """
        Crop card image to the bounding box of all OCR text, plus padding.
        
        Args:
            card_image_path: Path to the original card image
            ocr_texts: List of {'text': str, 'bbox': [x1, y1, x2, y2]} from OCR
            padding: Pixels to add around the text bbox
            
        Returns:
            Path to the cropped image (or original if crop fails)
        """
        try:
            # Filter to get only text elements with valid bbox (exclude buttons)
            text_bboxes = []
            for t in ocr_texts:
                bbox = t.get('bbox')
                text_lower = t['text'].lower()
                # Exclude UI buttons from bbox calculation
                if bbox and not any(ui in text_lower for ui in ['approva', 'rifiuta', '•••']):
                    text_bboxes.append(bbox)
            
            if not text_bboxes:
                logger.warning("No text bboxes found for cropping")
                return card_image_path
            
            # Calculate bounding box of all text
            min_x = min(b[0] for b in text_bboxes)
            min_y = min(b[1] for b in text_bboxes)
            max_x = max(b[2] for b in text_bboxes)
            max_y = max(b[3] for b in text_bboxes)
            
            # Add padding
            img = Image.open(card_image_path)
            img_width, img_height = img.size
            
            crop_left = max(0, int(min_x) - padding)
            crop_top = max(0, int(min_y) - padding)
            crop_right = min(img_width, int(max_x) + padding)
            crop_bottom = min(img_height, int(max_y) + padding)
            
            # Crop
            cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))
            
            # Save to new file
            cropped_path = card_image_path.replace('.png', '_cropped.png')
            cropped.save(cropped_path)
            
            logger.info(f"Card cropped to text bbox: ({crop_left}, {crop_top}) - ({crop_right}, {crop_bottom})")
            
            return cropped_path
            
        except Exception as e:
            logger.error(f"Failed to crop card to text bbox: {e}")
            return card_image_path


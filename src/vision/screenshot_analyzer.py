"""Screenshot analyzer using OpenRouter API with vision models - ASYNC version with cropping."""
import base64
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple
from PIL import Image
import httpx
import structlog
import cv2
import numpy as np

from src.config import settings
from src.vision.card_detector import CardDetector, DetectedCard

logger = structlog.get_logger()

# Facebook UI crop offsets (to remove header, sidebar, and filter bar)
# CRITICAL: These MUST match card_detector.py constants!
# Content is cropped at: HEADER_HEIGHT + FILTER_BAR_HEIGHT from top
CROP_TOP = 276     # Header (56) + filter bar (220) = 276
CROP_LEFT = 360    # Sidebar width
USER_CARD_HEIGHT = 350  # Approximate height of each user card


@dataclass
class MemberRequest:
    """Represents a member join request."""
    name: str
    profile_url: Optional[str]
    approve_coords: Tuple[int, int]  # Relative to card image
    decline_coords: Tuple[int, int]  # Relative to card image
    extra_info: Optional[str] = None
    screenshot_path: Optional[str] = None  # Path to screenshot where this user was found
    card_top: int = 0     # Absolute Y top of card in full page
    card_bottom: int = 0  # Absolute Y bottom of card in full page
    absolute_approve_coords: Optional[Tuple[int, int]] = None  # Absolute coords in full page
    
    def get_real_approve_coords(self) -> Tuple[int, int]:
        """Get coordinates adjusted for full page (add crop offsets)."""
        # approve_coords are relative to CARD
        # Absolute Y = crop_top + card_top + relative_y
        return (self.approve_coords[0] + CROP_LEFT, self.approve_coords[1] + self.card_top + CROP_TOP)
    
    def get_real_decline_coords(self) -> Tuple[int, int]:
        """Get coordinates adjusted for full page (add crop offsets)."""
        return (self.decline_coords[0] + CROP_LEFT, self.decline_coords[1] + self.card_top + CROP_TOP)
    
    def get_real_card_bounds(self) -> Tuple[int, int]:
        """Get card top/bottom adjusted for full page."""
        return (self.card_top + CROP_TOP, self.card_bottom + CROP_TOP)


@dataclass
class VisionResponse:
    """Response from vision analysis."""
    page_type: str
    member_requests: List[MemberRequest]
    has_more: bool
    error: Optional[str] = None


class ScreenshotAnalyzer:
    """Analyzes screenshots using OpenRouter's vision API - ASYNC version."""
    
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url
        self.model = settings.openrouter_model
        # self.client = httpx.AsyncClient(timeout=60.0) # Removed: All vision is local now
        self.screenshots_dir = settings.screenshots_dir
        self.card_detector = CardDetector(settings.screenshots_dir)
    
    async def analyze_full_page_cards(self, full_page_screenshot: str) -> List[MemberRequest]:
        """
        NEW: Analyze a full-page screenshot by splitting into individual cards.
        
        1. Use CardDetector to find and split cards
        2. Analyze each card separately with GPT
        3. Return MemberRequests with absolute coordinates
        """
        logger.info("Analyzing full-page screenshot with card detection")
        
        # Detect and split cards
        cards = self.card_detector.detect_cards(full_page_screenshot)
        
        if not cards:
            logger.warning("No cards detected, falling back to standard analysis")
            result = await self.analyze_member_requests(full_page_screenshot)
            return result.member_requests
        
        # Analyze each card
        all_requests = []
        for card in cards:
            try:
                request = await self._analyze_single_card(card)
                if request:
                    all_requests.append(request)
            except Exception as e:
                logger.error("Failed to analyze card", index=card.card_index, error=str(e))
        
        logger.info("Full-page analysis complete", total_requests=len(all_requests))
        return all_requests
    
    async def _analyze_single_card(self, card: DetectedCard) -> Optional[MemberRequest]:
        """Analyze a single card image and return MemberRequest with absolute coords."""
        prompt = """Analyze this Facebook group member request card image.

Return a JSON object with:
{
    "name": "Full name of the person",
    "profile_url": "URL if visible, null otherwise",
    "extra_info": "Any additional info shown (friends in group, answers, etc)",
    "approve_button_x": X coordinate of the center of the Approve/Approva button,
    "approve_button_y": Y coordinate of the center of the Approve/Approva button,
    "decline_button_x": X coordinate of the center of the Decline/Rifiuta button,
    "decline_button_y": Y coordinate of the center of the Decline/Rifiuta button
}

The coordinates should be relative to THIS image (top-left is 0,0).
If you cannot identify a member request, return {"error": "not a member request card"}.
Return ONLY the JSON, no other text."""

        try:
            # Load card image
            card_img = cv2.imread(str(card.image_path))
            if card_img is None:
                logger.error("Failed to load card image for analysis")
                return None

            # 1. Calculate Button Coordinates (Fixed Percentages - more reliable than OpenCV)
            card_height, card_width = card_img.shape[:2]
            
            # Skip small cards (partial views or garbage)
            # Minimum 300px ensures we have a complete card with valid name
            if card_height < 300:
                logger.debug("Skipping small card", height=card_height)
                return None
            
            approve_coords, decline_coords = self.card_detector.get_button_coords(card_width)
            
            rel_approve_x, rel_approve_y = approve_coords
            rel_decline_x, rel_decline_y = decline_coords
            
            # Use purely relative coords for MemberRequest
            mr_approve_x = rel_approve_x
            mr_approve_y = rel_approve_y
            mr_decline_coords = (rel_decline_x, rel_decline_y)
            
            # Recalculate absolute coords for logging/debugging only
            abs_approve = self.card_detector.get_absolute_coords(
                card, rel_approve_x, rel_approve_y
            )

            # 2. Extract Text (Name, Bio) using Tesseract - REMOVED
            text_data = {} # self.card_detector.extract_text(card_img)
            
            request = MemberRequest(
                name=text_data.get("name", "Unknown"),
                profile_url=None, # Cannot get URL from screenshot easily
                approve_coords=(mr_approve_x, mr_approve_y),
                decline_coords=mr_decline_coords,
                extra_info=text_data.get("extra_info", []),
                screenshot_path=card.image_path,
                card_top=card.y_start,
                card_bottom=card.y_end,
                absolute_approve_coords=abs_approve
            )
            
            logger.info("Card analyzed locally", 
                       name=request.name,
                       rel_approve=f"({mr_approve_x},{mr_approve_y})",
                       rel_decline=f"({mr_decline_coords[0]},{mr_decline_coords[1]})")
            
            return request
            
        except Exception as e:
            logger.error("Card analysis failed", error=str(e))
            return None

    
    def _crop_screenshot(self, image_path: str) -> str:
        """Crop screenshot to remove Facebook header and sidebar."""
        cropped_path = image_path.replace(".png", "_cropped.png")
        
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                
                # Crop: left, top, right, bottom
                cropped = img.crop((CROP_LEFT, CROP_TOP, width, height))
                cropped.save(cropped_path)
                
                logger.debug("Screenshot cropped", 
                           original_size=f"{width}x{height}",
                           cropped_size=f"{cropped.width}x{cropped.height}")
                
            return cropped_path
        except Exception as e:
            logger.error("Failed to crop screenshot", error=str(e))
            return image_path  # Fallback to original
    
    def get_cropped_screenshot(self, image_path: str) -> str:
        """Get cropped screenshot path (for sending to Telegram)."""
        return self._crop_screenshot(image_path)
    
    def crop_user_area(self, image_path: str, card_top: int, card_bottom: int, user_name: str) -> str:
        """Crop a specific user's card area from the screenshot.
        
        card_top: Top Y of user card in CROPPED image (from GPT-4V)
        card_bottom: Bottom Y of user card in CROPPED image (from GPT-4V)
        Returns path to cropped user-specific image.
        """
        # Create unique filename for this user
        safe_name = user_name.replace(" ", "_").replace("/", "")[:20]
        user_crop_path = image_path.replace(".png", f"_user_{safe_name}.png")
        
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                
                # Convert from cropped coords (GPT-4V) to original image coords
                real_top = card_top + CROP_TOP
                real_bottom = card_bottom + CROP_TOP
                
                # Validate bounds
                if real_top < CROP_TOP:
                    real_top = CROP_TOP
                if real_bottom > height:
                    real_bottom = height
                if real_bottom <= real_top:
                    # Invalid bounds, use fallback
                    real_top = CROP_TOP
                    real_bottom = min(height, CROP_TOP + 400)
                
                # Crop: left, top, right, bottom (remove left sidebar too)
                cropped = img.crop((CROP_LEFT, real_top, width, real_bottom))
                cropped.save(user_crop_path)
                
                logger.info("User card cropped", 
                           user=user_name,
                           crop_area=f"y={real_top}-{real_bottom}",
                           card_height=real_bottom - real_top)
                
            return user_crop_path
        except Exception as e:
            logger.error("Failed to crop user area", error=str(e))
            return self._crop_screenshot(image_path)  # Fallback
    
    async def analyze_member_requests(self, screenshot_path: str) -> VisionResponse:
        """
        Analyze a screenshot of the member requests page (cropped).
        REFACTORED to use local analysis (OpenCV + Tesseract) only.
        """
        logger.info("Analyzing member requests locally", path=screenshot_path)
        
        try:
            # Reuse full page logic which now uses local detection/extraction
            requests = await self.analyze_full_page_cards(screenshot_path)
            
            return VisionResponse(
                page_type="member_requests",
                member_requests=requests,
                has_more=False # Pagination handled by scrolling logic in moderator
            )
        except Exception as e:
            logger.error("Local analysis failed", error=str(e))
            return VisionResponse(page_type="error", member_requests=[])
    
    async def detect_page_type(self, screenshot_path: str) -> str:
        """Detect what type of Facebook page is shown using local OCR."""
        logger.info("Detecting page type locally", path=screenshot_path)
        
        try:
            # Fallback for now: assume member requests page
            img = cv2.imread(screenshot_path)
            if img is None:
                return "unknown"
            return "member_requests"
            
        except Exception as e:
            logger.error("Page type detection failed", error=str(e))
            return "unknown"
    
    async def find_element(self, screenshot_path: str, description: str) -> Optional[Tuple[int, int]]:
        """Find coordinates of a specific element by description."""
        # Local fallback since GPT-4 is removed.
        # For now, return None as this is mainly used for 'decline confirmation' which is rare.
        return None

    async def close(self):
        """Close resources."""
        # await self.client.aclose() # Removed
        pass

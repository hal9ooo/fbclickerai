"""Local computer vision for detecting and splitting member request cards."""
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger()

# Facebook UI constants
SIDEBAR_WIDTH = 360    # Left sidebar width to crop
HEADER_HEIGHT = 56     # Top header height to crop
FILTER_BAR_HEIGHT = 220  # Filter bar below header (Richieste, filtri, etc)
MIN_CARD_HEIGHT = 100  # Minimum height for a valid card
MAX_CARD_HEIGHT = 500  # Maximum height for a valid card

# Button positions (relative to card image, as % of card width)
# Based on Facebook's consistent UI layout
APPROVE_BUTTON_X_PERCENT = 0.60  # Approva is at ~60% of card width
DECLINE_BUTTON_X_PERCENT = 0.78  # Rifiuta is at ~78% of card width
BUTTON_Y_OFFSET = 46             # Both buttons are ~46px from top of card


@dataclass
class DetectedCard:
    """A detected member request card."""
    y_start: int          # Top Y position in FULL page
    y_end: int            # Bottom Y position in FULL page
    image_path: str       # Path to cropped card image
    card_index: int       # Index of this card (0-based)
    sidebar_width: int = 360  # Width of sidebar crop (for coordinate conversion)
    
    @property
    def height(self) -> int:
        """Height of the card in pixels."""
        return self.y_end - self.y_start
    
    @property
    def width(self) -> int:
        """Width of the card image in pixels."""
        try:
            img = cv2.imread(self.image_path)
            if img is not None:
                return img.shape[1]
        except:
            pass
        return 1560  # Default content width


class CardDetector:
    """Detects and splits member request cards using computer vision."""
    
    def __init__(self, screenshots_dir: str):
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_cards(self, full_page_image_path: str, viewport_mode: bool = False) -> List[DetectedCard]:
        """
        Detect member request cards in a screenshot.
        
        Args:
            full_page_image_path: Path to the screenshot
            viewport_mode: If True, assumes screenshot is already cropped viewport 
                          (no sidebar/header offset needed). If False, assumes full-page.
        
        1. Optionally crop sidebar and header (if full-page)
        2. Detect horizontal separators between cards
        3. Split into individual card images
        4. Return list of cards with their Y positions
        """
        mode_label = "viewport" if viewport_mode else "full-page"
        logger.info("=" * 60)
        logger.info(f"CARD DETECTION START - {mode_label} mode")
        logger.info(f"  Input image: {full_page_image_path}")
        
        # Load image
        img = cv2.imread(full_page_image_path)
        if img is None:
            logger.error("Failed to load image", path=full_page_image_path)
            return []
        
        height, width = img.shape[:2]
        logger.info(f"  Original image size: {width}x{height}")
        
        # Crop sidebar and header based on mode
        if viewport_mode:
            # Viewport screenshots still have sidebar, but header/filter bar are visible
            # We need to skip sidebar + the visible filter buttons row (~200-250px from top)
            content_left = SIDEBAR_WIDTH  # Still 360px sidebar
            content_top = 250  # Skip search bar + filter buttons in viewport
            content = img[content_top:, content_left:]
        else:
            # Full-page: crop sidebar and full header+filter area
            content_left = SIDEBAR_WIDTH
            content_top = HEADER_HEIGHT + FILTER_BAR_HEIGHT
            content = img[content_top:, content_left:]
        
        content_height, content_width = content.shape[:2]
        logger.info(f"  Crop offsets: left={content_left}, top={content_top}")
        logger.info(f"  Content area after crop: {content_width}x{content_height}")
        
        # Detect horizontal lines (card separators)
        card_boundaries = self._detect_card_boundaries(content)
        
        if not card_boundaries:
            logger.warning("No card boundaries detected, using full content as single card")
            card_boundaries = [(0, content_height)]
        
        logger.info(f"  Card boundaries found: {len(card_boundaries)}")
        
        # Split into individual cards
        cards = []
        for i, (y_start, y_end) in enumerate(card_boundaries):
            # Extract card image
            card_img = content[y_start:y_end, :]
            
            # Skip if too small
            if card_img.shape[0] < MIN_CARD_HEIGHT:
                logger.debug(f"  Card {i} skipped - too small: {card_img.shape[0]}px < {MIN_CARD_HEIGHT}px")
                continue
            
            # Save card image
            card_path = self.screenshots_dir / f"card_{i}.png"
            cv2.imwrite(str(card_path), card_img)
            
            # Calculate absolute Y positions (add back the header offset)
            abs_y_start = y_start + content_top
            abs_y_end = y_end + content_top
            
            cards.append(DetectedCard(
                y_start=abs_y_start,
                y_end=abs_y_end,
                image_path=str(card_path),
                card_index=i
            ))
            
            logger.info(f"  CARD {i}: saved to {card_path}")
            logger.info(f"    Dimensions: {card_img.shape[1]}x{card_img.shape[0]}")
            logger.info(f"    Y range in content: {y_start}-{y_end}")
            logger.info(f"    Y range absolute: {abs_y_start}-{abs_y_end}")
        
        logger.info(f"CARD DETECTION COMPLETE: {len(cards)} cards")
        logger.info("=" * 60)
        return cards
    
    def _detect_card_boundaries(self, content: np.ndarray) -> List[Tuple[int, int]]:
        """
        Detect card boundaries by finding uniform-colored separator rows.
        In Facebook's light theme, separators are uniform gray rows between cards.
        """
        height, width = content.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(content, cv2.COLOR_BGR2GRAY)
        
        # Calculate row statistics: look for rows with LOW variance (uniform color)
        # and specific brightness range (gray background ~200-240 for light theme)
        separator_rows = []
        
        for y in range(height):
            row = gray[y, :]
            row_mean = np.mean(row)
            row_std = np.std(row)
            
            # Separator rows are uniform (low std) and gray/light colored
            # Light theme: separator is ~#E4E6EB (228, 230, 235) -> gray ~229
            # Adjust thresholds if needed
            is_uniform = row_std < 15  # Low variance = uniform color
            is_separator_color = 200 < row_mean < 245  # Gray/light background
            
            if is_uniform and is_separator_color:
                separator_rows.append(y)
        
        if not separator_rows:
            logger.warning("No separator rows found, falling back to avatar detection")
            return self._detect_by_avatar(content)
        
        # Group consecutive separator rows into separator regions
        separator_regions = []
        region_start = separator_rows[0]
        prev_row = separator_rows[0]
        
        for row in separator_rows[1:]:
            if row - prev_row > 10:  # Gap > 10px means new region
                separator_regions.append((region_start, prev_row))
                region_start = row
            prev_row = row
        separator_regions.append((region_start, prev_row))
        
        # Filter: only keep significant separator regions (> 5px tall)
        significant_separators = [(s, e) for s, e in separator_regions if e - s >= 5]
        
        logger.debug("Found separator regions", count=len(significant_separators))
        
        # Build card boundaries: between consecutive separators
        if len(significant_separators) < 2:
            # Not enough separators, try avatar detection
            return self._detect_by_avatar(content)
        
        boundaries = []
        for i in range(len(significant_separators) - 1):
            card_start = significant_separators[i][1] + 1  # Just after separator ends
            card_end = significant_separators[i + 1][0]    # Just before next separator
            
            if card_end - card_start >= MIN_CARD_HEIGHT:
                boundaries.append((card_start, card_end))
        
        # Add first card (from top to first separator)
        if significant_separators[0][0] > MIN_CARD_HEIGHT:
            boundaries.insert(0, (0, significant_separators[0][0]))
        
        # Add last card (from last separator to bottom)
        last_sep_end = significant_separators[-1][1]
        if height - last_sep_end > MIN_CARD_HEIGHT:
            boundaries.append((last_sep_end + 1, height))
        
        # Sort by y_start
        boundaries.sort(key=lambda b: b[0])
        
        return boundaries
    
    def _detect_by_avatar(self, content: np.ndarray) -> List[Tuple[int, int]]:
        """
        Alternative detection: look for circular avatars as card markers.
        """
        height, width = content.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(content, cv2.COLOR_BGR2GRAY)
        
        # Detect circles (avatars)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=100,  # Minimum distance between circle centers
            param1=50,
            param2=30,
            minRadius=20,
            maxRadius=50
        )
        
        if circles is None:
            logger.warning("No avatars detected")
            # Fallback: divide evenly
            return self._divide_evenly(height)
        
        # Sort circles by Y position
        circles = circles[0]
        circles = sorted(circles, key=lambda c: c[1])  # Sort by Y
        
        # Use circle centers as card starts
        boundaries = []
        for i, circle in enumerate(circles):
            y_center = int(circle[1])
            y_start = max(0, y_center - 50)  # Start a bit above avatar
            
            if i < len(circles) - 1:
                next_y = int(circles[i + 1][1])
                y_end = max(y_start + MIN_CARD_HEIGHT, next_y - 20)
            else:
                y_end = min(y_start + MAX_CARD_HEIGHT, height)
            
            boundaries.append((y_start, y_end))
        
        return boundaries
    
    def _divide_evenly(self, height: int, estimated_cards: int = 5) -> List[Tuple[int, int]]:
        """Fallback: divide the content evenly."""
        card_height = height // estimated_cards
        return [(i * card_height, (i + 1) * card_height) for i in range(estimated_cards)]
    
    def get_absolute_coords(self, card: DetectedCard, 
                           relative_x: int, relative_y: int) -> Tuple[int, int]:
        """
        Convert coordinates relative to a card image back to absolute page coordinates.
        
        Args:
            card: The DetectedCard containing position info
            relative_x: X coordinate relative to card image
            relative_y: Y coordinate relative to card image
            
        Returns:
            Tuple of (absolute_x, absolute_y) for the full page
        """
        logger.info("=" * 40)
        logger.info("COORDINATE CONVERSION")
        logger.info(f"  Input relative coords: ({relative_x}, {relative_y})")
        logger.info(f"  Card index: {card.card_index}")
        logger.info(f"  Card y_start: {card.y_start}, y_end: {card.y_end}")
        logger.info(f"  Card dimensions: {card.width}x{card.height}")
        logger.info(f"  SIDEBAR_WIDTH: {SIDEBAR_WIDTH}")
        
        # Add sidebar offset for X
        absolute_x = relative_x + SIDEBAR_WIDTH
        
        # Add card's Y position for Y
        absolute_y = relative_y + card.y_start
        
        logger.info(f"  Output absolute coords: ({absolute_x}, {absolute_y})")
        logger.info("=" * 40)
        
        return (absolute_x, absolute_y)

    def get_button_coords(self, card_width: int, card_height: int = 380) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Calculate button coordinates based on card dimensions.
        
        Buttons are at TOP RIGHT of the card, around 46px from top.
        Using percentages of card width for responsive positioning.
        
        Args:
            card_width: Width of the card content area in pixels
            card_height: Height of the card content area in pixels (unused, kept for compatibility)
            
        Returns:
            ((approve_x, approve_y), (decline_x, decline_y)) - both relative to card
        """
        # Percentages from LEFT edge (calculated from OCR bbox detection)
        # Approva button center: bbox [834, 902] → center 868 → 868/1560 = 0.556
        # Rifiuta button center: bbox [1020, 1073] → center 1046 → 1046/1560 = 0.671
        approve_x = int(card_width * 0.556)
        decline_x = int(card_width * 0.671)
        
        # Buttons are at TOP of card, about 46px from top
        button_y = BUTTON_Y_OFFSET  # 46px from top
        
        approve_coords = (approve_x, button_y)
        decline_coords = (decline_x, button_y)
        
        logger.debug("Calculated button coords", 
                    card_width=card_width,
                    approve=approve_coords, 
                    decline=decline_coords)
        
        return approve_coords, decline_coords


    def detect_buttons(self, card_content: np.ndarray) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """
        Detect 'Approva' (Blue) and 'Rifiuta' (Gray) buttons.
        Returns ((approve_x, approve_y), (decline_x, decline_y)).
        """
        approve_btn = None
        decline_btn = None
        
        try:
            # Convert to HSV
            hsv = cv2.cvtColor(card_content, cv2.COLOR_BGR2HSV)
            
            # --- 1. APPROVE (Blue) ---
            lower_blue = np.array([100, 150, 150])
            upper_blue = np.array([120, 255, 255])
            mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
            
            kernel = np.ones((5,5), np.uint8)
            mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel)
            contours_blue, _ = cv2.findContours(mask_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find largest blue button
            max_area_blue = 0
            for c in contours_blue:
                x, y, w, h = cv2.boundingRect(c)
                area = w * h
                ar = w / float(h)
                if area > 1000 and w > 50 and h > 25 and 1.5 < ar < 6.0:
                    if area > max_area_blue:
                        max_area_blue = area
                        approve_btn = (x + w//2, y + h//2)
            
            # --- 2. DECLINE (Gray) ---
            # Gray is low saturation, high value (but not pyre white)
            # S < 25, V: 210-245 (Background is usually 255)
            lower_gray = np.array([0, 0, 210])
            upper_gray = np.array([180, 25, 248]) 
            mask_gray = cv2.inRange(hsv, lower_gray, upper_gray)
            
            mask_gray = cv2.morphologyEx(mask_gray, cv2.MORPH_CLOSE, kernel)
            contours_gray, _ = cv2.findContours(mask_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find gray button relative to Blue (if found) or just largest gray
            best_gray = None
            max_area_gray = 0
            
            for c in contours_gray:
                x, y, w, h = cv2.boundingRect(c)
                area = w * h
                ar = w / float(h)
                
                # Valid button shape
                if area > 1000 and w > 50 and h > 25 and 1.5 < ar < 6.0:
                    
                    # If we found Approve, Decline should be roughly same Y (+/- 20px)
                    if approve_btn:
                        app_x, app_y = approve_btn
                        if abs(y + h//2 - app_y) < 20: 
                             # Pick the one closest in size/alignment
                             if area > max_area_gray:
                                 max_area_gray = area
                                 best_gray = (x + w//2, y + h//2)
                    else:
                        # Fallback if no Approve found: just take largest gray
                        if area > max_area_gray:
                            max_area_gray = area
                            best_gray = (x + w//2, y + h//2)
            
            decline_btn = best_gray
            
            if approve_btn:
                logger.debug("OpenCV detected approve button", coords=approve_btn)
            if decline_btn:
                logger.debug("OpenCV detected decline button", coords=decline_btn)
                
            return approve_btn, decline_btn
            
        except Exception as e:
            logger.error("Button detection failed", error=str(e))
            return None, None
            
        except Exception as e:
            logger.error("Error detecting buttons", error=str(e))
            return None

    def extract_text(self, card_content: np.ndarray) -> dict:
        """
        Extract text from the card using Tesseract OCR.
        Returns a dictionary with 'name' and 'extra_info'.
        """
        import pytesseract
        
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(card_content, cv2.COLOR_BGR2GRAY)
            
            # Simple thresholding to improve text contrast
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Run OCR
            text = pytesseract.image_to_string(thresh, lang='ita+eng')
            
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            if not lines:
                return {"name": "Unknown", "extra_info": []}
            
            # Heuristic: Name is usually the first line
            # But sometimes first line is "Membro ...." or garbage
            # Facebook cards often put Name first in bold.
            
            name = lines[0]
            extra_info = lines[1:]
            
            # Simple cleanup for name if it looks like metadata
            if len(lines) > 1 and (name.lower().startswith("membro") or len(name) < 3):
                name = lines[1]
                extra_info = lines[0:1] + lines[2:]

            return {
                "name": name,
                "extra_info": extra_info
            }
            
        except Exception as e:
            logger.error("OCR extraction failed", error=str(e))
            return {"name": "Unknown (OCR Error)", "extra_info": []}

    def find_card_on_screen(self, screen_path: str, card_path: str) -> Optional[Tuple[int, int]]:
        """
        Locate the card image within the current screen screenshot using Template Matching.
        This is more robust than ORB for finding sub-images that are nearly identical (1:1 scale).
        """
        try:
            # Load images
            screen = cv2.imread(screen_path)
            card = cv2.imread(card_path)
            
            if screen is None or card is None:
                logger.error("Failed to load images for template matching")
                return None
            
            # Convert to grayscale
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            card_gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
            
            # Match only the LEFT side of the card (Avatar + Name)
            # This avoids false positives from identical "Approve" buttons on the right
            h, w = card_gray.shape
            roi_width = int(w * 0.60)
            card_template = card_gray[:, :roi_width]
            
            # Check dimensions again with ROI
            if card_template.shape[0] > screen_gray.shape[0] or card_template.shape[1] > screen_gray.shape[1]: 
                logger.warning("Card template ROI is larger than screen")
                return None

            # Template Matching on ROI
            # TM_CCOEFF_NORMED is good for lighting differences/noise
            res = cv2.matchTemplate(screen_gray, card_template, cv2.TM_CCOEFF_NORMED)
            
            # Get best match
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            logger.info("Template matching result", confidence=max_val, loc=max_loc)
            
            # Threshold: 0.8 is usually very high confidence for CCOEFF_NORMED
            # We use 0.7 to allow for minor timestamp changes (e.g. "1 min ago" vs "2 mins ago")
            if max_val >= 0.7:
                x_start, y_start = max_loc
                return (x_start, y_start)
            else:
                logger.warning("Template match confidence too low", confidence=max_val)
                return None

        except Exception as e:
            logger.error("Error finding card on screen", error=str(e))
            return None

    def crop_preview_modal(self, image_path: str) -> Optional[str]:
        """
        Detect and crop the preview modal from a screenshot.
        
        Uses edge detection to find the centered white modal rectangle.
        
        Args:
            image_path: Path to the screenshot containing the modal

        Returns:
            Path to the cropped modal image, or None if detection failed
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.warning(f"Could not load image for modal crop: {image_path}")
                return None

            h, w = img.shape[:2]
            center_x = w // 2

            logger.info(f"Cropping preview modal from {Path(image_path).name} ({w}x{h})")

            # Convert to grayscale and detect edges
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)

            # Dilate edges to close gaps
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(edges, kernel, iterations=2)

            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                logger.warning("No contours found in preview modal detection")
                return None

            # Filter contours: look for centered rectangles of modal size
            # Modal is typically 400-700px wide and at least 150px tall
            candidates = []
            for contour in contours:
                x, y, cw, ch = cv2.boundingRect(contour)
                cx = x + cw // 2
                dist_from_center = abs(cx - center_x)

                min_width, max_width = 350, 700
                min_height = 150

                if min_width <= cw <= max_width and ch >= min_height:
                    candidates.append({
                        "box": (x, y, cw, ch),
                        "center_dist": dist_from_center,
                        "area": cw * ch
                    })

            if not candidates:
                # Fallback: find white region in center third
                center_strip = gray[:, w//3:2*w//3]
                row_means = np.mean(center_strip, axis=1)
                white_rows = np.where(row_means > 200)[0]

                if len(white_rows) > 50:
                    y1 = white_rows[0]
                    y2 = white_rows[-1]
                    modal_rows = gray[y1:y2, :]
                    col_means = np.mean(modal_rows, axis=0)
                    white_cols = np.where(col_means > 200)[0]

                    if len(white_cols) > 100:
                        x1 = white_cols[0]
                        x2 = white_cols[-1]
                        candidates.append({
                            "box": (x1, y1, x2-x1, y2-y1),
                            "center_dist": abs((x1+x2)//2 - center_x),
                            "area": (x2-x1) * (y2-y1)
                        })

            if not candidates:
                logger.warning("No modal candidates found in preview")
                return None

            # Pick best candidate (most centered)
            best = min(candidates, key=lambda c: (c["center_dist"], -c["area"]))
            x, y, cw, ch = best["box"]

            logger.info(f"Modal detected at ({x}, {y}) size: {cw}x{ch}")

            # Add small padding
            padding = 5
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(w, x + cw + padding)
            y2 = min(h, y + ch + padding)

            # Crop the modal
            cropped = img[y1:y2, x1:x2]

            # Save cropped image
            cropped_path = image_path.replace(".png", "_modal.png")
            cv2.imwrite(cropped_path, cropped)
            logger.info(f"Modal cropped to {x2-x1}x{y2-y1}, saved: {cropped_path}")

            return cropped_path

        except Exception as e:
            logger.error(f"Error cropping preview modal: {e}")
            return None

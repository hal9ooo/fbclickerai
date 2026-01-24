from dataclasses import dataclass
from typing import List, Tuple, Any, Optional
import numpy as np
from rapidocr_onnxruntime import RapidOCR
import structlog
from PIL import Image
import cv2

logger = structlog.get_logger()

@dataclass
class TextLine:
    """Adapts RapidOCR result item to Surya-like interface."""
    text: str
    bbox: List[int]  # [x1, y1, x2, y2]
    confidence: float

@dataclass
class OCRResult:
    """Adapts RapidOCR full result to Surya-like interface."""
    text_lines: List[TextLine]

class OCREngine:
    """
    Wrapper around RapidOCR to provide a drop-in replacement for Surya OCR,
    optimized for low memory usage (<1GB RAM).
    """


    def __init__(self):
        logger.info("Initializing RapidOCR (ONNX Runtime)...")
        # Initialize RapidOCR with default options
        # We can tune parameters here if needed
        self.engine = RapidOCR()
        logger.info("RapidOCR initialized.")


    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image to improve OCR accuracy:
        1. Convert to grayscale
        2. Resize (upscale) if image is small
        3. Add padding
        """
        # Convert to grayscale if not already
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Upscale if image is small (width < 1000px usually benefits from 2x)
        # However for these cards, they seem to be cropped.
        # Let's upscale by 3x to see if it helps separation
        scale = 3.0
        # Use INTER_CUBIC for better quality resizing
        scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Adaptive Thresholding helps with varying lighting/contrast
        # It calculates threshold for small regions
        # blockSize=25 seems good for text size after 3x scaling
        # C=5 (reduced from 10) to catch faint text (closer to background brightness)
        binary = cv2.adaptiveThreshold(scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 5)

        # Add white padding
        # RapidOCR/PaddleOCR sometimes misses text at edges
        padding = 30
        padded = cv2.copyMakeBorder(binary, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        
        return padded

    def run_ocr(self, image: Any) -> List[OCRResult]:
        """
        Run OCR on the provided image.

        Args:
            image: Can be a PIL Image, numpy array, or path string.

        Returns:
            List containing one OCRResult (to match surya's [0] access pattern)
        """

        # Convert PIL Image to numpy array if needed
        img_array = image
        if isinstance(image, Image.Image):
            img_array = np.array(image)
            # PIL is RGB, OpenCV/RapidOCR expects BGR for color, or GRAY
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # If input is path, read it
        if isinstance(image, str):
            img_array = cv2.imread(image)
            
        if img_array is None:
            logger.error("Failed to load image for OCR")
            return [OCRResult(text_lines=[])]

        try:
            # Preprocess
            processed_img = self.preprocess_image(img_array)

            # result is a list of [box_points, text, score]
            # box_points is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # Note: rapidocr accepts numpy array
            result, elapse = self.engine(processed_img)

            text_lines = []
            if result:
                # We need to map coordinates back to original image space if we resized/padded
                scale_factor = 3.0
                padding = 30
                
                for item in result:
                    box_points = item[0]
                    text = item[1]
                    score = item[2]

                    # Calculate bounding box [min_x, min_y, max_x, max_y]
                    # And map back to original coordinates
                    xs = []
                    ys = []
                    for pt in box_points:
                        # Inverse of: new = (old * scale) + padding
                        # old = (new - padding) / scale
                        orig_x = (pt[0] - padding) / scale_factor
                        orig_y = (pt[1] - padding) / scale_factor
                        xs.append(orig_x)
                        ys.append(orig_y)
                        
                    x1, x2 = int(min(xs)), int(max(xs))
                    y1, y2 = int(min(ys)), int(max(ys))
                    
                    # Ensure coordinates are within valid range
                    x1 = max(0, x1)
                    y1 = max(0, y1)

                    text_lines.append(TextLine(
                        text=text,
                        bbox=[x1, y1, x2, y2],
                        confidence=score
                    ))

            return [OCRResult(text_lines=text_lines)]

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return [OCRResult(text_lines=[])]

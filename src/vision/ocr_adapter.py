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
            # PIL is RGB, OpenCV/RapidOCR expects BGR?
            # RapidOCR usually handles paths or numpy arrays.
            # If input is PIL RGB, convert to BGR for consistency if RapidOCR expects it,
            # though RapidOCR internal might handle it.
            # Looking at RapidOCR docs/code, it often uses opencv imread (BGR).
            # If we pass numpy array from PIL (RGB), we might need to swap channels.
            # Let's verify standard usage. RapidOCR supports numpy array.
            # If the results look weird, we might need to check BGR/RGB.
            # Usually cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        try:
            # result is a list of [box_points, text, score]
            # box_points is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            result, elapse = self.engine(img_array)

            text_lines = []
            if result:
                for item in result:
                    box_points = item[0]
                    text = item[1]
                    score = item[2]

                    # Calculate bounding box [min_x, min_y, max_x, max_y]
                    xs = [pt[0] for pt in box_points]
                    ys = [pt[1] for pt in box_points]
                    x1, x2 = int(min(xs)), int(max(xs))
                    y1, y2 = int(min(ys)), int(max(ys))

                    text_lines.append(TextLine(
                        text=text,
                        bbox=[x1, y1, x2, y2],
                        confidence=score
                    ))

            # Sort by Y coordinate to mimic Surya/reading order if needed
            # (RapidOCR usually returns in reading order but good to ensure)
            # text_lines.sort(key=lambda l: l.bbox[1])

            return [OCRResult(text_lines=text_lines)]

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return [OCRResult(text_lines=[])]

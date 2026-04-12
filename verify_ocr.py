
import sys
import os
import cv2
from src.vision.ocr_adapter import OCREngine

def test_ocr(image_path):
    if not os.path.exists(image_path):
        print(f"Error: File {image_path} not found.")
        return

    print(f"Testing OCR on {image_path}...")
    engine = OCREngine()
    
    # Run OCR
    # The adapter expects PIL image or path, let's pass path to be safe as per adapter logic
    # But adapter logic says: if isinstance(image, Image.Image): ... else (assumed numpy)
    # Let's use PIL to mimic full app usage
    from PIL import Image
    try:
        img = Image.open(image_path)
        results = engine.run_ocr(img)
        
        print(f"\nResults for {image_path}:")
        if results and results[0].text_lines:
            for line in results[0].text_lines:
                print(f"Text: '{line.text}' Conf: {line.confidence}")
        else:
            print("No text detected.")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_ocr.py <image_path>")
        # Default to one of the found images if not provided
        default_img = "c:/dev/fbclicker/data/screenshots/card_4_cropped.png"
        if os.path.exists(default_img):
            test_ocr(default_img)
    else:
        test_ocr(sys.argv[1])

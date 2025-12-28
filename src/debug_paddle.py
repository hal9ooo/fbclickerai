import traceback
try:
    print("Importing PaddleOCR...")
    from paddleocr import PaddleOCR
    print("Initializing PaddleOCR...")
    # Matches exactly the code in group_moderator.py
    engine = PaddleOCR(use_angle_cls=False, lang='it') 
    print("Success! Engine created.")
    
    print("Running test OCR on viewport_scan.png...")
    import os
    img_path = "/app/data/screenshots/viewport_scan.png"
    if os.path.exists(img_path):
        result = engine.ocr(img_path)
        print(f"OCR Result Type: {type(result)}")
        print(f"OCR Result Raw: {result}")
        print("OCR scanning SUCCESS verify pass.")
    else:
        print(f"Image not found at {img_path}")

except Exception:
    traceback.print_exc()

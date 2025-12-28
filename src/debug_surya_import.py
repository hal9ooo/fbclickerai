import sys
import os

print(f"Python: {sys.version}")
print(f"Path: {sys.path}")

try:
    print("Attempting to import surya...")
    import surya
    print(f"Surya module: {surya}")
    print(f"Surya file: {surya.__file__}")
    
    print("Attempting to import surya.ocr...")
    try:
        from surya.ocr import run_ocr
        print("Success: imported run_ocr")
    except ImportError as ie:
        print(f"Failed to import run_ocr: {ie}")
        print(f"Dir(surya): {dir(surya)}")
        
except ImportError as e:
    print(f"Failed to import surya: {e}")
    # Check if package exists in site-packages
    import site
    packages = site.getsitepackages()
    print(f"Site packages: {packages}")
    for p in packages:
        surya_path = os.path.join(p, 'surya')
        if os.path.exists(surya_path):
            print(f"Found surya at: {surya_path}")
            print(f"Contents: {os.listdir(surya_path)}")

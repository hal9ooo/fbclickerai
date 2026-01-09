"""
Simple gallery web server for viewing screenshots.
Runs on port 8081 and serves all screenshots as a responsive gallery.
"""
import os
import http.server
import socketserver
from pathlib import Path
from urllib.parse import unquote
import json
import logging
import io

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("WARNING: Pillow not installed. Thumbnails will be disabled.")

SCREENSHOTS_DIR = "/app/data/screenshots"
PORT = 8081

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GalleryServer")

# HTML template for the gallery
GALLERY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FBClicker Screenshots Gallery</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        
        h1 {
            text-align: center;
            margin-bottom: 10px;
            font-size: 2rem;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .stats {
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }
        
        .gallery {
            display: grid;
            /* Modified for ~3 columns on large screens (min 500px) */
            grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
            gap: 20px;
            max-width: 1800px; /* Increased max width */
            margin: 0 auto;
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 40px rgba(0,212,255,0.2);
            border-color: rgba(0,212,255,0.4);
        }
        
        .card img {
            width: 100%;
            height: 350px; /* Increased height for larger cards */
            object-fit: contain; /* Keep aspect ratio visible */
            background: #000;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .card .info {
            padding: 15px;
        }
        
        .card .name {
            font-weight: 600;
            font-size: 1.1rem;
            color: #fff;
            word-break: break-all;
            margin-bottom: 5px;
        }
        
        .card .meta {
            font-size: 0.85rem;
            color: #888;
            display: flex;
            justify-content: space-between;
        }
        
        /* Lightbox */
        .lightbox {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .lightbox.active {
            display: flex;
        }
        
        .lightbox img {
            max-width: 95%;
            max-height: 95%;
            object-fit: contain;
            box-shadow: 0 0 50px rgba(0,0,0,0.5);
        }
        
        .lightbox .close {
            position: fixed;
            top: 20px;
            right: 30px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
            z-index: 1001;
            width: 50px;
            height: 50px;
            text-align: center;
            line-height: 50px;
            background: rgba(0,0,0,0.5);
            border-radius: 50%;
        }
        
        .lightbox .nav {
            position: fixed;
            top: 50%;
            transform: translateY(-50%);
            font-size: 50px;
            color: #fff;
            cursor: pointer;
            padding: 20px;
            user-select: none;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            transition: background 0.2s;
        }
        
        .lightbox .nav:hover {
            background: rgba(0,0,0,0.6);
        }
        
        .lightbox .prev { left: 20px; }
        .lightbox .next { right: 20px; }
        
        .empty {
            text-align: center;
            padding: 60px;
            color: #666;
            font-size: 1.2rem;
            grid-column: 1 / -1;
        }
        
        .refresh-btn {
            display: block;
            margin: 0 auto 20px;
            padding: 10px 30px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            border: none;
            border-radius: 25px;
            color: #fff;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.2s;
            box-shadow: 0 4px 15px rgba(0,212,255,0.3);
        }
        
        .refresh-btn:hover {
            transform: scale(1.05);
        }
    </style>
</head>
<body>
    <h1>📸 FBClicker Screenshots</h1>
    <p class="stats" id="stats">Loading...</p>
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Gallery</button>
    
    <div class="gallery" id="gallery"></div>
    
    <div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
        <span class="close">&times;</span>
        <span class="nav prev" onclick="navigate(-1, event)">&lt;</span>
        <img id="lightbox-img" src="" alt="">
        <span class="nav next" onclick="navigate(1, event)">&gt;</span>
    </div>
    
    <script>
        let images = [];
        let currentIndex = 0;
        
        async function loadGallery() {
            try {
                const response = await fetch('/api/screenshots');
                images = await response.json();
                
                document.getElementById('stats').textContent = `${images.length} screenshots found`;
                
                const gallery = document.getElementById('gallery');
                
                if (images.length === 0) {
                    gallery.innerHTML = '<div class="empty">No screenshots yet. Run the bot to generate some!</div>';
                    return;
                }
                
                gallery.innerHTML = images.map((img, i) => `
                    <div class="card" onclick="openLightbox(${i})">
                        <img src="/thumbnail/${img.name}" loading="lazy" alt="${img.name}" onerror="this.src='/screenshots/${img.name}'">
                        <div class="info">
                            <div class="name">${img.name}</div>
                            <div class="meta">
                                <span>${img.size} KB</span>
                                <span>${img.modified}</span>
                            </div>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error("Error loading gallery:", e);
                document.getElementById('stats').textContent = "Error loading gallery data";
            }
        }
        
        function openLightbox(index) {
            currentIndex = index;
            const img = images[index];
            const lightboxImg = document.getElementById('lightbox-img');
            
            // Show loading placeholder or thumb first?
            // For now just load full res
            lightboxImg.src = '/screenshots/' + img.name;
            document.getElementById('lightbox').classList.add('active');
        }
        
        function closeLightbox(event) {
            if (event.target.classList.contains('lightbox') || event.target.classList.contains('close')) {
                document.getElementById('lightbox').classList.remove('active');
                document.getElementById('lightbox-img').src = ''; // Clear image
            }
        }
        
        function navigate(delta, event) {
            event.stopPropagation();
            currentIndex = (currentIndex + delta + images.length) % images.length;
            document.getElementById('lightbox-img').src = '/screenshots/' + images[currentIndex].name;
        }
        
        document.addEventListener('keydown', (e) => {
            if (!document.getElementById('lightbox').classList.contains('active')) return;
            if (e.key === 'Escape') {
                document.getElementById('lightbox').classList.remove('active');
                document.getElementById('lightbox-img').src = '';
            }
            if (e.key === 'ArrowLeft') navigate(-1, e);
            if (e.key === 'ArrowRight') navigate(1, e);
        });
        
        loadGallery();
    </script>
</body>
</html>
"""


class GalleryHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler for the gallery server."""
    
    def __init__(self, *args, **kwargs):
        self.screenshots_dir = SCREENSHOTS_DIR
        super().__init__(*args, directory=self.screenshots_dir, **kwargs)
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(GALLERY_HTML.encode())
            
        elif self.path == '/api/screenshots':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            screenshots = []
            screenshots_path = Path(self.screenshots_dir)
            
            if screenshots_path.exists():
                for f in sorted(screenshots_path.glob('*.png'), key=os.path.getmtime, reverse=True):
                    try:
                        stat = f.stat()
                        screenshots.append({
                            'name': f.name,
                            'size': round(stat.st_size / 1024, 1),
                            'modified': self._format_time(stat.st_mtime)
                        })
                    except Exception as e:
                        logger.error(f"Error reading file stats for {f}: {e}")
            
            self.wfile.write(json.dumps(screenshots).encode())
            
        elif self.path.startswith('/thumbnail/'):
            # Generate and serve thumbnail
            filename = unquote(self.path[11:])  # Remove '/thumbnail/'
            filepath = Path(self.screenshots_dir) / filename
            
            if not filepath.exists():
                self.send_error(404, 'File not found')
                return

            if not HAS_PILLOW:
                # Fallback to full image if Pillow is missing
                self._serve_file(filepath)
                return
            
            try:
                # Create on-the-fly thumbnail
                with Image.open(filepath) as img:
                    # Convert to RGB (in case of RGBA/P palette) for JPEG
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    # Resize to optimized width (e.g., 600px width)
                    target_width = 800
                    w_percent = (target_width / float(img.size[0]))
                    h_size = int((float(img.size[1]) * float(w_percent)))
                    
                    # Using resize() directly
                    img_resized = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
                    
                    # Save to memory buffer
                    buf = io.BytesIO()
                    img_resized.save(buf, format='JPEG', quality=85)
                    buf.seek(0)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    # Cache for 1 hour
                    self.send_header('Cache-Control', 'max-age=3600')
                    self.end_headers()
                    self.wfile.write(buf.read())
                    
            except Exception as e:
                logger.error(f"Thumbnail generation failed for {filename}: {e}")
                # Fallback to original file on error
                self._serve_file(filepath)
                
        elif self.path.startswith('/screenshots/'):
            # Serve actual screenshot files
            filename = unquote(self.path[13:])  # Remove '/screenshots/'
            filepath = Path(self.screenshots_dir) / filename
            self._serve_file(filepath)
        else:
            self.send_error(404, 'Not found')
            
    def _serve_file(self, filepath: Path):
        if filepath.exists() and filepath.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            self.send_response(200)
            content_type = 'image/png' if filepath.suffix == '.png' else 'image/jpeg'
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(filepath.stat().st_size))
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, 'File not found')
    
    def _format_time(self, timestamp):
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    def log_message(self, format, *args):
        # Suppress standard logging to avoid clutter
        if logger.isEnabledFor(logging.DEBUG):
             super().log_message(format, *args)


def run_server():
    """Run the gallery server."""
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    
    # Allow address reuse to avoid "Address already in use" errors on restart
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), GalleryHandler) as httpd:
        print(f"📸 Gallery server running at http://0.0.0.0:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()

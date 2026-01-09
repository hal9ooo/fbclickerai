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
import sys

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("WARNING: Pillow not installed. Thumbnails will be disabled.", flush=True)

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
            grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
            gap: 20px;
            max-width: 1800px;
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
            height: 350px;
            object-fit: contain;
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
        
        .breadcrumb {
            max-width: 1800px;
            margin: 0 auto 20px;
            font-size: 1.2rem;
            color: #ccc;
            display: none; /* Hidden by default */
        }
        
        .back-btn {
            background: none;
            border: none;
            color: #00d4ff;
            font-size: 1.2rem;
            cursor: pointer;
            text-decoration: underline;
            padding: 0;
        }
        
        .folder .name {
            font-size: 1.4rem;
            color: #00d4ff;
        }
    </style>
</head>
<body>
    <h1>📸 FBClicker Screenshots Gallery</h1>
    <p class="stats" id="stats">Loading...</p>
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Gallery</button>
    
    <div class="breadcrumb" id="breadcrumb"></div>
    <div class="gallery" id="gallery"></div>
    
    <div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
        <span class="close">&times;</span>
        <span class="nav prev" onclick="navigate(-1, event)">&lt;</span>
        <img id="lightbox-img" src="" alt="">
        <span class="nav next" onclick="navigate(1, event)">&gt;</span>
    </div>
    
    <script>
        let images = [];
        let groups = {}; // { "0": [img1, img2], "1": [...] }
        let currentView = 'collections'; // 'collections' | 'detail'
        let currentGroupId = null;
        let currentIndex = 0; // For lightbox
        
        // Regex to match card series (card_N or cardN, max 2 digits)
        // Matches: card_0, card_13, debug_..._card0, etc.
        const SERIES_REGEX = /card_?(\d{1,2})/i;

        async function loadGallery() {
            try {
                const response = await fetch('/api/screenshots');
                images = await response.json();
                
                // Group images
                groups = {};
                let uncategorized = [];
                
                images.forEach(img => {
                    const match = img.name.match(SERIES_REGEX);
                    if (match && match[1]) {
                        const id = match[1];
                        if (!groups[id]) groups[id] = [];
                        groups[id].push(img);
                    } else {
                        uncategorized.push(img);
                    }
                });
                
                // Sort groups by ID (numeric)
                // If there are uncategorized images, we can add them to a "Misc" group if desired
                if (uncategorized.length > 0) {
                    groups['Misc'] = uncategorized;
                }
                
                document.getElementById('stats').textContent = `${images.length} screenshots found, ${Object.keys(groups).length} series`;
                
                render();
            } catch (e) {
                console.error("Error loading gallery:", e);
                document.getElementById('stats').textContent = "Error loading gallery data";
            }
        }
        
        function render() {
            const gallery = document.getElementById('gallery');
            const breadcrumb = document.getElementById('breadcrumb');
            gallery.innerHTML = '';
            
            if (currentView === 'collections') {
                renderCollections(gallery);
                if (breadcrumb) breadcrumb.style.display = 'none';
            } else {
                renderDetail(gallery);
                if (breadcrumb) {
                    breadcrumb.style.display = 'block';
                    breadcrumb.innerHTML = `<button class="back-btn" onclick="goBack()">← Back to Collections</button> / Series ${currentGroupId}`;
                }
            }
        }
        
        function renderCollections(container) {
            const sortedKeys = Object.keys(groups).sort((a, b) => {
                if (a === 'Misc') return 1;
                if (b === 'Misc') return -1;
                return parseInt(b) - parseInt(a); // Newest series first (assuming higher ID is newer)
            });

            if (sortedKeys.length === 0) {
                container.innerHTML = '<div class="empty">No images found.</div>';
                return;
            }

            container.innerHTML = sortedKeys.map(id => {
                const groupImages = groups[id];
                // Try to find the main "card_N.png" for thumbnail, otherwise use first
                let thumbImg = groupImages.find(img => img.name === `card_${id}.png` || img.name === `card${id}.png`) || groupImages[0];
                
                return `
                <div class="card folder" onclick="openGroup('${id}')">
                    <img src="/thumbnail/${thumbImg.name}" loading="lazy" alt="Series ${id}" onerror="this.src='/screenshots/${thumbImg.name}'">
                    <div class="info">
                        <div class="name">${id === 'Misc' ? 'Uncategorized' : 'Card Series ' + id}</div>
                        <div class="meta">
                            <span>${groupImages.length} items</span>
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }
        
        function renderDetail(container) {
            const groupImages = groups[currentGroupId];
            if (!groupImages) return;
            
            container.innerHTML = groupImages.map((img, i) => `
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
        }
        
        function openGroup(id) {
            currentGroupId = id;
            currentView = 'detail';
            render();
            window.scrollTo(0, 0);
        }
        
        function goBack() {
            currentView = 'collections';
            currentGroupId = null;
            render();
        }
        
        function openLightbox(index) {
            // Need to map index relative to current filtered view if in detail mode?
            // Actually, for lightbox navigation to work across the whole group, we should probably ONLY let it navigate within the group.
            
            // Let's re-map the global 'currentIndex' logic to strictly follow the current displayed list.
            // Simplified: we pass the index within the groupImages array.
            
            currentIndex = index;
            const groupImages = groups[currentGroupId];
            const img = groupImages[index];
            
            const lightboxImg = document.getElementById('lightbox-img');
            lightboxImg.src = '/screenshots/' + img.name;
            document.getElementById('lightbox').classList.add('active');
        }
        
        function navigate(delta, event) {
            event.stopPropagation();
            if (currentView !== 'detail' || !currentGroupId) return;
            
            const groupImages = groups[currentGroupId];
            currentIndex = (currentIndex + delta + groupImages.length) % groupImages.length;
            document.getElementById('lightbox-img').src = '/screenshots/' + groupImages[currentIndex].name;
        }
        
        // ... (Close Lightbox logic remains same) ...
        function closeLightbox(event) {
            if (event.target.classList.contains('lightbox') || event.target.classList.contains('close')) {
                document.getElementById('lightbox').classList.remove('active');
                document.getElementById('lightbox-img').src = '';
            }
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
    def __init__(self, *args, **kwargs):
        self.screenshots_dir = SCREENSHOTS_DIR
        super().__init__(*args, directory=self.screenshots_dir, **kwargs)

    def do_GET(self):
        # Debugging: print to stderr to be seen in docker logs
        print(f"REQUEST: {self.path}", file=sys.stderr, flush=True)
        
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Cache-Control', 'no-store, must-revalidate')
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
            filename = unquote(self.path[11:])
            filepath = Path(self.screenshots_dir) / filename
            
            if not filepath.exists():
                self.send_error(404, 'File not found')
                return

            if not HAS_PILLOW:
                self._serve_file(filepath)
                return
            
            try:
                with Image.open(filepath) as img:
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    target_width = 800
                    ratio = target_width / float(img.size[0])
                    target_height = int(float(img.size[1]) * ratio)
                    
                    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    buf = io.BytesIO()
                    img_resized.save(buf, format='JPEG', quality=85)
                    buf.seek(0)
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Cache-Control', 'max-age=3600')
                    self.end_headers()
                    self.wfile.write(buf.read())
            except Exception as e:
                print(f"THUMBNAIL ERROR for {filename}: {e}", file=sys.stderr, flush=True)
                self._serve_file(filepath)
                
        elif self.path.startswith('/screenshots/'):
            filename = unquote(self.path[13:])
            filepath = Path(self.screenshots_dir) / filename
            self._serve_file(filepath)
        else:
            # For any other path, use standard handler or return 404
            super().do_GET()
            
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

def run_server():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), GalleryHandler) as httpd:
        print(f"📸 Gallery server running at http://0.0.0.0:{PORT}", flush=True)
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()

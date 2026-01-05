"""Stealth browser implementation with advanced anti-detection measures - ASYNC version."""
import os
import json
import random
import hashlib
from pathlib import Path
from typing import Optional, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import structlog

from src.config import settings

logger = structlog.get_logger()


# Updated User Agents (Chrome 131+, Firefox 133+, Edge - December 2024)
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Realistic viewport sizes (common monitor resolutions)
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1680, "height": 1050},
    {"width": 1280, "height": 720},
]

# Tracker domains to block
BLOCKED_DOMAINS = [
    "**/datadome.co/**",
    "**/google-analytics.com/**",
    "**/googletagmanager.com/**",
    "**/facebook.com/tr/**",  # Facebook Pixel
    "**/connect.facebook.net/signals/**",
    "**/perimeterx.net/**",
    "**/imperva.com/**",
    "**/kasada.io/**",
]


class StealthBrowser:
    """Browser with advanced stealth mode to avoid detection - ASYNC version."""
    
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session_path = Path(settings.sessions_dir) / "facebook_session.json"
        self._fingerprint_path = Path(settings.sessions_dir) / "fingerprint.json"
        self._fingerprint: dict = {}
        
    def _load_or_create_fingerprint(self) -> dict:
        """Load existing fingerprint or create a new persistent one."""
        if self._fingerprint_path.exists():
            try:
                with open(self._fingerprint_path, 'r') as f:
                    fingerprint = json.load(f)
                logger.info("Loaded existing fingerprint", 
                           user_agent=fingerprint.get('user_agent', '')[:50])
                return fingerprint
            except Exception as e:
                logger.warning("Failed to load fingerprint, creating new", error=str(e))
        
        # Create new fingerprint
        fingerprint = {
            "user_agent": random.choice(USER_AGENTS),
            "viewport": random.choice(VIEWPORTS),
            "hardware_concurrency": random.choice([4, 8, 12, 16]),
            "device_memory": random.choice([4, 8, 16, 32]),
            "platform": "Win32",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": random.choice([
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)",
            ]),
            "canvas_noise": random.uniform(0.0001, 0.001),
            "audio_noise": random.uniform(0.0001, 0.0005),
            "languages": ["it-IT", "it", "en-US", "en"],
        }
        
        # Save fingerprint
        os.makedirs(self._fingerprint_path.parent, exist_ok=True)
        with open(self._fingerprint_path, 'w') as f:
            json.dump(fingerprint, f, indent=2)
        
        logger.info("Created new fingerprint", user_agent=fingerprint['user_agent'][:50])
        return fingerprint
    
    def _get_stealth_scripts(self) -> str:
        """Generate comprehensive anti-detection JavaScript."""
        fp = self._fingerprint
        
        return f"""
        // ===== NAVIGATOR PROPERTIES =====
        
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined
        }});
        
        // Hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {fp.get('hardware_concurrency', 8)}
        }});
        
        // Device memory
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {fp.get('device_memory', 8)}
        }});
        
        // Platform
        Object.defineProperty(navigator, 'platform', {{
            get: () => '{fp.get('platform', 'Win32')}'
        }});
        
        // Languages
        Object.defineProperty(navigator, 'languages', {{
            get: () => {json.dumps(fp.get('languages', ['it-IT', 'it', 'en']))}
        }});
        
        // ===== PLUGINS (realistic browser plugins) =====
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = [
                    {{
                        name: 'Chrome PDF Plugin',
                        description: 'Portable Document Format',
                        filename: 'internal-pdf-viewer',
                        length: 1
                    }},
                    {{
                        name: 'Chrome PDF Viewer', 
                        description: '',
                        filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                        length: 1
                    }},
                    {{
                        name: 'Native Client',
                        description: '',
                        filename: 'internal-nacl-plugin',
                        length: 2
                    }}
                ];
                plugins.item = (i) => plugins[i] || null;
                plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                plugins.refresh = () => {{}};
                return plugins;
            }}
        }});
        
        // ===== CHROME RUNTIME =====
        window.chrome = {{
            runtime: {{
                connect: () => {{}},
                sendMessage: () => {{}},
                onMessage: {{ addListener: () => {{}} }}
            }},
            app: {{
                isInstalled: false,
                InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }},
                RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }}
            }}
        }};
        
        // ===== PERMISSIONS =====
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({{ state: Notification.permission }}) :
                originalQuery(parameters)
        );
        
        // ===== WEBGL FINGERPRINT SPOOFING =====
        const getParameterOriginal = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            // UNMASKED_VENDOR_WEBGL
            if (param === 37445) return '{fp.get('webgl_vendor', 'Google Inc. (NVIDIA)')}';
            // UNMASKED_RENDERER_WEBGL  
            if (param === 37446) return '{fp.get('webgl_renderer', 'ANGLE (NVIDIA GeForce RTX 3060)')}';
            return getParameterOriginal.call(this, param);
        }};
        
        // WebGL2 as well
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const getParameter2Original = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {{
                if (param === 37445) return '{fp.get('webgl_vendor', 'Google Inc. (NVIDIA)')}';
                if (param === 37446) return '{fp.get('webgl_renderer', 'ANGLE (NVIDIA GeForce RTX 3060)')}';
                return getParameter2Original.call(this, param);
            }};
        }}
        
        // ===== CANVAS FINGERPRINT NOISE =====
        const canvasNoise = {fp.get('canvas_noise', 0.0005)};
        
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            if (type === 'image/png' || type === undefined) {{
                const canvas = this;
                const ctx = canvas.getContext('2d');
                if (ctx && canvas.width > 0 && canvas.height > 0) {{
                    try {{
                        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {{
                            // Add subtle noise to RGB channels
                            imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + (Math.random() - 0.5) * canvasNoise * 255));
                            imageData.data[i+1] = Math.max(0, Math.min(255, imageData.data[i+1] + (Math.random() - 0.5) * canvasNoise * 255));
                            imageData.data[i+2] = Math.max(0, Math.min(255, imageData.data[i+2] + (Math.random() - 0.5) * canvasNoise * 255));
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
            }}
            return originalToDataURL.apply(this, arguments);
        }};
        
        // ===== AUDIO CONTEXT FINGERPRINT =====
        const audioNoise = {fp.get('audio_noise', 0.0003)};
        
        if (typeof AudioBuffer !== 'undefined') {{
            const originalGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(channel) {{
                const array = originalGetChannelData.call(this, channel);
                for (let i = 0; i < array.length; i++) {{
                    array[i] += (Math.random() - 0.5) * audioNoise;
                }}
                return array;
            }};
        }}
        
        // ===== AUTOMATION DETECTION =====
        // Hide Playwright/CDP traces
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        
        // Remove automation-related properties
        ['__webdriver_script_fn', '__driver_evaluate', '__webdriver_evaluate', 
         '__selenium_evaluate', '__fxdriver_evaluate', '__driver_unwrapped',
         '__webdriver_unwrapped', '__selenium_unwrapped', '__fxdriver_unwrapped',
         '__webdriver_script_func'].forEach(prop => {{
            try {{ delete window[prop]; }} catch(e) {{}}
            try {{ delete document[prop]; }} catch(e) {{}}
        }});
        
        // ===== SCREEN PROPERTIES =====
        const viewport = {json.dumps(fp.get('viewport', {'width': 1920, 'height': 1080}))};
        Object.defineProperty(screen, 'availWidth', {{ get: () => viewport.width }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => viewport.height }});
        Object.defineProperty(screen, 'width', {{ get: () => viewport.width }});
        Object.defineProperty(screen, 'height', {{ get: () => viewport.height }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => 24 }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => 24 }});
        
        console.log('[Stealth] Anti-detection scripts loaded');
        """
    
    async def _setup_request_blocking(self):
        """Block tracking and fingerprinting requests."""
        if not self._page:
            return
            
        for pattern in BLOCKED_DOMAINS:
            try:
                await self._page.route(pattern, lambda route: route.abort())
                logger.debug("Blocking requests to", pattern=pattern)
            except Exception as e:
                logger.warning("Failed to block pattern", pattern=pattern, error=str(e))
    
    async def start(self) -> Page:
        """Start the browser with advanced stealth settings."""
        logger.info("Starting stealth browser with enhanced anti-detection")
        
        # Load or create persistent fingerprint
        self._fingerprint = self._load_or_create_fingerprint()
        
        self._playwright = await async_playwright().start()
        
        # Select proxy if configured
        proxy_config = None
        if hasattr(settings, 'proxy_list') and settings.proxy_list:
            proxy = random.choice(settings.proxy_list)
            proxy_config = {"server": proxy}
            logger.info("Using proxy", proxy=proxy[:30] + "...")
        
        # Launch browser with enhanced anti-detection args
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--disable-extensions",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-breakpad",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
            # GPU args for consistent fingerprint
            "--enable-webgl",
            "--use-gl=angle",
            "--use-angle=default",
        ]
        
        self._browser = await self._playwright.chromium.launch(
            headless=settings.headless,
            slow_mo=settings.slow_mo,
            args=launch_args
        )
        
        # Use fingerprint values
        user_agent = self._fingerprint['user_agent']
        viewport = self._fingerprint['viewport']
        
        # Create context with session persistence
        context_options = {
            "user_agent": user_agent,
            "viewport": viewport,
            "locale": "it-IT",
            "timezone_id": "Europe/Rome",
            "permissions": ["geolocation"],
            "geolocation": {"latitude": 41.9028, "longitude": 12.4964},  # Rome
            "color_scheme": "light",
            "reduced_motion": "no-preference",
            "has_touch": False,
            "is_mobile": False,
            "device_scale_factor": 1,
        }
        
        if proxy_config:
            context_options["proxy"] = proxy_config
        
        # Load existing session if available
        if self._session_path.exists():
            logger.info("Loading existing session", path=str(self._session_path))
            self._context = await self._browser.new_context(
                storage_state=str(self._session_path),
                **context_options
            )
        else:
            self._context = await self._browser.new_context(**context_options)
        
        self._page = await self._context.new_page()
        
        # Inject comprehensive anti-detection scripts
        await self._page.add_init_script(self._get_stealth_scripts())
        
        # Setup request blocking for trackers
        await self._setup_request_blocking()
        
        logger.info("Stealth browser started", 
                   user_agent=user_agent[:50], 
                   viewport=viewport,
                   fingerprint_hash=hashlib.md5(json.dumps(self._fingerprint).encode()).hexdigest()[:8])
        return self._page
    
    async def save_session(self, force: bool = False):
        """Save browser session for reuse.
        
        Args:
            force: If True, save session even if auth cookies are missing.
                   If False (default), only save if c_user and xs cookies are present.
        """
        if self._context:
            # Check for auth cookies before saving
            cookies = await self._context.cookies()
            cookie_names = [c['name'] for c in cookies]
            has_auth = 'c_user' in cookie_names and 'xs' in cookie_names
            
            if not has_auth and not force:
                logger.warning("Skipping session save - auth cookies missing", 
                             cookies=cookie_names)
                return
            
            os.makedirs(self._session_path.parent, exist_ok=True)
            await self._context.storage_state(path=str(self._session_path))
            logger.info("Session saved", path=str(self._session_path), 
                       cookies_count=len(cookies), has_auth=has_auth)
    
    async def screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot and return the file path."""
        if not self._page:
            raise RuntimeError("Browser not started")
        
        os.makedirs(settings.screenshots_dir, exist_ok=True)
        path = os.path.join(settings.screenshots_dir, f"{name}.png")
        await self._page.screenshot(path=path, full_page=False)
        logger.info("Screenshot saved", path=path)
        return path
    
    @property
    def page(self) -> Page:
        """Get the current page."""
        if not self._page:
            raise RuntimeError("Browser not started")
        return self._page
    
    @property
    def fingerprint(self) -> dict:
        """Get the current fingerprint."""
        return self._fingerprint
    
    async def close(self):
        """Close the browser and save session."""
        logger.info("Closing browser")
        try:
            if self._context:
                await self.save_session()
                await self._context.close()
        except Exception as e:
            logger.warning("Error closing context", error=str(e))
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.warning("Error closing browser", error=str(e))
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("Error stopping playwright", error=str(e))

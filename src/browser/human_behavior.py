"""Human-like behavior simulation for browser automation - ASYNC version with advanced patterns."""
import asyncio
import random
import math
from typing import Tuple, List
from playwright.async_api import Page
import structlog

logger = structlog.get_logger()


def gaussian_random(mean: float, std: float, min_val: float = 0.1) -> float:
    """Generate gaussian-distributed random number with minimum floor."""
    # Box-Muller transform for gaussian distribution
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    value = mean + z * std
    return max(min_val, value)


def bezier_point(t: float, p0: Tuple[float, float], p1: Tuple[float, float], 
                 p2: Tuple[float, float], p3: Tuple[float, float]) -> Tuple[float, float]:
    """Calculate point on cubic Bézier curve at parameter t."""
    x = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
    y = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
    return (x, y)


def generate_bezier_path(start: Tuple[int, int], end: Tuple[int, int], 
                         num_points: int = 15) -> List[Tuple[int, int]]:
    """Generate a natural curved mouse path using Bézier curve."""
    # Calculate distance and direction
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.sqrt(dx*dx + dy*dy)
    
    # Generate control points with some randomness
    # Control points create the curve shape
    offset_range = distance * 0.3  # 30% of distance for curve amplitude
    
    # Random perpendicular offset for natural curves
    perpendicular = (dy / (distance + 0.001), -dx / (distance + 0.001))
    
    p0 = (float(start[0]), float(start[1]))
    p3 = (float(end[0]), float(end[1]))
    
    # Control point 1: about 1/3 of the way with curve offset
    curve_offset_1 = random.uniform(-offset_range, offset_range)
    p1 = (
        start[0] + dx * 0.3 + perpendicular[0] * curve_offset_1,
        start[1] + dy * 0.3 + perpendicular[1] * curve_offset_1
    )
    
    # Control point 2: about 2/3 of the way with different offset
    curve_offset_2 = random.uniform(-offset_range * 0.5, offset_range * 0.5)
    p2 = (
        start[0] + dx * 0.7 + perpendicular[0] * curve_offset_2,
        start[1] + dy * 0.7 + perpendicular[1] * curve_offset_2
    )
    
    # Generate points along the curve with variable density
    # More points at start (acceleration) and end (deceleration)
    path = []
    for i in range(num_points):
        # Non-linear t for ease-in-out effect
        linear_t = i / (num_points - 1)
        # Ease-in-out cubic
        if linear_t < 0.5:
            t = 4 * linear_t * linear_t * linear_t
        else:
            t = 1 - pow(-2 * linear_t + 2, 3) / 2
        
        point = bezier_point(t, p0, p1, p2, p3)
        path.append((int(point[0]), int(point[1])))
    
    return path


class HumanBehavior:
    """Simulates human-like browser interactions with advanced patterns - ASYNC version."""
    
    def __init__(self, page: Page):
        self.page = page
        self._last_position = None
    
    async def random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0, use_gaussian: bool = True):
        """Wait for a random amount of time with gaussian or uniform distribution."""
        if use_gaussian:
            # Gaussian with mean at center of range
            mean = (min_sec + max_sec) / 2
            std = (max_sec - min_sec) / 4
            delay = gaussian_random(mean, std, min_sec)
            delay = min(delay, max_sec * 1.2)  # Cap at 120% of max
        else:
            delay = random.uniform(min_sec, max_sec)
        
        await asyncio.sleep(delay)
    
    async def thinking_pause(self):
        """Simulate occasional thinking pauses that humans naturally have."""
        if random.random() < 0.15:  # 15% chance of thinking pause
            pause_duration = gaussian_random(2.0, 1.0, 0.5)
            logger.debug("Thinking pause", duration=f"{pause_duration:.2f}s")
            await asyncio.sleep(pause_duration)
    
    async def human_type(self, selector: str, text: str):
        """Type text with human-like delays between keystrokes."""
        element = self.page.locator(selector)
        await element.click()
        await self.random_delay(0.2, 0.5)
        
        for i, char in enumerate(text):
            # Variable typing speed based on character
            if char in ' \n\t':
                delay = random.randint(80, 200)  # Longer for spaces
            elif char.isupper():
                delay = random.randint(100, 180)  # Longer for uppercase (shift key)
            else:
                delay = random.randint(40, 120)
            
            await element.type(char, delay=delay)
            
            # Occasional longer pause (simulating reading/thinking)
            if random.random() < 0.08:  # 8% chance
                await self.random_delay(0.3, 0.8)
            
            # Small chance of faster burst typing
            if random.random() < 0.05:  # 5% chance of speed burst
                for _ in range(min(3, len(text) - i - 1)):
                    if i + 1 < len(text):
                        await element.type(text[i+1], delay=random.randint(20, 50))
                        i += 1
    
    async def human_click(self, x: int, y: int):
        """Click at coordinates with natural movement and randomization."""
        # Add small random offset (humans aren't perfectly accurate)
        jitter_x = int(gaussian_random(0, 2, -5))
        jitter_y = int(gaussian_random(0, 2, -5))
        
        final_x = x + jitter_x
        final_y = y + jitter_y
        
        # Move mouse naturally using Bézier curve
        await self._move_mouse_bezier(final_x, final_y)
        
        # Small delay before click (reaction time)
        await self.random_delay(0.08, 0.25)
        
        # Variable click duration
        click_delay = random.randint(50, 150)
        await self.page.mouse.click(final_x, final_y, delay=click_delay)
        
        # Update last position
        self._last_position = (final_x, final_y)
        
        logger.info("Human click performed", x=final_x, y=final_y)
        
        # Occasional post-click thinking pause
        await self.thinking_pause()
    
    async def _move_mouse_bezier(self, target_x: int, target_y: int):
        """Move mouse in a natural Bézier curve to target position."""
        viewport = self.page.viewport_size
        
        # Get start position
        if self._last_position:
            start_x, start_y = self._last_position
        else:
            # Start from random position near center if unknown
            start_x = viewport["width"] // 2 + random.randint(-100, 100)
            start_y = viewport["height"] // 2 + random.randint(-100, 100)
        
        # Calculate distance
        distance = math.sqrt((target_x - start_x)**2 + (target_y - start_y)**2)
        
        # Number of points based on distance (more for longer distances)
        num_points = max(8, min(25, int(distance / 30)))
        
        # Generate Bézier path
        path = generate_bezier_path((start_x, start_y), (target_x, target_y), num_points)
        
        # Move along path with variable speed
        for i, (x, y) in enumerate(path):
            await self.page.mouse.move(x, y)
            
            # Variable delay - slower at start and end (acceleration/deceleration)
            progress = i / len(path)
            if progress < 0.2 or progress > 0.8:
                delay = random.uniform(0.02, 0.05)  # Slower at edges
            else:
                delay = random.uniform(0.008, 0.025)  # Faster in middle
            
            await asyncio.sleep(delay)
    
    async def _move_mouse_natural(self, target_x: int, target_y: int):
        """Legacy method - now wraps Bézier movement."""
        await self._move_mouse_bezier(target_x, target_y)
    
    async def human_scroll(self, direction: str = "down", amount: int = None):
        """Scroll page in a human-like manner with variable speed."""
        if amount is None:
            amount = int(gaussian_random(350, 100, 150))
        
        if direction == "down":
            delta = amount
        else:
            delta = -amount
        
        # Scroll in small increments with variable sizes
        remaining = abs(delta)
        sign = 1 if delta > 0 else -1
        
        while remaining > 0:
            # Random chunk size (60-150 pixels)
            chunk = min(remaining, int(gaussian_random(90, 30, 40)))
            await self.page.mouse.wheel(0, sign * chunk)
            remaining -= chunk
            
            # Variable delay between scroll chunks
            await self.random_delay(0.03, 0.12, use_gaussian=True)
        
        logger.info("Human scroll performed", direction=direction, amount=amount)
        
        # Small post-scroll delay (reading)
        await self.random_delay(0.2, 0.5)
    
    async def look_around(self):
        """Simulate looking around the page (random mouse movements and scrolls)."""
        viewport = self.page.viewport_size
        
        # Random number of "look around" actions
        for _ in range(random.randint(2, 4)):
            # Move to random position (avoid edges)
            margin = 150
            x = random.randint(margin, viewport["width"] - margin)
            y = random.randint(margin, viewport["height"] - margin)
            await self._move_mouse_bezier(x, y)
            
            await self.random_delay(0.3, 0.8)
            
            # Maybe scroll a bit
            if random.random() < 0.3:
                direction = random.choice(["up", "down"])
                await self.human_scroll(direction, random.randint(50, 150))
    
    async def micro_movements(self):
        """Small micro-movements that humans naturally make."""
        if not self._last_position:
            return
        
        x, y = self._last_position
        
        # Small random movements (1-5 pixels)
        for _ in range(random.randint(1, 3)):
            dx = random.randint(-5, 5)
            dy = random.randint(-5, 5)
            await self.page.mouse.move(x + dx, y + dy)
            await asyncio.sleep(random.uniform(0.05, 0.15))
        
        # Return to original position
        await self.page.mouse.move(x, y)

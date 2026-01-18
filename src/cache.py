"""Cache for storing pending member request decisions."""
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path
import structlog

from src.config import settings

logger = structlog.get_logger()

CACHE_FILE = Path(settings.data_dir) / "decisions_cache.json"


@dataclass
class PendingRequest:
    """A member request pending decision."""
    name: str
    notified_at: str
    decision: Optional[str] = None  # None, "approve", or "decline"
    executed: bool = False
    extra_info: Optional[str] = None
    card_hash: Optional[str] = None  # Perceptual hash of card image
    preview_path: Optional[str] = None  # Path to preview screenshot
    action_buttons: Optional[Dict[str, List[int]]] = None  # {'approve': [x,y], 'decline': [x,y]}
    cropped_path: Optional[str] = None  # Path to cropped card image (text bbox only)
    is_unanswered: bool = False  # Whether the user hasn't answered questions


class DecisionCache:
    """Manages the cache of pending member request decisions."""
    
    def __init__(self):
        self._cache: Dict[str, PendingRequest] = {}
        self._hash_cache: Dict[str, str] = {}  # hash -> name mapping for quick lookup
        self._load()
    
    def _get_key(self, name: str) -> str:
        """Generate a unique key for a member name."""
        # Normalize name for consistent matching
        return name.strip().lower()
    
    def _load(self):
        """Load cache from disk."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, value in data.get("pending", {}).items():
                        self._cache[key] = PendingRequest(**value)
                        # Rebuild hash cache
                        if self._cache[key].card_hash:
                            self._hash_cache[self._cache[key].card_hash] = self._cache[key].name
                logger.info("Cache loaded", count=len(self._cache))
            except Exception as e:
                logger.error("Failed to load cache", error=str(e))
                self._cache = {}
        else:
            logger.info("No existing cache, starting fresh")
    
    def _save(self):
        """Save cache to disk."""
        os.makedirs(CACHE_FILE.parent, exist_ok=True)
        try:
            data = {
                "pending": {k: asdict(v) for k, v in self._cache.items()}
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Cache saved", count=len(self._cache))
        except Exception as e:
            logger.error("Failed to save cache", error=str(e))

    def is_hash_similar(self, new_hash: str, threshold: int) -> Optional[str]:
        """
        Check if a similar hash already exists in cache.
        
        Args:
            new_hash: The perceptual hash of the new card image
            threshold: Maximum Hamming distance to consider as "same" card

        Returns:
            Name of the matching request if found, None otherwise
        """
        if threshold <= 0:
            return None  # Feature disabled

        try:
            import imagehash
            new_hash_obj = imagehash.hex_to_hash(new_hash)

            for cached_hash, name in self._hash_cache.items():
                cached_hash_obj = imagehash.hex_to_hash(cached_hash)
                distance = new_hash_obj - cached_hash_obj
                if distance <= threshold:
                    logger.debug(f"Hash match found: distance={distance}, name={name}")
                    return name
        except Exception as e:
            logger.warning(f"Hash comparison error: {e}")
        
        return None
    
    def add_notification(self, name: str, extra_info: Optional[str] = None, card_hash: Optional[str] = None, 
                        preview_path: Optional[str] = None, action_buttons: Optional[Dict[str, List[int]]] = None,
                        cropped_path: Optional[str] = None, is_unanswered: bool = False) -> bool:
        """Add a new notification to cache. Returns False if already exists."""
        key = self._get_key(name)
        
        # If already in cache, don't overwrite (preserve decisions)
        if key in self._cache:
            logger.debug("Already in cache, skipping", name=name)
            return False  # Don't send duplicate notification
        
        self._cache[key] = PendingRequest(
            name=name,
            notified_at=datetime.now().isoformat(),
            extra_info=extra_info,
            card_hash=card_hash,
            preview_path=preview_path,
            action_buttons=action_buttons,
            cropped_path=cropped_path,
            is_unanswered=is_unanswered
        )
        
        # Add to hash cache
        if card_hash:
            self._hash_cache[card_hash] = name
        
        self._save()
        logger.info("Notification added to cache", name=name)
        return True
    
    def set_decision(self, name: str, decision: str) -> bool:
        """Set the decision (approve/decline) for a request."""
        key = self._get_key(name)
        if key not in self._cache:
            logger.warning("Request not in cache", name=name)
            return False
        
        self._cache[key].decision = decision
        self._save()
        logger.info("Decision saved", name=name, decision=decision)
        return True
    
    def get_pending_decisions(self) -> List[PendingRequest]:
        """Get all requests with a decision that haven't been executed yet."""
        return [
            req for req in self._cache.values()
            if req.decision is not None and not req.executed
        ]
    
    def mark_executed(self, name: str):
        """Mark a request as executed (remove from cache)."""
        key = self._get_key(name)
        if key in self._cache:
            # Remove from hash cache too
            if self._cache[key].card_hash:
                self._hash_cache.pop(self._cache[key].card_hash, None)
            del self._cache[key]
            self._save()
            logger.info("Request executed and removed", name=name)
    
    def get_request(self, name: str) -> Optional[PendingRequest]:
        """Get a specific request by name."""
        key = self._get_key(name)
        return self._cache.get(key)
    
    def is_notified(self, name: str) -> bool:
        """Check if a request has already been notified."""
        key = self._get_key(name)
        return key in self._cache
    
    def cleanup_old(self, max_age_hours: int = 360, pending_decision_max_hours: int = 360):
        """
        Remove old entries from cache.
        
        Args:
            max_age_hours: Remove notifications without decision after this many hours (default: 360h = 15 days)
            pending_decision_max_hours: Remove pending decisions that were never executed after 
                                        this many hours (default: 360h = 15 days). These are likely
                                        requests that were handled by another moderator.
        """
        now = datetime.now()
        to_remove = []

        for key, req in self._cache.items():
            notified = datetime.fromisoformat(req.notified_at)
            age_hours = (now - notified).total_seconds() / 3600

            # Case 1: No decision yet, older than max_age_hours
            if req.decision is None and age_hours > max_age_hours:
                to_remove.append((key, "no decision"))
                continue

            # Case 2: Decision pending but never executed, older than pending_decision_max_hours
            if req.decision is not None and not req.executed and age_hours > pending_decision_max_hours:
                to_remove.append((key, f"stale pending ({req.decision})"))

        for key, reason in to_remove:
            # Clean up hash cache
            if self._cache[key].card_hash:
                self._hash_cache.pop(self._cache[key].card_hash, None)
            name = self._cache[key].name
            del self._cache[key]
            logger.info(f"Removed stale entry: '{name}' ({reason})")

        if to_remove:
            self._save()
            logger.info(f"Cleanup complete: removed {len(to_remove)} stale entries")


def cleanup_old_screenshots(screenshots_dir: str, max_age_days: int = 15):
    """Delete screenshot files older than max_age_days."""
    from pathlib import Path
    from datetime import timedelta
    
    cutoff = datetime.now() - timedelta(days=max_age_days)
    count = 0
    try:
        for f in Path(screenshots_dir).glob("*.png"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                count += 1
        if count:
            logger.info(f"Screenshot cleanup: deleted {count} files older than {max_age_days} days")
    except Exception as e:
        logger.warning(f"Screenshot cleanup error: {e}")


# Global cache instance
cache = DecisionCache()

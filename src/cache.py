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


class DecisionCache:
    """Manages the cache of pending member request decisions."""
    
    def __init__(self):
        self._cache: Dict[str, PendingRequest] = {}
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
    
    def add_notification(self, name: str, extra_info: Optional[str] = None) -> bool:
        """Add a new notification to cache. Returns False if already exists."""
        key = self._get_key(name)
        
        # If already in cache, don't overwrite (preserve decisions)
        if key in self._cache:
            logger.debug("Already in cache, skipping", name=name)
            return False  # Don't send duplicate notification
        
        self._cache[key] = PendingRequest(
            name=name,
            notified_at=datetime.now().isoformat(),
            extra_info=extra_info
        )
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
    
    def cleanup_old(self, max_age_hours: int = 24):
        """Remove old entries that were never decided."""
        now = datetime.now()
        to_remove = []
        
        for key, req in self._cache.items():
            if req.decision is None:
                notified = datetime.fromisoformat(req.notified_at)
                age_hours = (now - notified).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_remove.append(key)
        
        for key in to_remove:
            del self._cache[key]
            logger.info("Removed stale request", name=self._cache.get(key, {}).get("name", key))
        
        if to_remove:
            self._save()


# Global cache instance
cache = DecisionCache()

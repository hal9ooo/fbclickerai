"""Configuration management for FBClicker bot."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Facebook credentials
    fb_email: str = Field(..., description="Facebook login email")
    fb_password: str = Field(..., description="Facebook login password")
    fb_group_id: str = Field(..., description="Facebook group ID to moderate")
    
    # OpenRouter API
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_model: str = Field(
        default="google/gemini-2.5-pro-preview-06-05",
        description="Vision model to use (must support images)"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    
    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    telegram_admin_ids: List[int] = Field(..., description="List of Telegram admin user IDs")
    
    # Browser settings
    headless: bool = Field(default=True, description="Run browser in headless mode")
    slow_mo: int = Field(default=100, description="Slow down actions by ms")
    
    # Proxy settings (for IP rotation - stealth)
    proxy_list: List[str] = Field(
        default=[],
        description="List of proxy servers (format: http://user:pass@host:port or socks5://host:port)"
    )
    
    # Debug settings
    debug_click_overlay: bool = Field(default=True, description="Save debug images showing click positions")
    debug_ai_validation: bool = Field(default=True, description="Use OpenRouter AI to validate click positions")
    
    # Polling with jitter (stealth)
    poll_interval: int = Field(default=3600, description="Base seconds between moderation checks")
    poll_jitter: float = Field(
        default=0.3, 
        description="Random jitter factor (0.3 = ±30% variation on poll_interval)"
    )

    # Perceptual hash threshold for skipping OCR on already-seen cards
    # 0 = disabled, higher = more tolerant (10 = recommended, max ~64)
    card_hash_threshold: int = Field(
        default=3,
        description="Hamming distance threshold for card image similarity (0=disabled, 2=strict)"
    )
    
    # Paths
    data_dir: str = Field(default="/app/data", description="Data directory path")
    screenshots_dir: str = Field(default="/app/data/screenshots", description="Screenshots directory")
    sessions_dir: str = Field(default="/app/data/sessions", description="Browser sessions directory")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


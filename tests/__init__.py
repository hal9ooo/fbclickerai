"""Ambiente minimo per importare src.config senza credenziali reali."""

import os

for _key, _value in {
    "FB_EMAIL": "test@example.com",
    "FB_PASSWORD": "test-password",
    "FB_GROUP_ID": "123456",
    "OPENROUTER_API_KEY": "test-key",
    "TELEGRAM_BOT_TOKEN": "123:test-token",
    "TELEGRAM_ADMIN_IDS": "[1,2]",
}.items():
    os.environ.setdefault(_key, _value)

"""Test unit per la configurazione (nessun I/O esterno)."""

import os
import unittest

from src.config import Settings

REQUIRED = dict(
    fb_email="a@example.com",
    fb_password="secret",
    fb_group_id="123",
    openrouter_api_key="key",
    telegram_bot_token="token",
    telegram_admin_ids=[1, 2],
)


class SettingsTests(unittest.TestCase):
    def test_defaults_are_applied(self):
        settings = Settings(**REQUIRED)
        self.assertEqual(settings.openrouter_base_url, "https://openrouter.ai/api/v1")
        self.assertTrue(settings.headless)
        self.assertEqual(settings.poll_interval, 10800)
        self.assertAlmostEqual(settings.poll_jitter, 0.3)
        self.assertEqual(settings.card_hash_threshold, 1)
        self.assertEqual(settings.data_dir, "data")

    def test_admin_ids_are_ints(self):
        settings = Settings(**REQUIRED)
        self.assertEqual(settings.telegram_admin_ids, [1, 2])

    def test_required_fields_come_from_environment(self):
        settings = Settings()
        self.assertEqual(settings.fb_email, os.environ["FB_EMAIL"])
        self.assertEqual(settings.telegram_admin_ids, [1, 2])


if __name__ == "__main__":
    unittest.main()

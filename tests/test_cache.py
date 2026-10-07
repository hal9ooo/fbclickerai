"""Test unit per DecisionCache su file temporaneo (nessuna rete)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import src.cache as cache_module
from src.cache import DecisionCache


class DecisionCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_cache_file = cache_module.CACHE_FILE
        cache_module.CACHE_FILE = Path(self._tmp.name) / "decisions_cache.json"
        self.cache = DecisionCache()

    def tearDown(self):
        cache_module.CACHE_FILE = self._original_cache_file
        self._tmp.cleanup()

    def test_add_notification_then_detect_duplicate_case_insensitive(self):
        self.assertTrue(self.cache.add_notification("Mario Rossi"))
        self.assertTrue(self.cache.is_notified("mario rossi"))
        self.assertFalse(self.cache.add_notification("  MARIO ROSSI  "))

    def test_decision_flow(self):
        self.cache.add_notification("Anna")
        self.assertFalse(self.cache.set_decision("sconosciuto", "approve"))
        self.assertTrue(self.cache.set_decision("Anna", "approve"))
        pending = self.cache.get_pending_decisions()
        self.assertEqual([req.name for req in pending], ["Anna"])
        self.cache.mark_executed("anna")
        self.assertFalse(self.cache.is_notified("Anna"))
        self.assertEqual(self.cache.get_pending_decisions(), [])

    def test_state_persists_across_instances(self):
        self.cache.add_notification("Luca", extra_info="unanswered")
        reloaded = DecisionCache()
        request = reloaded.get_request("luca")
        self.assertIsNotNone(request)
        self.assertEqual(request.extra_info, "unanswered")

    def test_hash_similarity_disabled_returns_none(self):
        self.cache.add_notification("Eva", card_hash="ffffffffffffffff")
        self.assertIsNone(self.cache.is_hash_similar("ffffffffffffffff", threshold=0))

    def test_cleanup_old_removes_stale_entries(self):
        self.cache.add_notification("Vecchio")
        key = self.cache._get_key("Vecchio")
        self.cache._cache[key].notified_at = datetime(2020, 1, 1).isoformat()
        self.cache.cleanup_old(max_age_hours=1)
        self.assertFalse(self.cache.is_notified("Vecchio"))


if __name__ == "__main__":
    unittest.main()

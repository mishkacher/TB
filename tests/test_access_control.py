import unittest
from tempfile import TemporaryDirectory

from database.access_control import AccessRegistry


class AccessRegistryTests(unittest.TestCase):
    def test_request_is_persisted_and_can_be_approved_once(self):
        with TemporaryDirectory() as directory:
            registry = AccessRegistry(f"{directory}/access.json")

            self.assertEqual(registry.request(42, "Иван", "ivan"), "pending")
            self.assertEqual(registry.request(42, "Иван", "ivan"), "pending_existing")
            self.assertTrue(registry.decide(42, "allowed"))
            self.assertTrue(registry.is_allowed(42))
            self.assertFalse(registry.decide(42, "blocked"))

    def test_blocked_user_cannot_submit_another_request(self):
        with TemporaryDirectory() as directory:
            registry = AccessRegistry(f"{directory}/access.json")
            registry.request(7, "Пётр", "petr")
            registry.decide(7, "blocked")

            self.assertEqual(registry.request(7, "Пётр", "petr"), "blocked")

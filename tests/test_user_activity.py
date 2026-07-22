import unittest
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from database.user_activity import UserActivityRegistry
from handlers.admin import format_user_stats


class UserActivityTests(unittest.TestCase):
    def test_touch_persists_first_and_last_activity(self):
        with TemporaryDirectory() as directory:
            registry = UserActivityRegistry(f"{directory}/activity.json")
            user = SimpleNamespace(id=42, first_name="Иван", last_name=None, username="ivan")
            registry.touch(user)
            registry.touch(user)

            record = registry.users()["42"]
            self.assertEqual(record["name"], "Иван")
            self.assertEqual(record["visits"], 2)
            self.assertLessEqual(record["first_seen"], record["last_seen"])

    def test_stats_counts_recent_users(self):
        with TemporaryDirectory() as directory:
            registry = UserActivityRegistry(f"{directory}/activity.json")
            now = datetime(2026, 7, 22, tzinfo=timezone.utc)
            registry._write({"users": {
                "1": {"name": "Сегодня", "last_seen": now.isoformat()},
                "2": {"name": "Неделя", "last_seen": (now - timedelta(days=3)).isoformat()},
                "3": {"name": "Старый", "last_seen": (now - timedelta(days=40)).isoformat()},
            }})

            report = format_user_stats(registry, now)
            self.assertIn("Всего пользователей: 3", report)
            self.assertIn("Активны за 24 часа: 1", report)
            self.assertIn("Активны за 7 дней: 2", report)

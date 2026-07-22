"""Persistent, privacy-minimal Telegram user activity tracking."""

import json
from datetime import datetime, timezone
from pathlib import Path


class UserActivityRegistry:
    def __init__(self, path="data/user_activity.json"):
        self.path = Path(path)

    def touch(self, user):
        """Save the latest interaction for a Telegram user."""
        data = self._read()
        users = data.setdefault("users", {})
        user_id = str(user.id)
        record = users.get(user_id, {})
        now = datetime.now(timezone.utc).isoformat()
        users[user_id] = {
            "name": " ".join(filter(None, [user.first_name, user.last_name])) or "Без имени",
            "username": user.username,
            "first_seen": record.get("first_seen", now),
            "last_seen": now,
            "visits": record.get("visits", 0) + 1,
        }
        self._write(data)

    def users(self):
        return self._read().get("users", {})

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

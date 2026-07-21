"""Atomic JSON persistence for FVG preferences, events and deliveries."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from alerts.fvg_detector import price_allowed
from alerts.fvg_models import FvgDirection, FvgEvent, FvgEventType


UTC = timezone.utc
_STORE_LOCKS: dict[str, threading.RLock] = {}
_STORE_LOCKS_GUARD = threading.Lock()


class AtomicJsonStore:
    def __init__(self, path: str):
        self.path = Path(path)
        resolved = str(self.path.resolve())
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(resolved, threading.RLock())

    def read(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}

    def write(self, data: dict) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)


def _symbol_defaults() -> dict:
    return {
        "enabled": True,
        "price_filter": {
            "enabled": False,
            "min": None,
            "max": None,
            "apply_to_pre_fvg": True,
            "apply_to_confirmed_fvg": True,
        },
    }


def _user_defaults() -> dict:
    return {
        "enabled": False,
        "notify_confirmed_fvg": True,
        "notify_pre_fvg": False,
        "bullish_enabled": True,
        "bearish_enabled": True,
        "symbols": {"BTCUSDT": _symbol_defaults()},
    }


class FvgAlertSettings:
    SCHEMA_VERSION = 2

    def __init__(self, path: str = "data/fvg_alert_settings.json"):
        self.store = AtomicJsonStore(path)
        self.path = self.store.path

    def _read(self) -> dict:
        raw = self.store.read()
        if raw.get("schema_version") == self.SCHEMA_VERSION:
            return raw
        users = {}
        known_ids = set(raw.get("enabled_chat_ids", [])) | set(raw.get("pre_enabled_chat_ids", []))
        for chat_id in known_ids:
            user = _user_defaults()
            user["enabled"] = True
            user["notify_confirmed_fvg"] = chat_id in raw.get("enabled_chat_ids", [])
            user["notify_pre_fvg"] = chat_id in raw.get("pre_enabled_chat_ids", [])
            users[str(chat_id)] = user
        return {
            "schema_version": self.SCHEMA_VERSION,
            "users": users,
            "legacy_last_event_key": raw.get("last_event_key"),
            "legacy_last_pre_event_key": raw.get("last_pre_event_key"),
        }

    def _write(self, data: dict) -> None:
        data["schema_version"] = self.SCHEMA_VERSION
        self.store.write(data)

    def _transaction(self, mutate) -> None:
        with self.store._lock:
            data = self._read()
            mutate(data)
            self._write(data)

    def user(self, chat_id: int) -> dict:
        return deepcopy(self._read().get("users", {}).get(str(chat_id), _user_defaults()))

    def update_user(self, chat_id: int, **values) -> None:
        def mutate(data):
            data.setdefault("users", {}).setdefault(str(chat_id), _user_defaults()).update(values)
        self._transaction(mutate)

    def enabled_chat_ids(self):
        return frozenset(int(key) for key, value in self._read().get("users", {}).items() if value.get("enabled") and value.get("notify_confirmed_fvg", True))

    def pre_enabled_chat_ids(self):
        return frozenset(int(key) for key, value in self._read().get("users", {}).items() if value.get("enabled") and value.get("notify_pre_fvg", False))

    def is_enabled(self, chat_id):
        return bool(self.user(chat_id).get("enabled"))

    def is_pre_enabled(self, chat_id):
        user = self.user(chat_id)
        return bool(user.get("enabled") and user.get("notify_pre_fvg"))

    def set_enabled(self, chat_id, enabled):
        self.update_user(chat_id, enabled=bool(enabled))

    def set_confirmed_enabled(self, chat_id, enabled):
        self.update_user(chat_id, notify_confirmed_fvg=bool(enabled))

    def set_pre_enabled(self, chat_id, enabled):
        self.update_user(chat_id, enabled=True, notify_pre_fvg=bool(enabled))

    def set_direction_enabled(self, chat_id, direction: FvgDirection, enabled: bool):
        key = "bullish_enabled" if direction is FvgDirection.BULLISH else "bearish_enabled"
        self.update_user(chat_id, **{key: bool(enabled)})

    def add_symbol(self, chat_id: int, symbol: str) -> None:
        def mutate(data):
            user = data.setdefault("users", {}).setdefault(str(chat_id), _user_defaults())
            user.setdefault("symbols", {}).setdefault(symbol.upper(), _symbol_defaults())
        self._transaction(mutate)

    def remove_symbol(self, chat_id: int, symbol: str) -> None:
        def mutate(data):
            user = data.setdefault("users", {}).setdefault(str(chat_id), _user_defaults())
            user.setdefault("symbols", {}).pop(symbol.upper(), None)
        self._transaction(mutate)

    def set_price_filter(
        self, chat_id: int, symbol: str, minimum: str | None, maximum: str | None,
        enabled: bool = True, apply_to_pre: bool = True, apply_to_confirmed: bool = True,
    ) -> None:
        try:
            min_value = Decimal(minimum) if minimum is not None else None
            max_value = Decimal(maximum) if maximum is not None else None
        except InvalidOperation as error:
            raise ValueError("Некорректная граница цены") from error
        if min_value is not None and max_value is not None and min_value > max_value:
            raise ValueError("Минимальная цена не может быть выше максимальной")
        def mutate(data):
            user = data.setdefault("users", {}).setdefault(str(chat_id), _user_defaults())
            symbol_data = user.setdefault("symbols", {}).setdefault(symbol.upper(), _symbol_defaults())
            symbol_data["price_filter"] = {
                "enabled": bool(enabled), "min": str(min_value) if min_value is not None else None,
                "max": str(max_value) if max_value is not None else None,
                "apply_to_pre_fvg": bool(apply_to_pre),
                "apply_to_confirmed_fvg": bool(apply_to_confirmed),
            }
        self._transaction(mutate)

    def active_symbols(self) -> frozenset[str]:
        symbols: set[str] = set()
        for user in self._read().get("users", {}).values():
            if user.get("enabled"):
                symbols.update(symbol for symbol, cfg in user.get("symbols", {}).items() if cfg.get("enabled", True))
        return frozenset(symbols)

    def recipients(self, event: FvgEvent) -> list[int]:
        recipients = []
        for key, user in self._read().get("users", {}).items():
            if not user.get("enabled"):
                continue
            type_key = "notify_pre_fvg" if event.event_type is FvgEventType.PRE_FVG else "notify_confirmed_fvg"
            if not user.get(type_key, event.event_type is FvgEventType.CONFIRMED_FVG):
                continue
            direction_key = "bullish_enabled" if event.direction is FvgDirection.BULLISH else "bearish_enabled"
            if not user.get(direction_key, True):
                continue
            symbol_cfg = user.get("symbols", {}).get(event.symbol)
            if not symbol_cfg or not symbol_cfg.get("enabled", True):
                continue
            price = symbol_cfg.get("price_filter", {})
            apply_key = "apply_to_pre_fvg" if event.event_type is FvgEventType.PRE_FVG else "apply_to_confirmed_fvg"
            use_filter = price.get("enabled", False) and price.get(apply_key, True)
            if not price_allowed(event.signal_price, use_filter, _decimal(price.get("min")), _decimal(price.get("max"))):
                continue
            recipients.append(int(key))
        return recipients

    # Compatibility with the old tests/API. New delivery dedup lives in FvgEventStore.
    def is_new(self, event_key):
        return self._read().get("legacy_last_event_key") != event_key

    def mark_sent(self, event_key):
        self._transaction(lambda data: data.update(legacy_last_event_key=event_key))

    def is_new_pre_event(self, event_key):
        return self._read().get("legacy_last_pre_event_key") != event_key

    def mark_pre_sent(self, event_key):
        self._transaction(lambda data: data.update(legacy_last_pre_event_key=event_key))


def _decimal(value):
    return Decimal(value) if value is not None else None


class FvgEventStore:
    def __init__(self, path: str = "data/fvg_event_store.json"):
        self.store = AtomicJsonStore(path)

    def _read(self):
        data = self.store.read()
        data.setdefault("events", {})
        data.setdefault("deliveries", {})
        data.setdefault("health", {})
        return data

    def _transaction(self, mutate):
        with self.store._lock:
            data = self._read()
            result = mutate(data)
            self.store.write(data)
            return result

    def record_event(self, event: FvgEvent) -> bool:
        def mutate(data):
            is_new = event.event_id not in data["events"]
            data["events"].setdefault(event.event_id, event.to_json())
            return is_new
        return self._transaction(mutate)

    def delivery_needed(self, chat_id: int, event_id: str) -> bool:
        return str(chat_id) not in self._read()["deliveries"].get(event_id, {})

    def mark_delivered(self, chat_id: int, event_id: str) -> None:
        self._transaction(lambda data: data["deliveries"].setdefault(event_id, {}).update({str(chat_id): datetime.now(UTC).isoformat()}))

    def update_health(self, **values) -> None:
        self._transaction(lambda data: data["health"].update(values))

    def increment_health(self, key: str, amount: int = 1) -> None:
        def mutate(data):
            data["health"][key] = int(data["health"].get(key, 0)) + amount
        self._transaction(mutate)

    def health(self) -> dict:
        data = self._read()
        return {**data["health"], "events": len(data["events"]), "deliveries": sum(len(v) for v in data["deliveries"].values())}

    def summary(self, days: int | None = 7) -> dict:
        data = self._read()
        cutoff = datetime.now(UTC).timestamp() - days * 86400 if days is not None else None
        events = []
        for event in data["events"].values():
            detected = datetime.fromisoformat(event["detected_at"]).timestamp()
            if cutoff is None or detected >= cutoff:
                events.append(event)
        result: dict[str, object] = {}
        for direction in ("BULLISH", "BEARISH"):
            selected = [event for event in events if event["direction"] == direction]
            confirmed = sum(event["event_type"] == "CONFIRMED_FVG" for event in selected)
            preliminary = sum(event["event_type"] == "PRE_FVG" for event in selected)
            result[direction] = {"confirmed": confirmed, "pre": preliminary, "total": len(selected)}
        result["deliveries"] = sum(
            len(data["deliveries"].get(event["event_id"], {})) for event in events
        )
        return result

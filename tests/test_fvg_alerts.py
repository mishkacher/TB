import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from tempfile import TemporaryDirectory

from alerts.fvg_detector import FvgDetector, aggregate_current_15m, price_allowed
from alerts.fvg_models import Candle, FvgDirection, FvgEventType
from alerts.fvg_service import FvgAlertService, format_fvg_message
from alerts.fvg_store import FvgAlertSettings, FvgEventStore


UTC = timezone.utc
BASE = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def candle(index, high, low, close=None, *, closed=True, complete=True, timeframe="15m"):
    step = timedelta(minutes=1 if timeframe == "1m" else 15)
    start = BASE + index * step
    close = Decimal(str(close if close is not None else (Decimal(str(high)) + Decimal(str(low))) / 2))
    return Candle(
        symbol="BTCUSDT", timeframe=timeframe, open_time=start, close_time=start + step,
        open=close, high=Decimal(str(high)), low=Decimal(str(low)), close=close,
        is_closed=closed, is_complete=complete,
    )


class FvgDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = FvgDetector()

    def test_bullish_confirmed_fvg(self):
        event = self.detector.detect_confirmed([candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105)])
        self.assertEqual(event.direction, FvgDirection.BULLISH)
        self.assertEqual((event.zone_low, event.zone_high), (Decimal("100"), Decimal("105")))
        self.assertEqual(event.signal_price, Decimal("108.5"))

    def test_bearish_confirmed_fvg(self):
        event = self.detector.detect_confirmed([candle(0, 110, 100), candle(1, 104, 95), candle(2, 94, 90)])
        self.assertEqual(event.direction, FvgDirection.BEARISH)
        self.assertEqual((event.zone_low, event.zone_high), (Decimal("94"), Decimal("100")))

    def test_no_gap_and_equal_boundaries_are_not_fvg(self):
        self.assertIsNone(self.detector.detect_confirmed([candle(0, 100, 90), candle(1, 106, 95), candle(2, 110, 100)]))

    def test_rejects_incomplete_open_or_nonconsecutive_candles(self):
        incomplete = [candle(0, 100, 90), candle(1, 108, 96, complete=False), candle(2, 112, 105)]
        opened = [candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105, closed=False)]
        skipped = [candle(0, 100, 90), candle(1, 108, 96), candle(3, 112, 105)]
        self.assertIsNone(self.detector.detect_confirmed(incomplete))
        self.assertIsNone(self.detector.detect_confirmed(opened))
        self.assertIsNone(self.detector.detect_confirmed(skipped))

    def test_pre_fvg_only_in_t_minus_three_window(self):
        a, b = candle(0, 100, 90), candle(1, 108, 96)
        c = candle(2, 112, 105, closed=False)
        on_time = c.open_time + timedelta(minutes=12, seconds=20)
        event = self.detector.detect_pre(a, b, c, on_time)
        self.assertEqual(event.event_type, FvgEventType.PRE_FVG)
        self.assertFalse(event.is_confirmed)
        self.assertIsNone(self.detector.detect_pre(a, b, c, c.open_time + timedelta(minutes=13)))

    def test_aggregates_exactly_twelve_complete_minutes(self):
        interval = BASE
        minutes = [candle(i, 101 + i, 99 + i, timeframe="1m") for i in range(12)]
        result = aggregate_current_15m("BTCUSDT", minutes, interval, interval + timedelta(minutes=12, seconds=10))
        self.assertIsNotNone(result)
        self.assertEqual(result.close, minutes[-1].close)
        self.assertIsNone(aggregate_current_15m("BTCUSDT", minutes[:-1], interval, interval + timedelta(minutes=12, seconds=10)))


class PriceFilterTests(unittest.TestCase):
    def test_disabled_and_inclusive_boundaries(self):
        self.assertTrue(price_allowed(Decimal("1"), False, Decimal("10"), Decimal("20")))
        self.assertTrue(price_allowed(Decimal("10"), True, Decimal("10"), Decimal("20")))
        self.assertTrue(price_allowed(Decimal("20"), True, Decimal("10"), Decimal("20")))

    def test_min_max_and_both(self):
        self.assertFalse(price_allowed(Decimal("9.99"), True, Decimal("10"), None))
        self.assertFalse(price_allowed(Decimal("20.01"), True, None, Decimal("20")))
        self.assertTrue(price_allowed(Decimal("15"), True, Decimal("10"), Decimal("20")))


class SettingsAndDedupTests(unittest.TestCase):
    def test_migrates_legacy_settings_and_preserves_pre_choice(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/settings.json"
            with open(path, "w", encoding="utf-8") as file:
                file.write('{"enabled_chat_ids":[1,2],"pre_enabled_chat_ids":[2]}')
            settings = FvgAlertSettings(path)
            self.assertTrue(settings.is_enabled(1))
            self.assertFalse(settings.is_pre_enabled(1))
            self.assertTrue(settings.is_pre_enabled(2))

    def test_direction_type_symbol_and_price_are_user_scoped(self):
        with TemporaryDirectory() as directory:
            settings = FvgAlertSettings(f"{directory}/settings.json")
            settings.set_enabled(1, True)
            settings.set_enabled(2, True)
            settings.set_price_filter(1, "BTCUSDT", "100", "110", apply_to_pre=True, apply_to_confirmed=False)
            event = FvgDetector().detect_confirmed([candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105)])
            self.assertEqual(settings.recipients(event), [1, 2])
            settings.set_direction_enabled(2, FvgDirection.BULLISH, False)
            self.assertEqual(settings.recipients(event), [1])

    def test_price_filter_can_apply_only_to_pre_fvg(self):
        with TemporaryDirectory() as directory:
            settings = FvgAlertSettings(f"{directory}/settings.json")
            settings.set_enabled(1, True)
            settings.set_pre_enabled(1, True)
            settings.set_price_filter(1, "BTCUSDT", "200", None, apply_to_pre=True, apply_to_confirmed=False)
            detector = FvgDetector()
            a, b, c = candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105, closed=False)
            pre = detector.detect_pre(a, b, c, c.open_time + timedelta(minutes=12))
            confirmed = detector.detect_confirmed([a, b, candle(2, 112, 105)])
            self.assertEqual(settings.recipients(pre), [])
            self.assertEqual(settings.recipients(confirmed), [1])

    def test_market_event_and_user_deliveries_are_separate_and_persistent(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/events.json"
            event = FvgDetector().detect_confirmed([candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105)])
            store = FvgEventStore(path)
            self.assertTrue(store.record_event(event))
            self.assertFalse(store.record_event(event))
            store.mark_delivered(1, event.event_id)
            restarted = FvgEventStore(path)
            self.assertFalse(restarted.delivery_needed(1, event.event_id))
            self.assertTrue(restarted.delivery_needed(2, event.event_id))

    def test_message_has_mandatory_fields_and_no_trading_advice(self):
        event = FvgDetector().detect_confirmed([candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105)])
        text = format_fvg_message(event)
        for expected in ("BTCUSDT", "15m", "Бычий", "Зона FVG", "Размер зоны", "Цена сигнала", "Подтверждён"):
            self.assertIn(expected, text)
        for forbidden in ("вход", "стоп", "тейк", "плеч"):
            self.assertNotIn(forbidden, text.lower())


class DeliveryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_users_receive_once_and_restart_does_not_duplicate(self):
        class Bot:
            def __init__(self):
                self.calls = []

            async def send_message(self, chat_id, text):
                self.calls.append((chat_id, text))

        with TemporaryDirectory() as directory:
            settings_path = f"{directory}/settings.json"
            events_path = f"{directory}/events.json"
            settings = FvgAlertSettings(settings_path)
            settings.set_enabled(1, True)
            settings.set_enabled(2, True)
            event = FvgDetector().detect_confirmed([candle(0, 100, 90), candle(1, 108, 96), candle(2, 112, 105)])
            bot = Bot()
            service = FvgAlertService(settings=settings, event_store=FvgEventStore(events_path))
            await service.deliver(bot, [event, event])
            restarted = FvgAlertService(
                settings=FvgAlertSettings(settings_path),
                event_store=FvgEventStore(events_path),
            )
            await restarted.deliver(bot, [event])
            self.assertEqual([call[0] for call in bot.calls], [1, 2])


if __name__ == "__main__":
    unittest.main()

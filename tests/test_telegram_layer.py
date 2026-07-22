import unittest

from bot import BOT_COMMANDS
from config import parse_telegram_ids


class TelegramLayerTests(unittest.TestCase):
    def test_parses_access_list(self):
        self.assertEqual(parse_telegram_ids("1, 2,3"), frozenset({1, 2, 3}))

    def test_command_menu_contains_only_fvg_and_administration(self):
        commands = {command.command for command in BOT_COMMANDS}

        self.assertTrue({"menu", "admin", "fvg_alert", "fvg_pre_alert", "fvg_symbol", "fvg_price", "fvg_size", "fvg_stats"} <= commands)
        self.assertFalse({"btc", "chart", "scan", "status", "myid"} & commands)


if __name__ == "__main__":
    unittest.main()

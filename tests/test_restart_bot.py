import unittest

from restart_bot import is_bot_command, parse_processes


class RestartBotTests(unittest.TestCase):
    def test_recognizes_only_python_bot_commands(self):
        self.assertTrue(is_bot_command("/usr/bin/Python -u bot.py"))
        self.assertTrue(is_bot_command(".venv/bin/python bot.py"))
        self.assertFalse(is_bot_command("python restart_bot.py"))
        self.assertFalse(is_bot_command("rg bot.py"))

    def test_parses_ps_output(self):
        output = "  123 /usr/bin/Python -u bot.py\n  456 /bin/zsh\n"
        self.assertEqual(
            parse_processes(output),
            [(123, "/usr/bin/Python -u bot.py"), (456, "/bin/zsh")],
        )


if __name__ == "__main__":
    unittest.main()

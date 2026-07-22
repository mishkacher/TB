import asyncio
import unittest

from handlers.myid import myid


class FakeMessage:
    def __init__(self):
        self.text = None

    async def reply_text(self, text):
        self.text = text


class FakeUpdate:
    def __init__(self, user_id):
        self.effective_user = type("User", (), {"id": user_id})()
        self.effective_message = FakeMessage()


class MyIdHandlerTests(unittest.TestCase):
    def test_returns_callers_telegram_id(self):
        update = FakeUpdate(123456)

        asyncio.run(myid(update, None))

        self.assertIn("123456", update.effective_message.text)


if __name__ == "__main__":
    unittest.main()

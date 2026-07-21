"""One shared reconnecting Bitunix public WebSocket for all active symbols."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import datetime, timezone

import aiohttp
import certifi


logger = logging.getLogger(__name__)
UTC = timezone.utc


class BitunixFvgStream:
    URL = "wss://fapi.bitunix.com/public"

    def __init__(self, service, reconnect_min=1, reconnect_max=60):
        self.service = service
        self.reconnect_min = reconnect_min
        self.reconnect_max = reconnect_max
        self._stopping = False
        self._delivery_queue = asyncio.Queue()
        self._observed_event_ids: set[str] = set()

    async def run(self, bot) -> None:
        delivery_worker = asyncio.create_task(self._deliver_worker(bot))
        try:
            await self._run_market(bot)
        finally:
            delivery_worker.cancel()
            await asyncio.gather(delivery_worker, return_exceptions=True)

    async def _deliver_worker(self, bot) -> None:
        while True:
            events = await self._delivery_queue.get()
            try:
                await self.service.deliver(bot, events)
            finally:
                self._delivery_queue.task_done()

    def _enqueue(self, events) -> None:
        new_events = []
        for event in events:
            if event.event_id not in self._observed_event_ids:
                self._observed_event_ids.add(event.event_id)
                new_events.append(event)
        if new_events:
            self._delivery_queue.put_nowait(new_events)

    async def _run_market(self, bot) -> None:
        delay = self.reconnect_min
        while not self._stopping:
            symbols = sorted(self.service.settings.active_symbols())
            if not symbols:
                await asyncio.sleep(5)
                continue
            try:
                timeout = aiohttp.ClientTimeout(total=None, sock_read=45)
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(
                        self.URL, heartbeat=20, ssl=ssl_context
                    ) as ws:
                        args = [
                            {"symbol": symbol, "ch": channel}
                            for symbol in symbols
                            for channel in ("market_kline_1min", "market_kline_15min")
                        ]
                        await ws.send_json({"op": "subscribe", "args": args})
                        now = datetime.now(UTC)
                        self.service.event_store.update_health(
                            ws_connected=True, subscribed_symbols=symbols,
                            last_reconnect=now.isoformat(), last_error=None,
                        )
                        for symbol in symbols:
                            events = await asyncio.to_thread(self.service.recover, symbol, now)
                            self._enqueue(events)
                        delay = self.reconnect_min
                        subscribed = set(symbols)
                        while not self._stopping:
                            current = set(self.service.settings.active_symbols())
                            removed, added = subscribed - current, current - subscribed
                            if removed:
                                await ws.send_json({"op": "unsubscribe", "args": [
                                    {"symbol": symbol, "ch": channel}
                                    for symbol in sorted(removed)
                                    for channel in ("market_kline_1min", "market_kline_15min")
                                ]})
                            if added:
                                await ws.send_json({"op": "subscribe", "args": [
                                    {"symbol": symbol, "ch": channel}
                                    for symbol in sorted(added)
                                    for channel in ("market_kline_1min", "market_kline_15min")
                                ]})
                                for symbol in sorted(added):
                                    events = await asyncio.to_thread(self.service.recover, symbol)
                                    self._enqueue(events)
                            subscribed = current
                            self.service.event_store.update_health(subscribed_symbols=sorted(subscribed))
                            try:
                                message = await ws.receive(timeout=5)
                            except asyncio.TimeoutError:
                                continue
                            if message.type in {
                                aiohttp.WSMsgType.CLOSE,
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.ERROR,
                            }:
                                raise ConnectionError("Bitunix WebSocket closed")
                            if message.type != aiohttp.WSMsgType.TEXT:
                                continue
                            payload = json.loads(message.data)
                            if payload.get("ch", "").startswith("market_kline_") and payload.get("data"):
                                try:
                                    events = self.service.ingest_ws(payload)
                                except (ValueError, KeyError, TypeError) as error:
                                    logger.warning("Invalid Bitunix FVG WebSocket candle: %s", error)
                                    self.service.event_store.increment_health("invalid_candles")
                                else:
                                    self._enqueue(events)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Bitunix FVG WebSocket disconnected: %s", error)
                self.service.event_store.update_health(ws_connected=False, last_error=str(error))
                self.service.event_store.increment_health("reconnects")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.reconnect_max)

    def stop(self) -> None:
        self._stopping = True

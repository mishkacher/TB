#!/usr/bin/env python3
"""Safely restart the single TradingAssistant Telegram bot instance."""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
BOT_FILE = PROJECT_DIR / "bot.py"
PID_FILE = PROJECT_DIR / "data" / "bot.pid"
LOG_FILE = PROJECT_DIR / "data" / "bot.log"
BOT_COMMAND = re.compile(
    r"(?:^|/)python(?:\d+(?:\.\d+)*)?\b.*(?:^|\s)bot\.py(?:\s|$)",
    re.IGNORECASE,
)


def parse_processes(output: str) -> list[tuple[int, str]]:
    processes = []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)", line)
        if match:
            processes.append((int(match.group(1)), match.group(2)))
    return processes


def is_bot_command(command: str) -> bool:
    return bool(BOT_COMMAND.search(command))


def process_cwd(pid: int) -> Path | None:
    result = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:]).resolve()
    return None


def find_project_bots() -> list[int]:
    result = subprocess.run(
        ["ps", "ax", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=True,
    )
    current_pid = os.getpid()
    return [
        pid
        for pid, command in parse_processes(result.stdout)
        if pid != current_pid
        and is_bot_command(command)
        and process_cwd(pid) == PROJECT_DIR
    ]


def stop_processes(pids: list[int], timeout: float = 10.0) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        for pid in tuple(remaining):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                remaining.remove(pid)
        if remaining:
            time.sleep(0.1)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_bot() -> int:
    if not PYTHON.exists():
        raise RuntimeError(f"Не найден Python виртуального окружения: {PYTHON}")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(PYTHON), "-u", BOT_FILE.name],
            cwd=PROJECT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_FILE.write_text(f"{process.pid}\n", encoding="utf-8")
    time.sleep(0.5)
    if process.poll() is not None:
        raise RuntimeError(f"Бот завершился при запуске. Проверь журнал: {LOG_FILE}")
    return process.pid


def restart() -> tuple[list[int], int]:
    stopped = find_project_bots()
    stop_processes(stopped)
    return stopped, start_bot()


def main() -> None:
    parser = argparse.ArgumentParser(description="Перезапуск Telegram-бота")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="только показать найденные процессы, ничего не останавливать",
    )
    args = parser.parse_args()
    if args.dry_run:
        pids = find_project_bots()
        print("Найдены процессы:", ", ".join(map(str, pids)) or "нет")
        return
    stopped, started = restart()
    print("Остановлены:", ", ".join(map(str, stopped)) or "не было")
    print(f"Бот запущен: PID {started}")
    print(f"Журнал: {LOG_FILE}")


if __name__ == "__main__":
    main()

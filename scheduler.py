"""Opt-in daily scheduler for the supported BOSS read-only filter run."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable


class DailyFilterScheduler:
    def __init__(
        self,
        store: Any,
        run_filter: Callable[[str], str],
        *,
        now: Callable[[], datetime] = datetime.now,
        poll_seconds: float = 5.0,
    ) -> None:
        self.store = store
        self.run_filter = run_filter
        self.now = now
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-boss-filter", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def check_once(self) -> bool:
        """Start only inside the selected local minute, at most once per day."""
        timing = self.store.get_apply_config("timing") or {}
        if not timing.get("enable"):
            return False
        if self.store.get_apply_config("work_mode") != "filter_mode":
            return False
        try:
            hour, minute = int(timing["hour"]), int(timing["minute"])
        except (KeyError, TypeError, ValueError):
            return False
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return False
        now = self.now()
        today = now.date().isoformat()
        if (now.hour, now.minute) != (hour, minute) or timing.get("last_attempt_date") == today:
            return False
        if self._stop.is_set():
            return False
        try:
            result = self.run_filter("BOSS直聘")
        except Exception as exc:
            result = f"启动失败：{exc}"
        # Persist the attempt before the next wake so a login page or invalid
        # task cannot trigger repeated browser launches in the same minute.
        self.store.set_apply_config("timing.last_attempt_date", today)
        self.store.set_apply_config("timing.last_result", result)
        if result == "已运行":
            self.store.set_apply_config("timing.last_run_date", today)
            return True
        return False

    def current_message(self) -> str:
        timing = self.store.get_apply_config("timing") or {}
        if (timing.get("last_attempt_date") == self.now().date().isoformat()
                and timing.get("last_result") not in (None, "", "已运行")):
            return f"定时筛选未启动：{timing['last_result']}"
        return ""

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                # The controller exposes run errors; a settings read error must
                # not bring down the desktop app or start another browser.
                pass
            self._wake.wait(self.poll_seconds)
            self._wake.clear()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backend import LocalStore
from scheduler import DailyFilterScheduler


class SchedulerTests(unittest.TestCase):
    def test_opt_in_daily_filter_runs_once_in_selected_minute(self):
        with tempfile.TemporaryDirectory() as tmp:
            with LocalStore(Path(tmp) / "app.sqlite3") as store:
                store.set_apply_config("work_mode", "filter_mode")
                clock = [datetime(2026, 10, 17, 8, 59, 55)]
                calls = []
                scheduler = DailyFilterScheduler(
                    store, lambda platform: calls.append(platform) or "已运行",
                    now=lambda: clock[0],
                )
                self.assertFalse(scheduler.check_once())
                store.set_apply_config("timing.enable", True)
                self.assertFalse(scheduler.check_once())
                clock[0] = datetime(2026, 10, 17, 9, 0, 2)
                self.assertTrue(scheduler.check_once())
                self.assertFalse(scheduler.check_once())
                self.assertEqual(calls, ["BOSS直聘"])
                self.assertEqual(store.get_apply_config("timing.last_attempt_date"), "2026-10-17")
                self.assertEqual(store.get_apply_config("timing.last_run_date"), "2026-10-17")
                clock[0] = datetime(2026, 10, 18, 9, 0, 2)
                self.assertTrue(scheduler.check_once())
                self.assertEqual(len(calls), 2)

    def test_invalid_time_and_failed_start_do_not_record_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with LocalStore(Path(tmp) / "app.sqlite3") as store:
                store.set_apply_config("work_mode", "filter_mode")
                store.set_apply_config("timing.enable", True)
                store.set_apply_config("timing.hour", 24)
                calls = []
                scheduler = DailyFilterScheduler(
                    store, lambda platform: calls.append(platform) or "无任务",
                    now=lambda: datetime(2026, 10, 17, 9, 0, 2),
                )
                self.assertFalse(scheduler.check_once())
                store.set_apply_config("timing.hour", 9)
                self.assertFalse(scheduler.check_once())
                self.assertEqual(calls, ["BOSS直聘"])
                self.assertIsNone(store.get_apply_config("timing.last_run_date"))
                self.assertIn("无任务", scheduler.current_message())

    def test_timer_never_starts_application_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with LocalStore(Path(tmp) / "app.sqlite3") as store:
                store.set_apply_config("work_mode", "apply_mode")
                store.set_apply_config("timing.enable", True)
                calls = []
                scheduler = DailyFilterScheduler(
                    store, lambda platform: calls.append(platform) or "已运行",
                    now=lambda: datetime(2026, 10, 17, 9, 0, 2),
                )
                self.assertFalse(scheduler.check_once())
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

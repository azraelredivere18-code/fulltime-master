import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from app import WindowAPI, WindowManager


class FakeController:
    platform_name = "BOSS直聘"

    def __init__(self):
        self.started = 0

    def get_run_status(self):
        return {"running": False}

    def start(self, platform):
        self.started += 1
        return "已运行"


class ActiveController:
    def __init__(self, platform):
        self.platform_name = platform
        self.running = False
        self.stopped = 0

    def get_run_status(self):
        return {"running": self.running, "platform": self.platform_name,
                "message": "正在投递" if self.running else "未运行",
                "current": 1, "total": 1, "saved": 0, "applied": 0,
                "daily_used": 0, "daily_limit": 30}

    def start(self, platform):
        self.running = True
        return "已运行"

    def stop(self):
        self.running = False
        self.stopped += 1
        return "已停止"


class RunModeTests(unittest.TestCase):
    def test_two_platforms_run_and_stop_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            api = WindowAPI(manager.db_path, manager, "index")
            manager._windows["index"] = api
            windows = {name: SimpleNamespace(events=SimpleNamespace(closed=threading.Event()))
                       for name in ("BOSS直聘", "智联招聘", "前程无忧")}
            manager._browser_windows.update(windows)
            manager._browser_window = windows["BOSS直聘"]
            manager.controllers = {name: ActiveController(name) for name in windows}
            api.get_login_status = lambda platform: "logged_in"
            try:
                self.assertIs(manager.current_browser_window("智联招聘"), windows["智联招聘"])
                self.assertEqual(api.start("BOSS直聘", "apply_mode"), "已运行")
                self.assertEqual(api.start("智联招聘", "apply_mode"), "已运行")
                self.assertTrue(api.get_run_status()["running"])
                self.assertEqual(len(api.get_run_status()["platforms"]), 3)
                self.assertIn("最多同时运行两个平台", api.start("前程无忧", "apply_mode"))
                self.assertEqual(api.stop("BOSS直聘"), "已停止")
                self.assertFalse(api.get_run_status("BOSS直聘")["running"])
                self.assertTrue(api.get_run_status("智联招聘")["running"])
                self.assertEqual(api.start("前程无忧", "apply_mode"), "已运行")
            finally:
                api.close()

    def test_auto_mode_requires_manual_login_before_start(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            api = WindowAPI(manager.db_path, manager, "index")
            manager._windows["index"] = api
            manager.controller = FakeController()
            try:
                self.assertIn("手动登录", api.start("BOSS直聘", "apply_mode"))
                self.assertEqual(manager.controller.started, 0)
                self.assertEqual(api.get_apply_config("work_mode"), "apply_mode")
                self.assertIn("仅支持自动投递", api.start("BOSS直聘", "filter_mode"))
                manager._browser_window = SimpleNamespace(events=SimpleNamespace(closed=threading.Event()))
                api.get_login_status = lambda platform: "logged_in"
                self.assertEqual(api.start("BOSS直聘", "apply_mode"), "已运行")
                self.assertEqual(manager.controller.started, 1)
            finally:
                api.close()

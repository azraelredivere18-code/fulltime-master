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


class RunModeTests(unittest.TestCase):
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

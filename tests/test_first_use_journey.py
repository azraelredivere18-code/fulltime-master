"""Exercise the first-use gate and record path across the public API and worker."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from app import WindowAPI, WindowManager
from automation import AutomationController


class JourneyBrowser:
    def __init__(self):
        self.url = "https://passport.zhipin.com/login"
        self.events = SimpleNamespace(closed=threading.Event())
        self.shown = 0

    def get_current_url(self):
        return self.url

    def run_js(self, script):
        return "shown" if "fulltime-master-guidance" in script else "logged_in"

    def show(self):
        self.shown += 1


class JourneyJobsPage:
    def __init__(self):
        self.url = ""
        self.applied = []

    def get(self, url):
        self.url = url
        return True

    def login_state(self):
        return "logged_in"

    def eles(self, locator, timeout=0):
        return [{"title": "Python 开发", "company": "甲公司", "area": "上海",
                 "salary": "20-30K", "experience": "3-5年", "education": "本科",
                 "employment_type": "full_time",
                 "link": "https://www.zhipin.com/job_detail/journey.html"}]

    def apply_job(self, link):
        self.applied.append(link)
        return {"state": "sent", "clicked": True}


class FirstUseJourneyTests(unittest.TestCase):
    def test_manual_login_resume_confirmation_apply_and_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code_dir = root / "config" / "boss"
            code_dir.mkdir(parents=True)
            (code_dir / "code.json").write_text(json.dumps({"上海": 101020100}), encoding="utf-8")
            manager = WindowManager(root / "data")
            api = WindowAPI(manager.db_path, manager, "index")
            manager._windows["index"] = api
            page = JourneyJobsPage()
            controller = AutomationController(api, config_dir=root / "config",
                                              page_factory=lambda: page, poll_seconds=0.01)
            manager.controllers["BOSS直聘"] = controller
            api.save_task({"keyword": "Python", "city": "上海", "search_re": "Python",
                           "job_re": "", "resume": "", "match_degree": 0,
                           "platform": "BOSS直聘", "employment_type": "full_time",
                           "recruitment_track": "all"})
            browser = JourneyBrowser()
            try:
                self.assertIn("打开", api.start("BOSS直聘", "apply_mode"))
                manager._browser_windows["BOSS直聘"] = browser
                self.assertEqual(api.get_login_status("BOSS直聘"), "logged_out")
                self.assertTrue(api.show_browser_guidance("BOSS直聘", "login"))
                self.assertEqual(browser.shown, 1)
                browser.url = "https://www.zhipin.com/web/geek/jobs"
                self.assertIn("网站简历", api.start("BOSS直聘", "apply_mode"))
                self.assertEqual(api.acknowledge_platform_resume("BOSS直聘")["state"], "manual")
                self.assertEqual(api.start("BOSS直聘", "apply_mode"), "已运行")
                deadline = time.monotonic() + 2
                while not api.get_apply_record() and time.monotonic() < deadline:
                    time.sleep(0.01)
                records = api.get_apply_record()
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["submit"], "是")
                self.assertEqual((records[0]["company"], records[0]["salary"]),
                                 ("甲公司", "20-30K"))
                self.assertEqual(len(page.applied), 1)
                browser.url = "https://passport.zhipin.com/login"
                deadline = time.monotonic() + 2
                while api.get_run_status("BOSS直聘")["running"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertFalse(api.get_run_status("BOSS直聘")["running"])
                self.assertIn("简历需要重新确认", api.get_run_status("BOSS直聘")["message"])
                self.assertEqual(api.get_platform_resume_setup("BOSS直聘")["state"], "unprepared")
            finally:
                controller.close()
                api.close()


if __name__ == "__main__":
    unittest.main()

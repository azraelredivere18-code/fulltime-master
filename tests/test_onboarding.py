import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from app import WindowAPI, WindowManager
from embedded_browser import new_resume_receipt
from onboarding import browser_guidance_script


class ResumeBrowser:
    def __init__(self, url, replies):
        self.url = url
        self.replies = list(replies)
        self.scripts = []
        self.shown = 0
        self.loaded_urls = []
        self.events = SimpleNamespace(closed=threading.Event())

    def get_current_url(self):
        return self.url

    def run_js(self, script):
        self.scripts.append(script)
        return self.replies.pop(0)

    def show(self):
        self.shown += 1

    def load_url(self, url):
        self.loaded_urls.append(url)
        self.url = url


class OnboardingTests(unittest.TestCase):
    def test_resume_upload_needs_new_receipt(self):
        self.assertFalse(new_resume_receipt(["上传成功"], ["上传成功"]))
        self.assertTrue(new_resume_receipt(["上传成功"], ["上传成功", "上传成功"]))
        self.assertTrue(new_resume_receipt([], ["简历上传成功"]))
        self.assertFalse(new_resume_receipt([], None))

    def test_browser_guidance_escapes_platform_and_rejects_unknown_kind(self):
        script = browser_guidance_script('测试"平台', "login")
        self.assertIn(json.dumps('测试"平台', ensure_ascii=True), script)
        self.assertIn("textContent", script)
        with self.assertRaises(ValueError):
            browser_guidance_script("测试", "submit")

    def test_browser_guidance_only_focuses_when_newly_shown(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            api = WindowAPI(manager.db_path, manager, "index")
            browser = ResumeBrowser("https://www.zhipin.com/web/geek/jobs",
                                    ["shown", "already", "dismissed"])
            manager._browser_windows["BOSS直聘"] = browser
            try:
                self.assertTrue(api.show_browser_guidance("BOSS直聘", "login"))
                self.assertTrue(api.show_browser_guidance("BOSS直聘", "login"))
                self.assertTrue(api.show_browser_guidance("BOSS直聘", "login"))
                self.assertEqual(browser.shown, 1)
            finally:
                api.close()

    def test_resume_confirmation_expires_after_logout_or_new_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            api = WindowAPI(manager.db_path, manager, "index")
            browser = ResumeBrowser("https://www.zhipin.com/web/geek/jobs",
                                    ["logged_in", "logged_in", "logged_in"])
            manager._browser_windows["BOSS直聘"] = browser
            try:
                self.assertEqual(api.get_login_status("BOSS直聘"), "logged_in")
                self.assertEqual(api.acknowledge_platform_resume("BOSS直聘")["state"], "manual")
                self.assertEqual(api.get_platform_resume_setup("BOSS直聘")["state"], "manual")
                browser.url = "https://passport.zhipin.com/login"
                self.assertEqual(api.get_login_status("BOSS直聘"), "logged_out")
                self.assertEqual(api.get_platform_resume_setup("BOSS直聘")["state"], "unprepared")
                browser.url = "https://www.zhipin.com/web/geek/jobs"
                self.assertEqual(api.acknowledge_platform_resume("BOSS直聘")["state"], "manual")
                manager._browser_windows["BOSS直聘"] = ResumeBrowser(browser.url, [])
                self.assertEqual(api.get_platform_resume_setup("BOSS直聘")["state"], "unprepared")
            finally:
                api.close()

    def test_reconnect_preserves_same_platform_login_page(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            browser = ResumeBrowser("https://passport.zhipin.com/login", [])
            manager._browser_windows["BOSS直聘"] = browser
            manager.open_browser_window("https://www.zhipin.com/web/geek/jobs", "BOSS直聘")
            self.assertEqual(browser.loaded_urls, [])
            self.assertEqual(browser.shown, 1)

    def test_resume_form_requires_site_page_and_fresh_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            browser = ResumeBrowser("https://www.zhipin.com/web/geek/resume", [
                {"state": "ok", "fingerprint": "abc", "available": ["full_name"],
                 "targets": [{"field": "full_name", "label": "姓名"}]},
                {"state": "ok", "fingerprint": "abc", "available": ["full_name"]},
                {"state": "ok", "filled": ["full_name"]},
            ])
            manager._browser_windows["BOSS直聘"] = browser
            profile = {"full_name": "测试用户", "id_number": "123456789012345678"}
            self.assertEqual(manager.platform_resume_form_action("BOSS直聘", profile, fill=False)["state"], "ok")
            self.assertEqual(manager.platform_resume_form_action("BOSS直聘", profile, fill=True)["filled"], ["full_name"])
            self.assertEqual(len(browser.scripts), 3)
            self.assertTrue(all("123456789012345678" not in script for script in browser.scripts))
            browser.url = "https://www.zhipin.com/web/geek/jobs"
            self.assertEqual(manager.platform_resume_form_action("BOSS直聘", profile, fill=False)["state"], "wrong_page")

    def test_resume_form_never_fills_after_url_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = WindowManager(Path(folder))
            browser = ResumeBrowser("https://www.zhipin.com/web/geek/resume", [
                {"state": "ok", "fingerprint": "abc", "available": ["full_name"]},
            ])
            manager._browser_windows["BOSS直聘"] = browser
            profile = {"full_name": "测试用户"}
            manager.platform_resume_form_action("BOSS直聘", profile, fill=False)
            browser.url = "https://www.zhipin.com/web/geek/resume?section=other"
            self.assertEqual(manager.platform_resume_form_action("BOSS直聘", profile, fill=True)["state"], "stale_preview")
            self.assertEqual(len(browser.scripts), 1)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from app import WindowManager
from embedded_browser import new_resume_receipt
from onboarding import browser_guidance_script


class ResumeBrowser:
    def __init__(self, url, replies):
        self.url = url
        self.replies = list(replies)
        self.scripts = []
        self.events = SimpleNamespace(closed=threading.Event())

    def get_current_url(self):
        return self.url

    def run_js(self, script):
        self.scripts.append(script)
        return self.replies.pop(0)


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

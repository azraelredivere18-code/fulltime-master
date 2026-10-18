import threading
import unittest

from automation import parse_boss_card
from embedded_browser import CARD_LOCATOR, DETAIL_LOCATOR, EmbeddedBossPage


class FakeWindow:
    def __init__(self, url, result):
        self.url = url
        self.result = result
        self.events = type("Events", (), {"loaded": threading.Event()})()
        self.events.loaded.set()
        self.visits = []
        self.closed = False

    def get_current_url(self):
        return self.url

    def load_url(self, url):
        self.url = url
        self.visits.append(url)

    def evaluate_js(self, script):
        return self.result

    def run_js(self, script):
        return self.result

    def destroy(self):
        self.closed = True


class FakeManager:
    def __init__(self, window):
        self.window = window
        self.open_count = 0
        self.detail = FakeWindow("https://www.zhipin.com/job_detail/1.html", "支持远程")

    def current_browser_window(self, platform=None):
        return self.window

    def open_browser_window(self, platform=None):
        self.open_count += 1
        return self.window

    def open_detail_window(self, url):
        self.detail.url = url
        return self.detail

    def close_browser_window(self, platform=None):
        self.window = None


class EmbeddedBrowserTests(unittest.TestCase):
    def test_login_window_is_reused_for_job_read_and_detail(self):
        window = FakeWindow("https://www.zhipin.com/", [{
            "title": "Python 开发", "company": "甲公司", "salary": "20-30K",
            "area": "上海", "hr_title": "HR", "activity": "今日活跃",
            "summary": "Python 开发", "link": "/job_detail/1.html",
        }])
        manager = FakeManager(window)
        page = EmbeddedBossPage(manager)
        search = "https://www.zhipin.com/web/geek/jobs?query=Python&city=101020100"
        self.assertTrue(page.get(search))
        self.assertIs(manager.current_browser_window(), window)
        self.assertEqual(page.url, search)
        self.assertEqual(manager.open_count, 1)
        cards = page.eles(CARD_LOCATOR)
        self.assertEqual(parse_boss_card(cards[0])["title"], "Python 开发")
        detail = page.new_tab("https://www.zhipin.com/job_detail/1.html")
        self.assertEqual(detail.ele(DETAIL_LOCATOR).text, "支持远程")
        detail.close()
        self.assertTrue(manager.detail.closed)

    def test_closed_window_reports_clear_error_and_rejects_external_links(self):
        manager = FakeManager(FakeWindow("https://www.zhipin.com/", []))
        page = EmbeddedBossPage(manager)
        manager.window = None
        with self.assertRaisesRegex(RuntimeError, "内置浏览器已关闭"):
            page.eles(CARD_LOCATOR)
        with self.assertRaisesRegex(ValueError, "只能导航"):
            page.get("https://example.com/")
        with self.assertRaisesRegex(ValueError, "职位详情链接无效"):
            page.new_tab("https://example.com/job_detail/1.html")


if __name__ == "__main__":
    unittest.main()

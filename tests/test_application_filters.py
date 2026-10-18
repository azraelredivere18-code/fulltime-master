import unittest

from application_filters import applied_company_reason, off_site_reason


class ApplicationFilterTests(unittest.TestCase):
    def test_confirmed_company_filter_respects_platform_and_ten_day_window(self):
        rows = [
            {"company": " 甲 公司 ", "source": "BOSS直聘", "submit": "是",
             "submit_time": "2026-10-08T09:00:00"},
            {"company": "乙公司", "source": "前程无忧", "submit": "是",
             "submit_time": "2026-10-17T09:00:00"},
            {"company": "丙公司", "source": "BOSS直聘", "submit": "否",
             "submit_time": "2026-10-17T09:00:00"},
            {"company": "丁公司", "source": "BOSS直聘", "submit": "是",
             "submit_time": "2026-10-07T09:00:00"},
        ]
        same = "过滤10天内同一平台投递过的公司"
        all_sites = "过滤10天内不同平台投递过的公司"
        self.assertIsNotNone(applied_company_reason("甲公司", rows, same, "BOSS直聘", "2026-10-17"))
        self.assertIsNone(applied_company_reason("乙公司", rows, same, "BOSS直聘", "2026-10-17"))
        self.assertIsNotNone(applied_company_reason("乙公司", rows, all_sites, "BOSS直聘", "2026-10-17"))
        for company in ("丙公司", "丁公司", "", "甲公司分公司"):
            self.assertIsNone(applied_company_reason(company, rows, all_sites, "BOSS直聘", "2026-10-17"))

    def test_region_filter_rejects_only_clear_different_city(self):
        cities = {"上海", "北京", "广州", "深圳"}
        self.assertIsNone(off_site_reason("上海·浦东新区", "上海", cities, applying=True))
        self.assertIn("异地职位", off_site_reason("北京·朝阳区", "上海", cities, applying=True))
        self.assertIn("未确认", off_site_reason("", "上海", cities, applying=True))
        self.assertIn("未确认", off_site_reason("上海/北京", "上海", cities, applying=True))
        self.assertIsNone(off_site_reason("", "上海", cities, applying=False))


if __name__ == "__main__":
    unittest.main()

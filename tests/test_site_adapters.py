import tempfile
import sqlite3
import unittest
from pathlib import Path

from backend import LocalStore
from site_adapters import SITES, valid_site_url
from site_automation import SiteAutomationController, parse_site_card


class SiteAdapterTests(unittest.TestCase):
    def test_legacy_slot_table_migrates_to_boss_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.sqlite3"
            db = sqlite3.connect(path)
            try:
                db.execute("CREATE TABLE application_slot (day TEXT NOT NULL, link TEXT NOT NULL, "
                           "city TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, "
                           "PRIMARY KEY(day,link))")
                db.execute("INSERT INTO application_slot VALUES(?,?,?,?,?)", (
                    "2026-10-17", "https://www.zhipin.com/job_detail/1.html",
                    "上海", "unknown", "2026-10-17T10:00:00"))
                db.commit()
            finally:
                db.close()
            store = LocalStore(path)
            try:
                self.assertEqual(store.daily_application_usage("2026-10-17", "BOSS直聘")["total"], 1)
                self.assertEqual(store.daily_application_usage("2026-10-17", "前程无忧")["total"], 0)
            finally:
                store.close()

    def test_job_links_stay_on_selected_site(self):
        zhilian = SITES["智联招聘"]
        qiancheng = SITES["前程无忧"]
        yjs = SITES["应届生"]
        liepin = SITES["猎聘"]
        lagou = SITES["拉勾"]
        niuke = SITES["牛客网"]
        self.assertTrue(valid_site_url(zhilian, "https://www.zhaopin.com/jobdetail/123", detail=True))
        self.assertTrue(valid_site_url(qiancheng, "https://we.51job.com/pc/job/123", detail=True))
        self.assertFalse(valid_site_url(zhilian, "https://evil.example/jobdetail/123", detail=True))
        self.assertFalse(valid_site_url(qiancheng, "https://q.yingjiesheng.com/jobs/123", detail=True))
        self.assertTrue(valid_site_url(yjs, "https://q.yingjiesheng.com/jobs/123", detail=True))
        self.assertTrue(valid_site_url(liepin, "https://www.liepin.com/job/123.shtml", detail=True))
        self.assertTrue(valid_site_url(lagou, "https://www.lagou.com/jobs/123.html", detail=True))
        self.assertFalse(valid_site_url(lagou, "https://www.liepin.com/job/123.shtml", detail=True))
        self.assertFalse(valid_site_url(liepin, "http://www.liepin.com/job/123.shtml", detail=True))
        self.assertTrue(valid_site_url(niuke, "https://www.nowcoder.com/jobs/detail/340669", detail=True))
        self.assertFalse(valid_site_url(niuke, "https://www.nowcoder.com/jobs/intern/center", detail=True))
        self.assertIsNone(parse_site_card({"title": "工程师", "link": "https://evil.example/jobdetail/123"}, zhilian))

    def test_sites_have_separate_daily_ledgers_and_pending_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.sqlite3"
            store = LocalStore(path)
            day = "2026-10-17"
            z_link = "https://www.zhaopin.com/jobdetail/123"
            q_link = "https://we.51job.com/pc/job/123"
            try:
                self.assertEqual(store.reserve_application_slot(z_link, "广州", day=day,
                    platform="智联招聘", daily_limit=30), "reserved")
                store.finalize_application_slot(z_link, "unknown", day=day, platform="智联招聘")
                self.assertEqual(store.reserve_application_slot(q_link, "上海", day=day,
                    platform="前程无忧", daily_limit=30), "reserved")
                self.assertEqual(store.daily_application_usage(day, "BOSS直聘")["total"], 0)
            finally:
                store.close()
            store = LocalStore(path)
            try:
                self.assertEqual(store.daily_application_usage(day, "智联招聘")["total"], 1)
                self.assertEqual(store.daily_application_usage(day, "前程无忧")["total"], 1)
                self.assertEqual(store.reserve_application_slot(z_link, "广州", day=day,
                    platform="智联招聘", daily_limit=30), "duplicate")
                store.finalize_application_slot(z_link, "confirmed", day=day, platform="智联招聘")
                self.assertEqual(store.daily_application_usage(day, "智联招聘")["total"], 1)
            finally:
                store.close()

    def test_new_site_uses_its_city_code_and_task_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            store = LocalStore(Path(temp) / "app.sqlite3")
            try:
                store.save_task({"keyword": "产品经理", "city": "上海", "platform": "前程无忧",
                                 "match_degree": 0})
                store.save_task({"keyword": "设计师", "city": "北京", "platform": "智联招聘",
                                 "match_degree": 0})
                config = Path(__file__).resolve().parents[1] / "config"
                q = SiteAutomationController(store, site=SITES["前程无忧"],
                                             page_factory=lambda: None, config_dir=config)
                z = SiteAutomationController(store, site=SITES["智联招聘"],
                                             page_factory=lambda: None, config_dir=config)
                yjs = SiteAutomationController(store, site=SITES["应届生"],
                                               page_factory=lambda: None, config_dir=config)
                self.assertEqual([(p[1], p[2], p[3]) for p in q._build_plans()],
                                 [("产品经理", "上海", "020000")])
                self.assertEqual([(p[1], p[2], p[3]) for p in z._build_plans()],
                                 [("设计师", "北京", "北京")])
                self.assertEqual(yjs._city_code("上海"), "020000")
                liepin = SiteAutomationController(store, site=SITES["猎聘"],
                                                  page_factory=lambda: None, config_dir=config)
                lagou = SiteAutomationController(store, site=SITES["拉勾"],
                                                page_factory=lambda: None, config_dir=config)
                self.assertTrue(liepin._city_code("上海"))
                self.assertEqual(lagou._city_code("上海"), "上海")
                niuke = SiteAutomationController(store, site=SITES["牛客网"],
                                                 page_factory=lambda: None, config_dir=config)
                self.assertEqual(niuke._city_code("上海"), "上海")
            finally:
                store.close()

    def test_site_specific_filter_validation_does_not_run_boss_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            with LocalStore(Path(temp) / "filters.sqlite3") as store:
                store.save_task({"keyword": "设计", "city": "上海", "platform": "前程无忧",
                                 "match_degree": 0})
                q = SiteAutomationController(store, site=SITES["前程无忧"],
                                             page_factory=lambda: None)
                self.assertEqual(len(q._build_plans()), 1)
                store.set_apply_config("qiancheng.filter.target", "只投HR")
                with self.assertRaisesRegex(ValueError, "前程无忧.*target"):
                    q._build_plans()
                store.set_apply_config("qiancheng.filter", {})
                self.assertEqual(len(q._build_plans()), 1)

    def test_new_site_record_backfill_preserves_submission_result(self):
        with tempfile.TemporaryDirectory() as temp:
            store = LocalStore(Path(temp) / "records.sqlite3")
            link = "https://we.51job.com/pc/job/123"
            record_id = store.add_apply_record({
                "source": "前程无忧", "link": link, "title": "管理培训生",
                "submit": "是", "attempt_state": "confirmed", "remarks": "已投递",
            })

            class Detail:
                url = link
                def metadata(self):
                    return {"company": "乙公司", "area": "上海", "salary": "8-9千",
                            "experience": "1-3年", "education": "本科"}
                def ele(self, locator, timeout=0):
                    return None
                def close(self):
                    pass

            class Page:
                def login_state(self):
                    return "logged_in"
                def new_tab(self, url, background=True):
                    assert url == link
                    return Detail()

            try:
                controller = SiteAutomationController(
                    store, site=SITES["前程无忧"], page_factory=Page)
                self.assertEqual(controller.backfill_record_metadata(), {"checked": 1, "updated": 1})
                record = next(row for row in store.get_apply_record() if row["id"] == record_id)
                self.assertEqual((record["company"], record["area"], record["salary"]),
                                 ("乙公司", "上海", "8-9千"))
                self.assertEqual((record["experience"], record["education"]), ("1-3年", "本科"))
                self.assertEqual((record["submit"], record["attempt_state"]), ("是", "confirmed"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

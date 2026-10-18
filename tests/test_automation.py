import json
import tempfile
import time
import unittest
from pathlib import Path

from automation import AutomationController, boss_search_url, parse_boss_card
from backend import LocalStore, china_day


class FakeElement:
    def __init__(self, text="", href=""):
        self.text = text
        self.href = href

    def attr(self, key):
        return self.href if key == "href" else None


class FakeCard:
    def __init__(self, title, company, href, summary="", hr_title="", activity=""):
        self.elements = {
            ".job-name": FakeElement(title),
            ".company-name": FakeElement(company),
            ".salary": FakeElement("20-30K"),
            ".job-area": FakeElement("上海"),
            ".boss-info-attr": FakeElement(hr_title),
            ".boss-active-time": FakeElement(activity),
            'a[href*="/job_detail/"]': FakeElement(href=href),
        }
        self.text = summary or f"{title} {company}"

    def ele(self, locator, timeout=0):
        return self.elements.get(locator.removeprefix("css:"))


class FakePage:
    def __init__(self, cards):
        self.cards = cards
        self.urls = []
        self.url = ""
        self.tab_id = "test"
        self.activated = False
        self.details = {}
        self.detail_metadata = {}

    def get(self, url):
        self.urls.append(url)
        self.url = url
        return True

    def eles(self, locator, timeout=0):
        assert locator == "css:.card-area .job-card-wrap, .job-card-wrapper"
        return self.cards

    def activate_tab(self, tab_id):
        self.activated = True

    def new_tab(self, url, background=False):
        text = self.details.get(url)
        class DetailTab:
            def __init__(self):
                self.url = url
                self.closed = False

            def ele(self, locator, timeout=0):
                assert locator == "css:.job-detail-section:nth-child(1) .job-sec-text"
                return FakeElement(text) if text else None

            def close(self):
                self.closed = True

            def metadata(self):
                return self_detail_metadata.get(url, {})
        self_detail_metadata = self.detail_metadata
        return DetailTab()

    def quit(self, **kwargs):
        pass


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config" / "boss"
        self.config.mkdir(parents=True)
        (self.config / "code.json").write_text(
            json.dumps({"上海": 101020100, "北京": 101010100, "广州": 101280100}), encoding="utf-8"
        )
        self.store = LocalStore(self.root / "data" / "app.sqlite3")
        self.store.set_apply_config("work_mode", "filter_mode")
        self.store.save_task({
            "keyword": "Python", "city": "上海", "search_prompt": "", "job_prompt": "",
            "search_re": "Python", "job_re": "", "resume": "", "match_degree": 0,
            "platform": "BOSS直聘",
        })

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_boss_url_uses_recovered_city_code(self):
        self.assertEqual(
            boss_search_url("数据 分析", 101020100),
            "https://www.zhipin.com/web/geek/jobs?query=%E6%95%B0%E6%8D%AE+%E5%88%86%E6%9E%90&city=101020100",
        )

    def test_parse_rejects_non_boss_and_missing_title(self):
        self.assertIsNone(parse_boss_card(FakeCard("", "甲公司", "/job_detail/123.html")))
        self.assertIsNone(parse_boss_card(FakeCard("Python", "甲公司", "https://example.com/job")))
        parsed = parse_boss_card({"title": "兼职", "link": "/job_detail/part.html",
                                  "experience": "5天/周", "education": "3个月"})
        self.assertEqual((parsed["experience"], parsed["education"]), ("", ""))

    def test_start_filters_and_deduplicates_read_only_records(self):
        page = FakePage([
            FakeCard("Python 开发", "甲公司", "/job_detail/123.html"),
            FakeCard("Java 开发", "Python乙公司", "/job_detail/456.html", summary="Python 在描述中出现"),
            FakeCard("Python 测试", "黑名单科技", "/job_detail/789.html"),
        ])
        self.store.save_blocklist({"company": "黑名单"})
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page, poll_seconds=0.01,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        for _ in range(100):
            if len(self.store.get_apply_record()) >= 3:
                break
            time.sleep(0.01)
        self.assertEqual(controller.stop(), "已停止")
        self.assertEqual(len(self.store.get_apply_record()), 3)
        item = next(row for row in self.store.get_apply_record() if row["title"] == "Python 开发")
        self.assertEqual(item["title"], "Python 开发")
        self.assertEqual(item["submit"], "否")
        self.assertEqual(item["link"], "https://www.zhipin.com/job_detail/123.html")
        rejected = next(row for row in self.store.get_apply_record() if row["title"] == "Java 开发")
        self.assertEqual(rejected["submit"], "否")
        self.assertEqual(rejected["remarks"], "正则筛选职位不符合")
        blocked = next(row for row in self.store.get_apply_record() if row["title"] == "Python 测试")
        self.assertEqual(blocked["remarks"], "公司黑名单")
        self.assertEqual(page.urls[0], boss_search_url("Python", 101020100))
        self.assertEqual(controller.scan_once(), 0)
        controller.close()

    def test_rejects_unimplemented_modes_and_ai_rules(self):
        controller = AutomationController(self.store, config_dir=self.root / "config", page_factory=lambda: FakePage([]))
        self.assertIn("尚未完成", controller.start("猎聘"))
        self.store.set_apply_config("work_mode", "application_mode")
        self.assertIn("无效", controller.start("BOSS直聘"))
        self.store.set_apply_config("work_mode", "filter_mode")
        task = self.store.get_task("BOSS直聘")
        task["job_prompt"] = "请分析岗位需求"
        self.store.update_task(task)
        self.assertIn("AI 提示词", controller.start("BOSS直聘"))

    def test_all_selected_tasks_keywords_and_cities_run_sequentially(self):
        first = self.store.get_task("BOSS直聘")
        first["keyword"] = "Python_开发 数据_分析"
        first["city"] = "上海 北京"
        self.store.update_task(first)
        self.store.save_task({
            "keyword": "Go", "city": "北京", "search_prompt": "", "job_prompt": "",
            "search_re": "", "job_re": "", "resume": "", "match_degree": 0,
            "platform": "BOSS直聘,猎聘",
        })
        page = FakePage([])
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=0.02,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 2
        while len(page.urls) < 5 and time.monotonic() < deadline:
            time.sleep(0.01)
        controller.stop()
        self.assertEqual(page.urls, [
            boss_search_url("Python 开发", 101020100),
            boss_search_url("数据 分析", 101020100),
            boss_search_url("Python 开发", 101010100),
            boss_search_url("数据 分析", 101010100),
            boss_search_url("Go", 101010100),
        ])
        controller.close()

    def test_security_verification_pauses_search_until_user_returns(self):
        task = self.store.get_task("BOSS直聘")
        task["city"] = "上海 北京"
        self.store.update_task(task)
        page = FakePage([])
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=0.03,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        page.url = "https://www.zhipin.com/web/passport/zp/verify.html?code=35"
        time.sleep(0.1)
        self.assertEqual(len(page.urls), 1)
        self.assertIn("安全验证", controller.get_run_status()["message"])
        page.url = page.urls[0]
        deadline = time.monotonic() + 1
        while len(page.urls) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(page.urls), 2)
        controller.close()

    def test_same_job_is_evaluated_separately_for_two_tasks(self):
        first = self.store.get_task("BOSS直聘")
        first["search_re"] = "Java"
        self.store.update_task(first)
        second_id = self.store.save_task({
            "keyword": "Python", "city": "上海", "search_prompt": "", "job_prompt": "",
            "search_re": "Python", "job_re": "", "resume": "", "match_degree": 0,
            "platform": "BOSS直聘",
        })
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/123.html")])
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=0.03,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while len(self.store.get_apply_record()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = self.store.get_apply_record()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["task_id"] for row in rows}, {first["id"], second_id})
        self.assertEqual({row["remarks"] for row in rows},
                         {"正则筛选职位不符合", "仅筛选保存；未自动投递"})
        controller.close()

    def test_job_detail_regex_and_retryable_missing_description(self):
        task = self.store.get_task("BOSS直聘")
        task["job_re"] = "远程"
        self.store.update_task(task)
        page = FakePage([
            FakeCard("Python 开发", "甲公司", "/job_detail/1.html"),
            FakeCard("Python 测试", "乙公司", "/job_detail/2.html"),
            FakeCard("Python 运维", "丙公司", "/job_detail/3.html"),
        ])
        page.details = {
            "https://www.zhipin.com/job_detail/1.html": "支持远程工作",
            "https://www.zhipin.com/job_detail/2.html": "需要到岗",
        }
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=10,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while len(self.store.get_apply_record()) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = {row["title"]: row for row in self.store.get_apply_record()}
        self.assertEqual(rows["Python 开发"]["remarks"], "仅筛选保存；未自动投递")
        self.assertEqual(rows["Python 测试"]["remarks"], "详情正则筛选职位不符合")
        self.assertEqual(rows["Python 运维"]["remarks"], "详情页未读取到职位描述")
        controller.stop()
        page.details["https://www.zhipin.com/job_detail/3.html"] = "可远程"
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            row = next(r for r in self.store.get_apply_record() if r["title"] == "Python 运维")
            if row["remarks"] == "仅筛选保存；未自动投递":
                break
            time.sleep(0.01)
        self.assertEqual(row["remarks"], "仅筛选保存；未自动投递")
        self.assertEqual(len(self.store.get_apply_record()), 3)
        controller.close()

    def test_page_read_failure_is_reported(self):
        class BrokenPage(FakePage):
            def eles(self, locator, timeout=0):
                raise RuntimeError("DOM unavailable")

        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: BrokenPage([]),
            poll_seconds=0.01, dwell_seconds=0.03,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while controller.get_run_status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn("无法读取职位列表", controller.get_run_status()["message"])
        self.assertEqual(self.store.get_apply_record(), [])
        controller.close()

    def test_saved_recruiter_filters_are_applied_and_unsupported_ones_fail(self):
        self.store.set_apply_config("boss.filter.target", "只投HR")
        self.store.set_apply_config("boss.filter.liveness", "是")
        page = FakePage([
            FakeCard("Python 开发", "甲公司", "/job_detail/1.html",
                     hr_title="招聘 HR", activity="今日活跃"),
            FakeCard("Python 测试", "乙公司", "/job_detail/2.html",
                     hr_title="部门经理", activity="今日活跃"),
            FakeCard("Python 运维", "丙公司", "/job_detail/3.html",
                     hr_title="HR", activity="一个月前活跃"),
        ])
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=10,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while len(self.store.get_apply_record()) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = {row["title"]: row["remarks"] for row in self.store.get_apply_record()}
        self.assertEqual(rows["Python 开发"], "仅筛选保存；未自动投递")
        self.assertEqual(rows["Python 测试"], "招聘者类型不符合或未显示")
        self.assertEqual(rows["Python 运维"], "招聘者近期活跃状态未确认")
        controller.close()
        self.store.set_apply_config("boss.filter.工作经验", "1-3年")
        blocked = AutomationController(self.store, config_dir=self.root / "config",
                                       page_factory=lambda: page)
        self.assertIn("工作经验", blocked.start("BOSS直聘"))
        self.store.set_apply_config("boss.filter.工作经验", "")
        self.store.set_apply_config("boss.filter.target", "未知")
        self.assertIn("target", blocked.start("BOSS直聘"))

    def test_sales_exclusion_prevents_contact_and_rechecks_existing_filter_record(self):
        task = self.store.get_task("BOSS直聘")
        task["search_re"] = ""
        self.store.update_task(task)
        link = "https://www.zhipin.com/job_detail/sales.html"
        page = FakePage([FakeCard("高薪销售", "甲公司", link)])
        page.details[link] = "开发客户，完成销售指标"
        page.apply_calls = []
        page.apply_job = lambda url: page.apply_calls.append(url) or {"state": "sent"}
        self.store.set_apply_config("exclude_sales_roles", True)
        self.store.set_apply_config("work_mode", "apply_mode")
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page = page
        controller._task = task
        controller.mode = "apply_mode"
        controller.scan_once()
        row = self.store.get_apply_record()[0]
        self.assertIn("销售岗位已排除", row["remarks"])
        self.assertEqual(row["submit"], "否")
        self.assertEqual(page.apply_calls, [])
        controller.close()

    def test_apply_requires_visible_success_and_does_not_repeat_uncertain_send(self):
        task = self.store.get_task("BOSS直聘")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/123.html")])
        calls = []
        page.apply_job = lambda url: calls.append(url) or {"state": "unknown", "reason": "无回执"}
        self.store.set_apply_config("work_mode", "apply_mode")
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page = page
        controller._task = task
        controller.mode = "apply_mode"
        controller.scan_once()
        controller.scan_once()
        self.assertEqual(len(calls), 1)
        row = self.store.get_apply_record()[0]
        self.assertEqual(row["submit"], "否")
        self.assertIn("未记录为成功", row["remarks"])
        controller.close()

    def test_pending_confirmation_waits_then_reconciles_visible_success(self):
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/pending.html")])
        observations = ["needs_confirmation"]
        page.apply_job = lambda link: {"state": "needs_confirmation", "clicked": True}
        page.check_application_result = lambda link: observations[0]
        self.store.set_apply_config("work_mode", "apply_mode")
        controller = AutomationController(
            self.store, config_dir=self.root / "config", page_factory=lambda: page,
            poll_seconds=0.01, dwell_seconds=10,
        )
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while not self.store.get_apply_record() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.store.get_apply_record()[0]["submit"], "否")
        self.assertEqual(self.store.daily_application_usage()["total"], 1)
        observations[0] = "sent"
        deadline = time.monotonic() + 1
        while self.store.get_apply_record()[0]["submit"] != "是" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.store.get_apply_record()[0]["submit"], "是")
        self.assertEqual(self.store.daily_application_usage()["total"], 1)
        controller.close()

    def test_restart_can_reconcile_pending_record_without_reapplying(self):
        link = "https://www.zhipin.com/job_detail/restart.html"
        day = "2026-10-17"
        self.store.reserve_application_slot(link, "上海", day=day)
        self.store.finalize_application_slot(link, "unknown", day=day)
        record_id = self.store.add_apply_record({
            "source": "BOSS直聘", "link": link, "title": "Python 开发",
            "submit": "否", "attempt_state": "pending", "application_day": day,
            "remarks": "沟通需要人工确认；未记录为成功",
        })
        page = FakePage([])
        page.url = boss_search_url("Python", 101020100)
        page.login_state = lambda: "logged_in"
        observed = ["unknown"]
        page.check_application_result = lambda url: observed[0]
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        self.assertEqual(controller.reconcile_saved_record(record_id)["state"], "unknown")
        self.assertEqual(self.store.get_apply_record()[0]["submit"], "否")
        observed[0] = "sent"
        self.assertEqual(controller.reconcile_saved_record(record_id)["state"], "confirmed")
        self.assertEqual(self.store.get_apply_record()[0]["submit"], "是")
        self.assertEqual(self.store.daily_application_usage(day)["total"], 1)
        controller.close()

    def test_browser_exception_keeps_auditable_uncertain_record(self):
        task = self.store.get_task("BOSS直聘")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/fail.html")])
        def fail(_link):
            raise RuntimeError("browser disconnected")
        page.apply_job = fail
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        row = self.store.get_apply_record()[0]
        self.assertEqual(row["attempt_state"], "pending")
        self.assertIn("browser disconnected", row["remarks"])
        self.assertEqual(self.store.daily_application_usage()["total"], 1)
        controller.close()

    def test_enabling_sales_filter_rechecks_old_saved_candidate(self):
        task = self.store.get_task("BOSS直聘")
        task["search_re"] = ""
        self.store.update_task(task)
        page = FakePage([FakeCard("高薪销售", "甲公司", "/job_detail/123.html")])
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page = page
        controller._task = task
        controller.scan_once()
        self.assertEqual(self.store.get_apply_record()[0]["remarks"], "仅筛选保存；未自动投递")
        self.store.set_apply_config("exclude_sales_roles", True)
        controller.scan_once()
        self.assertIn("销售岗位已排除", self.store.get_apply_record()[0]["remarks"])
        controller.close()

    def test_confirmed_apply_marks_submitted(self):
        task = self.store.get_task("BOSS直聘")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/123.html")])
        page.apply_job = lambda url: {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page = page
        controller._task = task
        controller.mode = "apply_mode"
        self.assertEqual(controller.scan_once(), 1)
        self.assertEqual(self.store.get_apply_record()[0]["submit"], "是")
        self.assertEqual(controller.applied_count, 1)
        controller.close()

    def test_campus_task_waits_for_explicit_detail_evidence_before_contact(self):
        task = self.store.get_task("BOSS直聘")
        task["recruitment_track"] = "campus"
        self.store.update_task(task)
        campus_link = "https://www.zhipin.com/job_detail/campus.html"
        social_link = "https://www.zhipin.com/job_detail/social.html"
        unknown_link = "https://www.zhipin.com/job_detail/unknown.html"
        unreadable_link = "https://www.zhipin.com/job_detail/unreadable.html"
        conflict_link = "https://www.zhipin.com/job_detail/conflict.html"
        page = FakePage([
            FakeCard("Python 开发", "甲公司", campus_link),
            FakeCard("Python 社招开发", "乙公司", social_link),
            FakeCard("Python 开发", "丙公司", unknown_link),
            FakeCard("Python 校招开发", "丁公司", unreadable_link),
            FakeCard("Python 校招开发", "戊公司", conflict_link),
        ])
        page.details[campus_link] = "招聘类型：校园招聘\n工作地点：上海"
        page.details[social_link] = "招聘类型：社会招聘"
        page.details[unknown_link] = "负责产品开发，应届生优先"
        page.details[conflict_link] = "招聘类型：社会招聘"
        calls = []
        page.apply_job = lambda link: calls.append(link) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        controller.scan_once()
        rows = {row["link"]: row for row in self.store.get_apply_record()}
        self.assertEqual(calls, [campus_link])
        self.assertEqual(rows[campus_link]["recruitment_track"], "campus")
        self.assertEqual(rows[social_link]["submit"], "否")
        self.assertIn("未明确", rows[unknown_link]["remarks"])
        self.assertIn("详情页未能核对", rows[unreadable_link]["remarks"])
        self.assertEqual(rows[conflict_link]["submit"], "否")
        controller.close()

    def test_saved_company_filter_blocks_before_application(self):
        task = self.store.get_task("BOSS直聘")
        self.store.add_apply_record({
            "source": "前程无忧", "company": "甲公司", "submit": "是",
            "submit_time": china_day() + "T09:00:00", "title": "其他岗位",
        })
        self.store.set_apply_config("company_filter", "过滤10天内不同平台投递过的公司")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/company.html")])
        calls = []
        page.apply_job = lambda url: calls.append(url) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        row = next(row for row in self.store.get_apply_record() if row["title"] == "Python 开发")
        self.assertIn("已投递公司", row["remarks"])
        self.assertEqual(calls, [])
        controller.close()

    def test_regex_company_blocklist_excludes_matching_employer(self):
        self.store.save_blocklist({"company": "^(甲|乙)公司$"})
        task = self.store.get_task("BOSS直聘")
        page = FakePage([FakeCard("Python 开发", "乙公司", "/job_detail/blocked.html")])
        calls = []
        page.apply_job = lambda url: calls.append(url) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        self.assertEqual(self.store.get_apply_record()[0]["remarks"], "公司黑名单")
        self.assertEqual(calls, [])
        controller.close()

    def test_saved_off_site_filter_blocks_different_and_unknown_location(self):
        task = self.store.get_task("BOSS直聘")
        self.store.set_apply_config("off_site_filter", "过滤")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/other-city.html")])
        page.cards[0].elements[".job-area"].text = "北京·朝阳"
        calls = []
        page.apply_job = lambda url: calls.append(url) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        self.assertIn("异地职位", self.store.get_apply_record()[0]["remarks"])
        page.cards[0].elements[".job-area"].text = ""
        page.cards[0].elements['a[href*="/job_detail/"]'].href = "/job_detail/unknown-city.html"
        controller.scan_once()
        rows = self.store.get_apply_record()
        self.assertTrue(any("岗位地区未确认" in row["remarks"] for row in rows))
        self.assertEqual(calls, [])
        controller.close()

    def test_region_allowance_carries_unused_slots(self):
        task = self.store.get_task("BOSS直聘")
        task["city"] = "上海 北京 广州"
        self.store.update_task(task)
        page = FakePage([])
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page = page
        controller._plans = controller._build_plans()
        controller._plan_region_quota()
        controller._navigate_plan(0)
        self.assertEqual(controller._region_allowance, {"上海": 40, "北京": 40, "广州": 40})
        for number in range(10):
            self.assertEqual(self.store.reserve_application_slot(
                f"https://www.zhipin.com/job_detail/a{number}.html", "上海",
                city_limit=controller._city_limit()), "reserved")
        self.assertTrue(controller._advance_plan())
        self.assertEqual(controller._search_city, "北京")
        self.assertEqual(controller._region_effective, 70)
        for number in range(50):
            self.store.reserve_application_slot(
                f"https://www.zhipin.com/job_detail/b{number}.html", "北京",
                city_limit=controller._city_limit())
        self.assertTrue(controller._advance_plan())
        self.assertEqual(controller._search_city, "广州")
        self.assertEqual(controller._region_effective, 60)
        controller.close()

    def test_full_daily_cap_prevents_browser_click(self):
        for number in range(120):
            self.store.reserve_application_slot(
                f"https://www.zhipin.com/job_detail/used{number}.html", "上海")
        task = self.store.get_task("BOSS直聘")
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/new.html")])
        calls = []
        page.apply_job = lambda link: calls.append(link) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        self.assertEqual(calls, [])
        self.assertEqual(self.store.daily_application_usage()["total"], 120)
        controller.close()

    def test_old_record_metadata_is_enriched_without_reapplying(self):
        task = self.store.get_task("BOSS直聘")
        card = FakeCard("Python 开发", "", "/job_detail/old.html")
        card.elements.update({
            ".boss-name": FakeElement("甲公司"),
            ".company-location": FakeElement("上海·浦东"),
            ".job-salary": FakeElement("20-30K"),
            ".tag-list li:first-child": FakeElement("3-5年"),
            ".tag-list li:nth-child(2)": FakeElement("本科"),
        })
        link = "https://www.zhipin.com/job_detail/old.html"
        self.store.add_apply_record({"source": "BOSS直聘", "task_id": task["id"],
                                     "title": "Python 开发", "link": link, "submit": "是",
                                     "submit_time": "2026-10-16 10:00:00", "remarks": "已沟通"})
        page = FakePage([card])
        calls = []
        page.apply_job = lambda link: calls.append(link) or {"state": "sent"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        controller._page, controller._task, controller.mode = page, task, "apply_mode"
        controller.scan_once()
        row = self.store.get_apply_record()[0]
        self.assertEqual([row[key] for key in ("company", "area", "salary", "experience", "education")],
                         ["甲公司", "上海·浦东", "20-30K", "3-5年", "本科"])
        self.assertEqual((row["submit"], row["remarks"]), ("是", "已沟通"))
        self.assertEqual(calls, [])
        controller.close()

    def test_explicit_backfill_reads_old_details_without_changing_submission(self):
        task = self.store.get_task("BOSS直聘")
        link = "https://www.zhipin.com/job_detail/archive.html"
        self.store.add_apply_record({"source": "BOSS直聘", "task_id": task["id"],
                                     "title": "Python 开发", "link": link, "submit": "是",
                                     "remarks": "已沟通"})
        page = FakePage([])
        page.login_state = lambda: "logged_in"
        page.detail_metadata[link] = {"company": "乙公司", "area": "北京·海淀",
                                      "salary": "25-35K", "experience": "5-10年",
                                      "education": "本科"}
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page)
        self.assertEqual(controller.backfill_record_metadata(), {"checked": 1, "updated": 1})
        row = self.store.get_apply_record()[0]
        self.assertEqual((row["company"], row["area"], row["salary"],
                          row["experience"], row["education"]),
                         ("乙公司", "北京·海淀", "25-35K", "5-10年", "本科"))
        self.assertEqual((row["submit"], row["remarks"]), ("是", "已沟通"))
        controller.close()

    def test_logged_out_page_waits_for_manual_login(self):
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/123.html")])
        state = ["logged_out"]
        page.login_state = lambda: state[0]
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page, poll_seconds=0.01)
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        time.sleep(0.08)
        self.assertEqual(self.store.get_apply_record(), [])
        self.assertIn("手动登录", controller.get_run_status()["message"])
        state[0] = "logged_in"
        deadline = time.monotonic() + 1
        while not self.store.get_apply_record() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.store.get_apply_record()), 1)
        controller.close()

    def test_same_job_is_not_contacted_twice_across_tasks(self):
        first = self.store.get_task("BOSS直聘")
        second_id = self.store.save_task({
            "keyword": "Python", "city": "上海", "search_prompt": "", "job_prompt": "",
            "search_re": "Python", "job_re": "", "resume": "", "match_degree": 0,
            "platform": "BOSS直聘",
        })
        page = FakePage([FakeCard("Python 开发", "甲公司", "/job_detail/123.html")])
        calls = []
        page.apply_job = lambda url: calls.append(url) or {"state": "sent"}
        self.store.set_apply_config("work_mode", "apply_mode")
        controller = AutomationController(self.store, config_dir=self.root / "config",
                                          page_factory=lambda: page, poll_seconds=0.01,
                                          dwell_seconds=0.03)
        self.assertEqual(controller.start("BOSS直聘"), "已运行")
        deadline = time.monotonic() + 1
        while len(self.store.get_apply_record()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = self.store.get_apply_record()
        self.assertEqual(len(calls), 1)
        self.assertEqual({row["task_id"] for row in rows}, {first["id"], second_id})
        self.assertEqual(sum(row["submit"] == "是" for row in rows), 1)
        self.assertTrue(any("跳过重复操作" in row["remarks"] for row in rows))
        controller.close()


if __name__ == "__main__":
    unittest.main()

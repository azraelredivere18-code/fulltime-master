import json
import shutil
import subprocess
import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import LocalStore
from site_adapters import (BROWSER_ONLY_SITES, EmbeddedSitePage, SITES,
                           SiteDetailTab, ZHAOPIN_CITY_PATHS, valid_site_url)
from site_automation import SiteAutomationController, parse_site_card


class SiteAdapterTests(unittest.TestCase):
    def test_zhaopin_card_without_stable_detail_link_reports_blocker(self):
        class Browser:
            def run_js(self, script):
                return [{"title": "数据分析师", "area": "北京", "link": ""}]

        manager = type("Manager", (), {"current_browser_window": lambda self, platform=None: Browser()})()
        site = SITES["智联招聘"]
        with self.assertRaisesRegex(RuntimeError, "未暴露可核验详情链接"):
            EmbeddedSitePage(manager, site).eles("css:" + site.cards)

    def test_zhaopin_redirect_to_current_jobs_page_requires_visible_city(self):
        class Browser:
            def __init__(self, selected):
                self.selected = selected
                self.events = type("Events", (), {"loaded": type("Loaded", (), {"wait": lambda self, timeout: True})()})()

            def get_current_url(self):
                return "https://www.zhaopin.com/jobs/"

            def load_url(self, url):
                pass

            def run_js(self, script):
                if "const candidates=Array.from(document.querySelectorAll('button,span,div'))" in script:
                    return self.selected
                if "search_requested" in script:
                    return "search_requested"
                return "city_input_missing"

        class Manager:
            def __init__(self, browser):
                self.browser = browser

            def open_browser_window(self, **kwargs):
                return self.browser

            def current_browser_window(self, platform):
                return self.browser

        self.assertTrue(EmbeddedSitePage(Manager(Browser(True)), SITES["智联招聘"])
                        .navigate_search("数据分析", "北京", "北京"))
        with self.assertRaisesRegex(RuntimeError, "城市选择控件未找到"):
            EmbeddedSitePage(Manager(Browser(False)), SITES["智联招聘"]).navigate_search(
                "数据分析", "上海", "上海")

    def test_zhaopin_task_cities_use_verified_search_routes_without_city_popover(self):
        class Browser:
            def __init__(self):
                self.url = ""
                self.scripts = []
                self.events = type("Events", (), {"loaded": type("Loaded", (), {"wait": lambda self, timeout: True})()})()

            def get_current_url(self):
                return self.url

            def run_js(self, script):
                self.scripts.append(script)
                if "const candidates=Array.from(document.querySelectorAll('button,span,div'))" in script:
                    return True
                if "search_requested" in script:
                    return "search_requested"
                raise AssertionError("The mapped city must not open the obsolete city popover")

        browser = Browser()

        class Manager:
            def open_browser_window(self, *, initial_url, platform):
                browser.url = initial_url
                return browser

            def current_browser_window(self, platform):
                return browser

        page = EmbeddedSitePage(Manager(), SITES["智联招聘"])
        for city, route in ZHAOPIN_CITY_PATHS.items():
            self.assertTrue(page.navigate_search("数据分析", city, city))
            self.assertEqual(browser.url, "https://www.zhaopin.com/sou/" + route)
        self.assertEqual(len(browser.scripts), 4 * len(ZHAOPIN_CITY_PATHS))

    @unittest.skipUnless(shutil.which("node"), "Node required for DOM regression")
    def test_niuke_search_finds_job_filter_placeholder_not_header_search(self):
        class Browser:
            def __init__(self):
                self.url = ""
                self.script = ""
                self.events = type("Events", (), {"loaded": type("Loaded", (), {"wait": lambda self, timeout: True})()})()

            def get_current_url(self):
                return self.url

            def run_js(self, script):
                self.script = script
                return True

        browser = Browser()

        class Manager:
            def open_browser_window(self, *, initial_url, platform):
                browser.url = initial_url
                return browser

            def current_browser_window(self, platform):
                return browser

        page = EmbeddedSitePage(Manager(), SITES["牛客网"])
        self.assertTrue(page.navigate_search("产品经理", "深圳", "深圳"))
        harness = """
          const fs=require('fs');const script=fs.readFileSync(0,'utf8');
          global.HTMLInputElement=function(){};
          Object.defineProperty(HTMLInputElement.prototype,'value',{set(v){this._value=v}});
          global.Event=function(type){this.type=type};
          global.KeyboardEvent=function(type){this.type=type};
          let clicked=0;const events=[];
          const button={getClientRects:()=>[1],innerText:'搜索',click(){clicked++}};
          const region={querySelectorAll:()=>[button]};
          const input=Object.create(HTMLInputElement.prototype);
          Object.assign(input,{disabled:false,getClientRects:()=>[1],focus(){},
            dispatchEvent(e){events.push(e.type)},closest:()=>region});
          global.document={querySelectorAll:()=>[input]};
          const ok=eval(script);
          process.stdout.write(JSON.stringify({ok,value:input._value,events,clicked}));
        """
        result = subprocess.run([shutil.which("node"), "-e", harness], input=browser.script,
                                text=True, encoding="utf-8", capture_output=True, check=True)
        observed = json.loads(result.stdout)
        self.assertEqual((observed["ok"], observed["value"], observed["clicked"]),
                         (True, "产品经理", 1))
        self.assertIn("input", observed["events"])

    def test_uncalibrated_sites_are_browser_only(self):
        self.assertEqual(BROWSER_ONLY_SITES["就业在线"], "https://www.jobonline.cn/")
        self.assertIn("国聘网", SITES)
        self.assertFalse(set(BROWSER_ONLY_SITES).intersection(SITES))

    @unittest.skipUnless(shutil.which("node"), "Node required for DOM regression")
    def test_guopin_public_job_row_yields_link_and_explicit_track(self):
        class Browser:
            script = ""

            def run_js(self, script):
                self.script = script
                return []

        browser = Browser()
        manager = type("Manager", (), {"current_browser_window": lambda self, platform=None: browser})()
        site = SITES["国聘网"]
        EmbeddedSitePage(manager, site).eles("css:" + site.cards)
        harness = """
          const fs=require('fs');const script=fs.readFileSync(0,'utf8');
          const company={innerText:'甲公司'};
          const row={innerText:'数据分析师\\n「北京-海淀区」\\n8~12K校招应届生本科\\n甲公司\\n申请职位',
            querySelector:s=>s.includes('company-name')?company:null};
          const a={href:'https://www.iguopin.com/job/detail?id=123',innerText:'数据分析师',
            getClientRects:()=>[1],
            closest:()=>row,parentElement:null};
          global.document={querySelectorAll:()=>[a]};
          process.stdout.write(JSON.stringify(eval(script)));
        """
        result = subprocess.run([shutil.which("node"), "-e", harness], input=browser.script,
                                text=True, encoding="utf-8", capture_output=True, check=True)
        row = json.loads(result.stdout)[0]
        self.assertEqual((row["title"], row["company"], row["area"], row["salary"]),
                         ("数据分析师", "甲公司", "北京-海淀区", "8~12K"))
        self.assertEqual((row["employment_type"], row["recruitment_track"]), ("全职", "校招"))
        self.assertTrue(valid_site_url(site, row["link"], detail=True))
        self.assertFalse(valid_site_url(site, "https://www.iguopin.com/job/detail", detail=True))

    def test_guopin_unknown_receipt_never_returns_sent(self):
        link = "https://www.iguopin.com/job/detail?id=123"

        class Browser:
            events = type("Events", (), {"loaded": type("Loaded", (), {"wait": lambda self, timeout: True})()})()
            url = "https://www.iguopin.com/job/list?keyword=data"

            def get_current_url(self):
                return self.url

            def run_js(self, script):
                return {"state": "clicked"}

        browser = Browser()

        class Manager:
            def current_browser_window(self, platform):
                return browser

            def open_browser_window(self, *, initial_url, platform):
                browser.url = initial_url
                return browser

        page = EmbeddedSitePage(Manager(), SITES["国聘网"])
        with patch.object(page, "login_state", return_value="logged_in"), \
             patch.object(page, "check_application_result", return_value="unknown"), \
             patch("site_adapters.time.sleep", return_value=None):
            result = page.apply_job(link)
        self.assertEqual(result["state"], "unknown")
        self.assertTrue(result["clicked"])
        self.assertEqual(browser.url, link)

    def test_guopin_controller_stops_after_unverified_submission(self):
        with tempfile.TemporaryDirectory() as temp:
            with LocalStore(Path(temp) / "guopin-pending.sqlite3") as store:
                store.save_task({"keyword": "数据分析", "city": "北京", "platform": "国聘网",
                                 "employment_type": "full_time", "match_degree": 0})
                task = store.get_task("国聘网")
                link = "https://www.iguopin.com/job/detail?id=123"
                card = {"title": "数据分析师", "company": "甲公司", "area": "北京-海淀",
                        "salary": "8~12K", "experience": "应届生", "education": "本科",
                        "employment_type": "全职", "recruitment_track": "校招", "link": link}
                calls = []

                class Page:
                    url = "https://www.iguopin.com/job/list?keyword=data"

                    def login_state(self):
                        return "logged_in"

                    def eles(self, locator, timeout=0):
                        return [card]

                    def apply_job(self, target):
                        calls.append(target)
                        return {"state": "unknown", "clicked": True, "reason": "无成功回执"}

                    def check_application_result(self, target):
                        return "unknown"

                page = Page()
                controller = SiteAutomationController(store, site=SITES["国聘网"],
                                                      page_factory=lambda: page)
                controller._page, controller._task = page, task
                controller._search_city, controller.mode = "北京", "apply_mode"
                controller.scan_once()
                controller.scan_once()
                self.assertEqual(calls, [link])
                row = store.get_apply_record()[0]
                self.assertEqual((row["submit"], row["attempt_state"]), ("否", "pending"))
                self.assertEqual(store.daily_application_usage(platform="国聘网")["total"], 1)
                controller.close()

    def test_guopin_filters_out_jobs_outside_current_city(self):
        with tempfile.TemporaryDirectory() as temp:
            with LocalStore(Path(temp) / "guopin.sqlite3") as store:
                controller = SiteAutomationController(store, site=SITES["国聘网"],
                                                      page_factory=lambda: None)
                controller._search_city = "北京"
                base = {"title": "数据分析师", "company": "甲公司",
                        "link": "https://www.iguopin.com/job/detail?id=123"}
                self.assertIsNone(controller._parse_site_card({**base, "area": "上海-浦东"}))
                self.assertEqual(controller._parse_site_card({**base, "area": "北京-海淀"})["area"],
                                 "北京-海淀")

    @unittest.skipUnless(shutil.which("node"), "Node required for DOM regression")
    def test_niuke_route_does_not_invent_full_time_and_detail_title_marks_track(self):
        class Browser:
            script = ""
            def run_js(self, script):
                self.script = script
                return []
        browser = Browser()
        manager = type("Manager", (), {"current_browser_window": lambda self, platform=None: browser})()
        site = SITES["牛客网"]
        EmbeddedSitePage(manager, site).eles("css:" + site.cards)
        harness = """
          const fs=require('fs');const script=fs.readFileSync(0,'utf8');
          global.location={pathname:'/jobs/fulltime/center'};
          const text=value=>({innerText:value});
          const card={getAttribute:()=>'',closest:()=>null,
            querySelector:s=>({'.job-name':text('运营专员'),
            '.company-name':text('甲公司'),'.job-city':text('上海')})[s]||null,
            querySelectorAll:s=>s==='a[href]'?[{href:'https://www.nowcoder.com/jobs/detail/123'}]:[]};
          global.document={querySelectorAll:s=>s==='.job-card-item'?[card]:[]};
          process.stdout.write(JSON.stringify(eval(script)));
        """
        result = subprocess.run([shutil.which("node"), "-e", harness], input=browser.script,
                                text=True, encoding="utf-8", capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)[0]["employment_type"], "")

        detail = SiteDetailTab(browser, site)
        detail.metadata()
        harness = """
          const fs=require('fs');const script=fs.readFileSync(0,'utf8');
          global.document={title:TITLE,querySelectorAll:()=>[]};
          process.stdout.write(JSON.stringify(eval(script)));
        """
        for title, expected in (("开发工程师_某公司社招_牛客网", "社招"),
                                ("校招社招混合招聘_牛客网", "")):
            result = subprocess.run([shutil.which("node"), "-e", harness.replace("TITLE", json.dumps(title))],
                                    input=browser.script, text=True, encoding="utf-8", capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["recruitment_track"], expected)

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

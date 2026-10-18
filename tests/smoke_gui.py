"""Interactive WebView smoke check; run separately from unit tests on Windows."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import WindowManager
from automation import parse_boss_card
from embedded_browser import (CARD_LOCATOR, DETAIL_LOCATOR, CHAT_RESULT_SCRIPT,
                              LOGIN_SCRIPT, START_CHAT_SCRIPT, build_resume_upload_script, EmbeddedBossPage,
                              EmbeddedDetailTab)
from site_adapters import EmbeddedSitePage, SiteDetailTab, SITES
from site_automation import parse_site_card


def main() -> None:
    class FixtureHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/detail":
                html = ('<div class="company-info"><a>甲公司</a></div>'
                        '<span class="job-salary">20-30K</span>'
                        '<span class="location-address">上海·浦东</span>'
                        '<ul class="tag-list"><li>3-5年</li><li>本科</li></ul>'
                        '<div class="job-detail-section"><div class="job-sec-text">支持远程工作</div></div>')
            elif self.path == "/loggedout":
                html = '<header><a class="header-login-btn">登录/注册</a></header>'
            elif self.path == "/nav_avatar":
                html = '<header><span class="nav-figure"><img src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" alt=""></span></header>'
            elif self.path == "/apply":
                html = ('<header><div class="user-nav">求职用户</div></header>'
                        '<button class="btn-startchat" onclick="'
                        'this.innerText=\'已沟通\';'
                        'document.querySelector(\'#receipt\').innerText=\'已向BOSS发送消息\'">'
                        '立即沟通</button><div id="receipt"></div>')
            elif self.path == "/resume":
                html = ('<header><div class="user-nav">求职用户</div></header>'
                        '<label>上传附件简历<input type="file" accept=".pdf,.docx"></label>'
                        '<div id="upload-status"></div><script>'
                        'document.querySelector("input").addEventListener("change", e => {'
                        'document.querySelector("#upload-status").innerText = '
                        'e.target.files[0]?.name === "smoke.pdf" ? "上传成功" : "错误";'
                        '});</script>')
            elif self.path == "/zhilian":
                html = ('<div class="job-card"><a class="job-card__job-name" '
                        'href="https://www.zhaopin.com/jobdetail/1">产品经理</a>'
                        '<span class="job-card__company-name">甲公司</span>'
                        '<span class="job-card__salary">15-20K</span>'
                        '<div class="job-card__location"><span>广州·黄埔</span></div></div>')
            elif self.path == "/zhilian_detail":
                html = ('<div class="companyinfo__name">甲公司</div>'
                        '<div class="jobinfo__salary">15-20K</div>'
                        '<section><div class="jobinfo__other-info-item"><span>广州</span></div>'
                        '<div class="jobinfo__other-info-item">3-5年</div>'
                        '<div class="jobinfo__other-info-item">本科</div></section>')
            elif self.path == "/qiancheng":
                html = ('<div class="joblist"><div class="joblist-item">'
                        '<div class="joblist-item-left"><a class="jname" '
                        'href="https://we.51job.com/pc/job/2">管理培训生</a>'
                        '<span class="sal">8-9千</span><span class="area">上海</span></div>'
                        '<div class="joblist-item-right"><span class="cname">乙公司</span></div>'
                        '</div></div>')
            elif self.path == "/qiancheng_detail":
                html = ('<div class="com-name">乙公司</div><div class="job_area">上海</div>'
                        '<div class="job-salary">8-9千</div>'
                        '<span data-field="jobYear">1-3年</span>'
                        '<span data-field="jobDegree">本科</span>')
            elif self.path == "/yjs_detail":
                html = ('<div class="left-detail-company">丙公司</div>'
                        '<div class="left-detail-area">北京</div>'
                        '<div class="right-salary">1-1.5万</div>'
                        '<div class="job-year">应届生</div><div class="job-degree">硕士</div>')
            elif self.path == "/zhilian_modal":
                html = ('<div class="a-modal"><h3>请选择要投递的简历</h3>'
                        '<input type="radio" checked><button onclick="'
                        'document.querySelector(\'.a-modal\').remove();'
                        'document.querySelector(\'.a-button\').innerText=\'已申请\'">'
                        '投递简历</button></div><button class="a-button a--bordered a--filled">立即投递</button>')
            elif self.path == "/qiancheng_success":
                html = ('<div class="el-dialog"><h3>投递成功</h3></div>'
                        '<button class="apply-btn-new">投递</button>')
            elif self.path == "/zhilian_loggedin":
                html = '<div class="home-header__right"><img alt="头像">求职用户</div>'
            elif self.path == "/qiancheng_loggedin":
                html = '<div class="right-menu"><img alt="头像">求职用户</div>'
            elif self.path == "/yjs_login":
                html = ('<div class="head-nav-right"><span class="login-text">登录/注册</span></div>'
                        '<div>应届生求职登录</div>')
            else:
                html = ('<div class="card-area"><div class="job-card-wrap">'
                        '<a class="job-name" href="https://www.zhipin.com/job_detail/1.html">Python 开发</a>'
                        '<div class="boss-name">甲公司</div><span class="job-salary">20-30K</span>'
                        '<span class="company-location">上海·浦东</span>'
                        '<ul class="tag-list"><li>3-5年</li><li>本科</li></ul>'
                        '<span class="boss-info-attr">HR</span></div></div>')
            body = ("<html><body>" + html + "</body></html>").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    fixture_url = f"http://127.0.0.1:{server.server_port}"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        manager = WindowManager(Path(tmp))
        window = manager.open_window("index")
        saved_ids = []
        for keyword in ("Python", "Java"):
            saved_ids.append(manager._windows["index"].save_task({
                "keyword": keyword, "city": "上海", "search_prompt": "", "job_prompt": "",
                "search_re": "", "job_re": "", "resume": "", "match_degree": 0,
                "platform": "BOSS直聘",
            }))
        errors = []

        def check() -> None:
            setting = None
            record = None
            official_window = None
            detail = None
            try:
                window.events.loaded.wait(15)
                time.sleep(2)
                main_result = window.evaluate_js("""({
                    title: document.title,
                    options: document.querySelectorAll('.selected-platform option').length,
                    bridge: typeof window.pywebview.api.get_tasks,
                    modeOptions: document.querySelectorAll('input[name="run-mode"]').length,
                    notice: document.body.innerText.includes('自动投递')
                })""")
                setting = manager.open_window("setting")
                setting.events.loaded.wait(15)
                time.sleep(2)
                setting_result = setting.evaluate_js("""({
                    tabs: document.querySelectorAll('.nav-link').length,
                    bridge: typeof window.pywebview.api.get_platform_setting,
                    employmentType: document.querySelector('#employment-type').value,
                    noFilterMode: !document.querySelector('#work-mode option[value="filter_mode"]')
                })""")
                print(json.dumps({"main": main_result, "setting": setting_result}, ensure_ascii=False), flush=True)
                if (main_result["options"] != 7 or main_result["modeOptions"] != 0
                        or not main_result["notice"] or not setting_result["noFilterMode"]
                        or setting_result["employmentType"] != "full_time"
                        or setting.evaluate_js("document.querySelector('#recruitment-track').value") != "all"):
                    raise AssertionError("GUI failed to load expected options")
                official_window = manager.open_window("official")
                official_window.events.loaded.wait(15)
                time.sleep(1)
                official_result = official_window.evaluate_js("""({
                    fields: document.querySelectorAll('#profile-fields [data-key]').length,
                    bridge: typeof window.pywebview.api.save_official_profile,
                    importBridge: typeof window.pywebview.api.preview_official_resume_import,
                    importButtons: document.querySelectorAll('#import-selected-resume,#import-file-resume').length,
                    url: !!document.querySelector('#official-url')
                })""")
                if official_result != {"fields": 20, "bridge": "function", "importBridge": "function",
                                       "importButtons": 2, "url": True}:
                    raise AssertionError(f"Official application window failed: {official_result}")
                mode_ui = window.evaluate_js("document.querySelector('#start-apply').innerText")
                if not mode_ui.startswith("开始自动投递"):
                    raise AssertionError(f"Auto mode control did not update: {mode_ui}")
                setting.evaluate_js("$('.table-tasks tbody tr:eq(1) .icon-up').trigger('click')")
                time.sleep(0.5)
                row_ids = setting.evaluate_js("""Array.from(document.querySelectorAll(
                    '.table-tasks tbody tr .row-id')).map(el => Number(el.textContent))""")
                stored_ids = [task["id"] for task in manager._windows["index"].get_tasks()]
                if row_ids != saved_ids[::-1] or stored_ids != saved_ids[::-1]:
                    raise AssertionError(f"Task row IDs changed during reorder: {row_ids}, {stored_ids}")
                record = manager.open_window("record")
                record.events.loaded.wait(15)
                record_ui = record.evaluate_js("""({
                    button: !!document.querySelector('#backfill-records'),
                    bridge: typeof window.pywebview.api.start_record_backfill,
                    metrics: typeof window.RecordMetrics,
                    confirmed: window.RecordMetrics.platformCounts([
                        {submit:'是',source:'BOSS直聘',submit_time:'2026-10-17T10:00:00'},
                        {submit:'否',source:'BOSS直聘',create_time:'2026-10-17 11:00:00'}
                    ],'2026-10-17')['BOSS直聘']
                })""")
                if (not record_ui["button"] or record_ui["bridge"] != "function"
                        or record_ui["metrics"] != "object" or record_ui["confirmed"] != 1):
                    raise AssertionError(f"Record backfill control unavailable: {record_ui}")
                browser = manager.open_browser_window(initial_url=fixture_url + "/cards")
                if browser.gui.renderer != "edgechromium" or browser._js_api is not None:
                    raise AssertionError("Browser is not an isolated WebView2 window")
                page = EmbeddedBossPage(manager)
                cards = page.eles(CARD_LOCATOR)
                card = parse_boss_card(cards[0]) if cards else None
                if not card or [card[key] for key in
                                ("title", "company", "area", "salary", "experience", "education")] != [
                                    "Python 开发", "甲公司", "上海·浦东", "20-30K", "3-5年", "本科"]:
                    raise AssertionError(f"Embedded job list was not read: {cards}")
                browser.evaluate_js("document.cookie = 'smoke_session=shared; path=/'")
                detail = EmbeddedDetailTab(manager.open_detail_window(fixture_url + "/detail"))
                shared = detail.window.evaluate_js("document.cookie.includes('smoke_session=shared')")
                description = detail.ele(DETAIL_LOCATOR)
                metadata = detail.metadata()
                if (not shared or description is None or description.text != "支持远程工作"
                        or [metadata[key] for key in ("company", "area", "salary", "experience", "education")]
                        != ["甲公司", "上海·浦东", "20-30K", "3-5年", "本科"]):
                    raise AssertionError(f"Browser session/detail did not work: {shared}, {description}")
                detail.close()
                detail = None
                manager.close_browser_window()
                reopened = manager.open_browser_window(initial_url=fixture_url + "/cards")
                persisted = reopened.evaluate_js("document.cookie.includes('smoke_session=shared')")
                if not persisted or len(page.eles(CARD_LOCATOR)) != 1:
                    raise AssertionError("Embedded browser did not recover after closing its window")
                reopened.load_url(fixture_url + "/zhilian")
                time.sleep(0.7)
                z_page = EmbeddedSitePage(manager, SITES["智联招聘"])
                z_cards = z_page.eles("css:" + SITES["智联招聘"].cards)
                z_card = parse_site_card(z_cards[0], SITES["智联招聘"]) if z_cards else None
                if not z_card or (z_card["title"], z_card["company"], z_card["area"]) != (
                        "产品经理", "甲公司", "广州·黄埔"):
                    raise AssertionError(f"智联职位卡片读取失败：{z_cards}")
                z_diag = z_page.diagnostics()
                if z_diag["cardCount"] != 1 or ".job-card__job-name" not in z_diag["fields"]["title"]:
                    raise AssertionError(f"智联页面诊断失真：{z_diag}")
                reopened.load_url(fixture_url + "/qiancheng")
                time.sleep(0.7)
                q_page = EmbeddedSitePage(manager, SITES["前程无忧"])
                q_cards = q_page.eles("css:" + SITES["前程无忧"].cards)
                q_card = parse_site_card(q_cards[0], SITES["前程无忧"]) if q_cards else None
                if not q_card or (q_card["title"], q_card["company"], q_card["salary"]) != (
                        "管理培训生", "乙公司", "8-9千"):
                    raise AssertionError(f"前程职位卡片读取失败：{q_cards}")
                for route, site_name, expected in (
                    ("zhilian_detail", "智联招聘", ["甲公司", "广州", "15-20K", "3-5年", "本科"]),
                    ("qiancheng_detail", "前程无忧", ["乙公司", "上海", "8-9千", "1-3年", "本科"]),
                    ("yjs_detail", "应届生", ["丙公司", "北京", "1-1.5万", "应届生", "硕士"]),
                ):
                    reopened.load_url(fixture_url + "/" + route)
                    time.sleep(0.5)
                    metadata = SiteDetailTab(reopened, SITES[site_name]).metadata()
                    actual = [metadata[key] for key in ("company", "area", "salary", "experience", "education")]
                    if actual != expected:
                        raise AssertionError(f"{site_name} 详情字段未读取：{actual}")
                class SiteWindow:
                    def __init__(self, browser_window, official_url):
                        self.browser_window, self.official_url = browser_window, official_url
                    def get_current_url(self):
                        return self.official_url
                    def run_js(self, script):
                        return self.browser_window.run_js(script)
                class SiteManager:
                    def __init__(self, browser_window):
                        self.browser_window = browser_window
                    def current_browser_window(self):
                        return self.browser_window
                reopened.load_url(fixture_url + "/zhilian_modal")
                time.sleep(0.7)
                z_modal = EmbeddedSitePage(SiteManager(SiteWindow(reopened,
                    "https://www.zhaopin.com/jobdetail/1")), SITES["智联招聘"])
                if z_modal.check_application_result("https://www.zhaopin.com/jobdetail/1") != "needs_confirmation":
                    raise AssertionError("智联简历弹窗未识别")
                if not z_modal._confirm_selected_resume() or z_modal.check_application_result(
                        "https://www.zhaopin.com/jobdetail/1") != "sent":
                    raise AssertionError("智联已选简历确认或回执未识别")
                reopened.load_url(fixture_url + "/qiancheng_success")
                time.sleep(0.7)
                q_success = EmbeddedSitePage(SiteManager(SiteWindow(reopened,
                    "https://we.51job.com/pc/job/2")), SITES["前程无忧"])
                if q_success.check_application_result("https://we.51job.com/pc/job/2") != "sent":
                    raise AssertionError("前程投递成功弹窗未识别")
                for route, site_name, official, expected in (
                    ("zhilian_loggedin", "智联招聘", "https://www.zhaopin.com/sou/jl530", "logged_in"),
                    ("qiancheng_loggedin", "前程无忧", "https://we.51job.com/pc/search", "logged_in"),
                    ("yjs_login", "应届生", "https://q.yingjiesheng.com/jobs/search/", "logged_out"),
                ):
                    reopened.load_url(fixture_url + "/" + route)
                    time.sleep(0.5)
                    state = EmbeddedSitePage(SiteManager(SiteWindow(reopened, official)),
                                             SITES[site_name]).login_state()
                    if state != expected:
                        raise AssertionError(f"{site_name} 登录状态未识别：{state}")
                reopened.load_url(fixture_url + "/loggedout")
                time.sleep(0.7)
                logged_out = reopened.run_js(LOGIN_SCRIPT)
                reopened.load_url(fixture_url + "/nav_avatar")
                time.sleep(0.4)
                avatar_login = reopened.run_js(LOGIN_SCRIPT)
                reopened.load_url(fixture_url + "/apply")
                time.sleep(0.7)
                logged_in = reopened.run_js(LOGIN_SCRIPT)
                click = reopened.run_js(START_CHAT_SCRIPT)
                receipt = reopened.run_js(CHAT_RESULT_SCRIPT)
                if (logged_out, avatar_login, logged_in, click.get("state"), receipt) != (
                        "logged_out", "logged_in", "logged_in", "clicked", "sent"):
                    raise AssertionError(f"Browser scripts failed: {logged_out}, {avatar_login}, {logged_in}, {click}, {receipt}")
                file = Path(tmp) / "smoke.pdf"
                file.write_bytes(b"%PDF-1.4\n%%EOF")
                reopened.load_url(fixture_url + "/resume")
                time.sleep(0.7)
                upload = reopened.run_js(build_resume_upload_script(file))
                upload_text = reopened.run_js("document.querySelector('#upload-status').innerText")
                if upload.get("state") != "submitted_to_form" or upload_text != "上传成功":
                    raise AssertionError(f"Browser file upload failed: {upload}, {upload_text}")
                print(json.dumps({"browser": "edgechromium", "shared_session": shared,
                                  "reopened_session": persisted, "cards": len(cards),
                                  "detail": description.text, "login": logged_in,
                                  "apply_fixture": receipt, "upload_fixture": upload_text,
                                  "zhilian_cards": len(z_cards), "qiancheng_cards": len(q_cards),
                                  "zhilian_resume_modal": "sent", "qiancheng_receipt": "sent",
                                  "site_login_states": "passed"},
                                 ensure_ascii=False), flush=True)
            except Exception as exc:
                errors.append(exc)
            finally:
                if detail is not None:
                    detail.close()
                manager.close_browser_window()
                if setting is not None:
                    setting.destroy()
                if record is not None:
                    record.destroy()
                if official_window is not None:
                    official_window.destroy()
                window.destroy()

        webview.start(check, gui="edgechromium", private_mode=False,
                      storage_path=str(Path(tmp) / "webview"))
        if errors:
            raise errors[0]
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()

"""Desktop shell for the independent 全职高手 job application client.

Run with ``python app.py`` from the source tree. The original executable is
never loaded. Every UI window receives a local API backed by the same SQLite
file; there is no activation or remote licensing endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit

from backend import LocalStore, china_day


VERSION = "0.13.0"
WINDOWS = {
    "index": ("全职高手", "index.html", 660, 760),
    "setting": ("设置", "setting.html", 1120, 760),
    "record": ("记录", "record.html", 1280, 780),
    "official": ("企业官网投递助手", "official.html", 820, 840),
}


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def default_data_dir() -> Path:
    root = os.getenv("LOCALAPPDATA")
    return Path(root) / "OneClickJobRebuild" if root else Path.home() / ".oneclickjob_rebuild"


class WindowAPI(LocalStore):
    """Methods called by recovered GUI JavaScript through pywebview."""

    def __init__(self, db_path: Path, manager: "WindowManager", kind: str) -> None:
        super().__init__(db_path, config_dir=bundle_dir() / "config")
        self._manager = manager
        self._kind = kind
        self._window = None

    def get_config(self, key: str | None = None):
        values = {"appname": "全职高手", "version": VERSION}
        return values.get(key) if key else values

    def get_version(self) -> str:
        return VERSION

    def get_biz_config(self):
        return None

    def start(self, platform: str, mode: str | None = None) -> str:
        return self._manager.start_automation(platform, mode)

    def stop(self, platform: str | None = None) -> str:
        return self._manager.stop_automation(platform)

    def get_run_status(self, platform: str | None = None) -> dict:
        statuses = self._manager.controller_statuses()
        if platform:
            status = statuses.get(platform, {
                "running": False, "message": "未运行", "current": 0,
                "total": 0, "saved": 0, "platform": platform,
            })
        else:
            running = [value for value in statuses.values() if value.get("running")]
            status = {
                "running": bool(running), "message": "；".join(
                    f"{value.get('platform')}: {value.get('message')}" for value in running) or "未运行",
                "current": sum(int(value.get("current") or 0) for value in running),
                "total": sum(int(value.get("total") or 0) for value in running),
                "saved": sum(int(value.get("saved") or 0) for value in running),
                "applied": sum(int(value.get("applied") or 0) for value in running),
                "platforms": statuses,
            }
        scheduler = self._manager.scheduler
        if not status["running"] and scheduler and not platform:
            status["message"] = scheduler.current_message() or status["message"]
        return status

    def open_browser(self, platform: str = "BOSS直聘") -> bool | str:
        try:
            from automation import BOSS_HOME
            from site_adapters import SITES
            home = BOSS_HOME if platform == "BOSS直聘" else SITES[platform].home
            self._manager.open_browser_window(initial_url=home, platform=platform)
            return True
        except KeyError:
            return f"{platform} 的内置浏览器适配器尚未完成"
        except Exception as exc:
            return f"内置浏览器打开失败：{exc}"

    def get_login_status(self, platform: str = "BOSS直聘") -> str:
        if self._manager.current_browser_window(platform) is None:
            return "browser_closed"
        from embedded_browser import EmbeddedBossPage
        try:
            if platform == "BOSS直聘":
                return EmbeddedBossPage(self._manager).login_state()
            from site_adapters import EmbeddedSitePage, SITES
            return EmbeddedSitePage(self._manager, SITES[platform]).login_state()
        except Exception:
            return "unknown"

    def export_page_diagnostics(self, platform: str) -> dict[str, str]:
        from site_adapters import EmbeddedSitePage, SITES
        site = SITES.get(platform)
        if platform != "BOSS直聘" and site is None:
            return {"state": "unsupported", "reason": "当前网站没有页面诊断适配器"}
        if self._manager.current_browser_window(platform) is None:
            return {"state": "browser_closed", "reason": "请先打开内置浏览器"}
        if platform == "BOSS直聘":
            from embedded_browser import EmbeddedBossPage
            page = EmbeddedBossPage(self._manager)
            hosts = {"zhipin.com", "www.zhipin.com"}
        else:
            page = EmbeddedSitePage(self._manager, site)
            hosts = site.hosts
        if urlsplit(page.url).hostname not in hosts:
            return {"state": "wrong_site", "reason": f"请先在内置浏览器打开{platform}页面"}
        try:
            report = page.diagnostics()
            report["capturedAt"] = datetime.now().isoformat(timespec="seconds")
            folder = self._manager.data_dir / "diagnostics"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"state": "saved", "path": str(path),
                    "reason": "已保存页面控件诊断；文件不包含账号密码或简历正文，发送前仍可自行查看"}
        except Exception as exc:
            return {"state": "error", "reason": f"页面诊断失败：{exc}"}

    def choose_platform_resume(self) -> str:
        path = self.get_file_path(["简历 (*.pdf;*.docx)"])
        if not path:
            return ""
        file = Path(path)
        if file.suffix.lower() not in {".pdf", ".docx"} or not file.is_file():
            raise ValueError("请选择 PDF 或 DOCX 简历")
        self.set_apply_config("resume_file", str(file))
        return str(file)

    def upload_selected_resume(self, platform: str = "BOSS直聘") -> dict[str, str]:
        path = self.get_apply_config("resume_file")
        if not path:
            return {"state": "invalid_file", "reason": "请先选择本地简历文件"}
        if self._manager.current_browser_window(platform) is None:
            return {"state": "browser_closed", "reason": "请先打开内置浏览器并手动登录"}
        try:
            if platform == "BOSS直聘":
                from embedded_browser import EmbeddedBossPage
                page = EmbeddedBossPage(self._manager)
            else:
                from site_adapters import EmbeddedSitePage, SITES
                page = EmbeddedSitePage(self._manager, SITES[platform])
            return page.upload_resume_file(str(path))
        except Exception as exc:
            return {"state": "error", "reason": f"简历上传未完成：{exc}"}

    def open_setting_window(self) -> bool:
        self._manager.open_window("setting")
        return True

    def open_record_window(self) -> bool:
        self._manager.open_window("record")
        return True

    def open_official_window(self) -> bool:
        self._manager.open_window("official")
        return True

    def get_official_profile(self) -> dict[str, str]:
        from official_apply import OfficialProfileStore
        return OfficialProfileStore(self._manager.data_dir / "official_profile.dpapi").load()

    def preview_official_resume_import(self, source: str = "selected") -> dict:
        import zipfile
        from resume_import import extract_resume_candidates
        if source == "selected":
            selected = self.get_apply_config("resume_file")
        elif source == "browse":
            selected = self.get_file_path(["简历 (*.pdf;*.docx)"])
        else:
            return {"state": "invalid", "reason": "简历来源无效"}
        if not selected:
            return {"state": "cancelled", "reason": "尚未选择简历文件"}
        file = Path(str(selected))
        if file.suffix.lower() not in {".pdf", ".docx"} or not file.is_file():
            return {"state": "invalid", "reason": "请选择可读取的 PDF 或 DOCX 简历"}
        if file.stat().st_size > 20 * 1024 * 1024:
            return {"state": "invalid", "reason": "简历文件超过 20 MB，请选较小的 PDF 或 DOCX"}
        try:
            if file.suffix.lower() == ".docx":
                with zipfile.ZipFile(file) as archive:
                    if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                        return {"state": "invalid", "reason": "简历解压内容过大"}
            else:
                from pypdf import PdfReader
                if len(PdfReader(str(file)).pages) > 30:
                    return {"state": "invalid", "reason": "简历超过 30 页，请选择较短版本"}
            result = extract_resume_candidates(self.extract_resume_text(file))
        except Exception:
            return {"state": "error", "reason": "简历读取失败：请检查文件是否损坏或是否为扫描图片"}
        return {"state": "preview", "filename": file.name, **result}

    def save_official_profile(self, profile: dict[str, str]) -> bool:
        from official_apply import OfficialProfileStore
        OfficialProfileStore(self._manager.data_dir / "official_profile.dpapi").save(profile)
        self._manager.invalidate_official_preview()
        return True

    def clear_official_profile(self) -> bool:
        from official_apply import OfficialProfileStore
        OfficialProfileStore(self._manager.data_dir / "official_profile.dpapi").clear()
        self._manager.invalidate_official_preview()
        return True

    def open_official_site(self, url: str) -> dict[str, str]:
        try:
            return self._manager.open_official_browser_window(url)
        except Exception as exc:
            return {"state": "error", "reason": str(exc)}

    def official_page_status(self) -> dict[str, str]:
        return self._manager.official_page_status()

    def trust_current_official_site(self) -> dict[str, str]:
        try:
            return self._manager.trust_current_official_site()
        except Exception as exc:
            return {"state": "error", "reason": str(exc)}

    def inspect_official_form(self) -> dict:
        return self._official_form_action(fill=False)

    def fill_official_form(self, include_id_number: bool = False) -> dict:
        return self._official_form_action(fill=True, include_id_number=include_id_number)

    def _official_form_action(self, *, fill: bool, include_id_number: bool = False) -> dict:
        try:
            profile = self.get_official_profile()
            if not any(profile.values()):
                return {"state": "empty_profile", "reason": "请先填写并加密保存个人资料"}
            return self._manager.official_form_action(
                profile, fill=fill, include_id_number=include_id_number)
        except Exception as exc:
            return {"state": "error", "reason": str(exc)}

    def record_official_application(self, item: dict[str, str]) -> dict[str, str]:
        if not isinstance(item, dict):
            return {"state": "invalid", "reason": "请填写投递记录"}
        title = str(item.get("title") or "").strip()[:200]
        company = str(item.get("company") or "").strip()[:200]
        area = str(item.get("area") or "").strip()[:100]
        if not title or not company:
            return {"state": "invalid", "reason": "请填写岗位和公司名称"}
        status = self._manager.official_page_status()
        if status["state"] != "ready":
            return {"state": "wrong_site", "reason": "请先在已确认的官网页面核对投递结果"}
        from official_apply import safe_record_url
        link = safe_record_url(status["url"])
        if any(row.get("source") == "企业官网" and row.get("link") == link and
               row.get("title") == title and row.get("company") == company and row.get("submit") == "是"
               for row in self.get_apply_record()):
            return {"state": "duplicate", "reason": "此岗位已有官网手动投递记录"}
        record_id = self.add_apply_record({
            "source": "企业官网", "title": title, "company": company, "area": area,
            "link": link, "submit": "是", "submit_time": datetime.now().isoformat(timespec="seconds"),
            "application_day": china_day(), "attempt_state": "manual_confirmed",
            "remarks": "用户手动确认官网投递；未由程序核验平台回执",
        })
        return {"state": "saved", "reason": "已记录为用户手动确认投递", "id": str(record_id)}

    def start_record_backfill(self) -> dict:
        return self._manager.start_record_backfill()

    def get_record_backfill_status(self) -> dict:
        return self._manager.get_record_backfill_status()

    def reconcile_apply_record(self, record_id: int) -> dict:
        rows = [row for row in self.get_apply_record() if row["id"] == int(record_id)]
        if not rows:
            return {"state": "invalid", "reason": "未找到投递记录"}
        try:
            controller = self._manager.ensure_controller(rows[0].get("source") or "BOSS直聘")
        except (KeyError, RuntimeError) as exc:
            return {"state": "error", "reason": str(exc)}
        if controller.get_run_status()["running"]:
            return {"state": "busy", "reason": "请先停止当前任务，再核实投递记录"}
        try:
            return controller.reconcile_saved_record(int(record_id))
        except Exception as exc:
            return {"state": "error", "reason": f"核实失败：{exc}"}

    def close_current_window(self) -> bool:
        if self._window is not None:
            self._window.destroy()
            return True
        return False

    def get_file_path(self, file_types: list[str] | None = None) -> str:
        if self._window is None:
            return ""
        import webview

        selected = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=tuple(file_types or ["所有文件 (*.*)"]),
        )
        return str(selected[0]) if selected else ""

    def get_file_content(self, file_types: list[str] | None = None) -> str:
        path = self.get_file_path(file_types)
        return self.extract_resume_text(path) if path else ""

    def open_url(self, url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return webbrowser.open(url)

    def signout(self, platform: str) -> bool:
        controller = self._manager.controllers.get(platform)
        return bool(controller and hasattr(controller, "signout") and controller.signout(platform))

    def update_timing(self) -> bool:
        return self._manager.update_timing()

    def send_notification_miao(self, message: str) -> bool:
        return False

    def is_mcp_running(self):
        return False

    def start_mcp(self):
        return False

    def stop_mcp(self):
        return False

    def get_tabs(self):
        return []

    def switch_tab(self, tab_id: str):
        return False

    def close_tab(self, tab_id: str):
        return False

    def get_frame(self):
        return ""

    def dispatch_mouse_event(self, *_):
        return False

    def handle_mouse_wheel(self, *_):
        return False

    def handle_keyboard_event(self, *_):
        return False


class WindowManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "app.sqlite3"
        self._lock = threading.RLock()
        self._launch_lock = threading.RLock()
        self._windows: dict[str, WindowAPI] = {}
        self._browser_window = None
        self._browser_windows: dict[str, object] = {}
        self._official_browser_window = None
        self._official_trusted_host = ""
        self._official_pending_url = ""
        self._official_preview: dict | None = None
        self._detail_windows: set = set()
        self.controller = None
        self.controllers: dict[str, object] = {}
        self.scheduler = None
        self._backfill_thread: threading.Thread | None = None
        self._backfill_status = {"running": False, "checked": 0, "total": 0,
                                 "updated": 0, "message": "未开始"}

    def controller_statuses(self) -> dict[str, dict]:
        with self._lock:
            controllers = dict(self.controllers)
            if self.controller is not None:
                controllers.setdefault(self.controller.platform_name, self.controller)
        return {platform: controller.get_run_status()
                for platform, controller in controllers.items()}

    def active_platforms(self) -> set[str]:
        return {platform for platform, status in self.controller_statuses().items()
                if status.get("running")}

    def get_record_backfill_status(self) -> dict:
        with self._lock:
            return dict(self._backfill_status)

    def start_record_backfill(self) -> dict:
        from embedded_browser import EmbeddedBossPage
        from site_adapters import EmbeddedSitePage, SITES
        if self.active_platforms():
            return {"running": False, "message": "请先停止自动投递任务"}
        with self._lock:
            if self._backfill_thread and self._backfill_thread.is_alive():
                return dict(self._backfill_status)
            if self.current_browser_window() is None:
                return {"running": False, "message": "请先打开内置浏览器并手动登录相应招聘网站"}
            try:
                current = str(self.current_browser_window().get_current_url() or "")
                host = urlsplit(current).hostname
                if host in {"zhipin.com", "www.zhipin.com"}:
                    platform = "BOSS直聘"
                    page = EmbeddedBossPage(self)
                else:
                    platform = next((name for name, site in SITES.items()
                                     if host in site.hosts), "")
                    if not platform:
                        return {"running": False, "message": "请打开 BOSS直聘、智联招聘、前程无忧或应届生的页面"}
                    page = EmbeddedSitePage(self, SITES[platform])
                if page.login_state() != "logged_in":
                    return {"running": False, "message": f"请先在内置浏览器手动登录{platform}"}
            except Exception as exc:
                return {"running": False, "message": f"浏览器状态读取失败：{exc}"}
            self._backfill_status = {"running": True, "checked": 0, "total": 0,
                                     "updated": 0, "message": f"正在补全{platform}记录"}
            self._backfill_thread = threading.Thread(
                target=self._run_record_backfill, args=(platform,),
                name="record-metadata-backfill", daemon=True)
            self._backfill_thread.start()
            return dict(self._backfill_status)

    def _run_record_backfill(self, platform: str) -> None:
        from automation import AutomationController
        from embedded_browser import EmbeddedBossPage
        from site_adapters import EmbeddedSitePage, SITES
        from site_automation import SiteAutomationController
        store = LocalStore(self.db_path)
        try:
            if platform == "BOSS直聘":
                controller = AutomationController(store, page_factory=lambda: EmbeddedBossPage(self))
            else:
                site = SITES[platform]
                controller = SiteAutomationController(
                    store, site=site, page_factory=lambda: EmbeddedSitePage(self, site))
            def progress(checked: int, total: int, updated: int) -> None:
                with self._lock:
                    self._backfill_status.update(checked=checked, total=total, updated=updated,
                                                 message=f"已检查 {checked}/{total} 条，补全 {updated} 条")
            result = controller.backfill_record_metadata(progress)
            with self._lock:
                self._backfill_status.update(running=False,
                                             message=f"补全完成：检查 {result['checked']} 条，补全 {result['updated']} 条")
        except Exception as exc:
            with self._lock:
                self._backfill_status.update(running=False, message=f"补全中断：{exc}")
        finally:
            store.close()

    def open_window(self, kind: str):
        import webview

        if kind not in WINDOWS:
            raise ValueError(f"Unknown window: {kind}")
        with self._lock:
            existing = self._windows.get(kind)
            if existing is not None and existing._window is not None:
                existing._window.show()
                return existing._window
            title, html_file, width, height = WINDOWS[kind]
            api = WindowAPI(self.db_path, self, kind)
            html_path = bundle_dir() / "gui" / "templates" / html_file
            if not html_path.is_file():
                api.close()
                raise FileNotFoundError(html_path)
            window = webview.create_window(
                title, url=html_path.as_uri(), js_api=api,
                width=width, height=height, min_size=(380, 400),
            )
            api._window = window
            self._windows[kind] = api
            window.events.closed += lambda: self._on_closed(kind)
            return window

    def _on_closed(self, kind: str) -> None:
        if kind == "index" and self.scheduler:
            self.scheduler.close()
        if kind == "index":
            with self._lock:
                controllers = list(dict.fromkeys([*self.controllers.values(), self.controller]))
            for controller in controllers:
                if controller is not None:
                    controller.close()
            self.close_browser_window()
            self.close_official_browser_window()
        with self._lock:
            api = self._windows.pop(kind, None)
            if api:
                api.close()

    def current_browser_window(self, platform: str | None = None):
        with self._lock:
            window = self._browser_windows.get(platform) if platform else self._browser_window
            if platform == "BOSS直聘" and window is None and not self._browser_windows:
                window = self._browser_window
            return window if window is not None and not window.events.closed.is_set() else None

    def _on_browser_closed(self, window) -> None:
        with self._lock:
            for platform, candidate in list(self._browser_windows.items()):
                if candidate is window:
                    self._browser_windows.pop(platform, None)
            if self._browser_window is window:
                self._browser_window = next(iter(self._browser_windows.values()), None)

    def open_browser_window(self, initial_url: str | None = None,
                            platform: str | None = None):
        import webview
        from automation import BOSS_HOME
        from site_adapters import SITES

        if platform is None:
            host = urlsplit(initial_url or "").hostname
            platform = next((name for name, site in SITES.items() if host in site.hosts),
                            "BOSS直聘")
        if platform != "BOSS直聘" and platform not in SITES:
            raise ValueError("招聘平台不受支持")

        running_here = platform in self.active_platforms()
        with self._lock:
            window = self.current_browser_window(platform)
            if window is not None:
                if initial_url:
                    from urllib.parse import urlparse
                    current_host = urlparse(str(window.get_current_url() or "")).hostname
                    requested_host = urlparse(initial_url).hostname
                    if current_host != requested_host and not running_here:
                        window.load_url(initial_url)
                window.show()
                self._browser_window = window
                return window
            window = webview.create_window(
                "全职高手 · " + platform, url=initial_url or BOSS_HOME,
                width=1180, height=820,
                min_size=(680, 480), js_api=None,
            )
            window.events.closed += lambda: self._on_browser_closed(window)
            self._browser_windows[platform] = window
            self._browser_window = window
        if not window.events.loaded.wait(30):
            self.close_browser_window(platform)
            raise RuntimeError("内置浏览器未能加载")
        return window

    def _on_official_browser_closed(self, window) -> None:
        with self._lock:
            if self._official_browser_window is window:
                self._official_browser_window = None
                self._official_trusted_host = ""
                self._official_pending_url = ""
                self._official_preview = None

    def invalidate_official_preview(self) -> None:
        with self._lock:
            self._official_preview = None

    def current_official_browser_window(self):
        with self._lock:
            window = self._official_browser_window
            return window if window is not None and not window.events.closed.is_set() else None

    def open_official_browser_window(self, value: str) -> dict[str, str]:
        import webview
        from official_apply import normalize_official_url

        url = normalize_official_url(value)
        if self.active_platforms():
            raise RuntimeError("请先停止自动投递任务，再打开企业官网")
        host = urlsplit(url).hostname or ""
        with self._lock:
            self._official_preview = None
            window = self.current_official_browser_window()
            if window is None:
                window = webview.create_window(
                    "全职高手 · 企业官网", url=url, width=1200, height=850,
                    min_size=(680, 480), js_api=None,
                )
                window.events.closed += lambda: self._on_official_browser_closed(window)
                self._official_browser_window = window
            else:
                self._official_pending_url = url
                window.load_url(url)
                window.show()
            self._official_trusted_host = host
        if not window.events.loaded.wait(30):
            raise RuntimeError("企业官网未能加载，请检查网址")
        return self.official_page_status()

    def official_page_status(self) -> dict[str, str]:
        window = self.current_official_browser_window()
        if window is None:
            return {"state": "browser_closed", "url": "", "trusted_host": ""}
        url = str(window.get_current_url() or "")
        parsed = urlsplit(url)
        host = self._official_trusted_host
        if parsed.scheme != "https" or parsed.hostname != host:
            state = "redirected"
        elif self._official_pending_url and url != self._official_pending_url:
            state = "loading"
        else:
            self._official_pending_url = ""
            state = "ready"
        return {"state": state, "url": url, "trusted_host": host}

    def trust_current_official_site(self) -> dict[str, str]:
        from official_apply import normalize_official_url
        window = self.current_official_browser_window()
        if window is None:
            raise RuntimeError("请先打开企业官网")
        current = normalize_official_url(str(window.get_current_url() or ""))
        self._official_trusted_host = urlsplit(current).hostname or ""
        self._official_pending_url = ""
        self.invalidate_official_preview()
        return self.official_page_status()

    def official_form_action(self, profile: dict[str, str], *, fill: bool,
                             include_id_number: bool = False) -> dict:
        from official_apply import build_form_script
        with self._lock:
            status = self.official_page_status()
            if status["state"] != "ready":
                self._official_preview = None
                return {"state": "wrong_site", "reason": "当前网址与已确认域名不一致，请核对后重新确认"}
            window = self.current_official_browser_window()
            if window is None:
                return {"state": "browser_closed", "reason": "企业官网浏览器已关闭"}
            stale = {"state": "stale_preview", "reason": "网页或个人资料已变化，请重新识别后填写"}
            preview_script = build_form_script(profile, status["trusted_host"], fill=False)
            if not fill:
                result = window.run_js(preview_script)
                self._official_preview = None
                if isinstance(result, dict) and result.get("state") == "ok":
                    self._official_preview = {
                        "url": status["url"], "host": status["trusted_host"],
                        "fingerprint": result.get("fingerprint"),
                        "available": result.get("available"),
                    }
                return result if isinstance(result, dict) else {"state": "error", "reason": "表单识别未返回结果"}
            preview = self._official_preview
            if (not preview or preview["url"] != status["url"] or
                    preview["host"] != status["trusted_host"]):
                self._official_preview = None
                return stale
            check = window.run_js(preview_script)
            if (not isinstance(check, dict) or check.get("state") != "ok" or
                    check.get("fingerprint") != preview["fingerprint"] or
                    check.get("available") != preview["available"]):
                self._official_preview = None
                return stale
            selected = {key: value for key, value in profile.items()
                        if key in preview["available"] and (key != "id_number" or include_id_number)}
            self._official_preview = None
            result = window.run_js(build_form_script(
                selected, status["trusted_host"], fill=True,
                expected_fingerprint=preview["fingerprint"]))
            return result if isinstance(result, dict) else {"state": "error", "reason": "表单填写未返回结果"}

    def close_official_browser_window(self) -> None:
        with self._lock:
            window, self._official_browser_window = self._official_browser_window, None
            self._official_trusted_host = ""
            self._official_pending_url = ""
            self._official_preview = None
        if window is not None and not window.events.closed.is_set():
            window.destroy()

    def open_detail_window(self, url: str):
        import webview

        window = webview.create_window("职位详情读取", url=url, hidden=True, js_api=None)
        with self._lock:
            self._detail_windows.add(window)
        window.events.closed += lambda: self._detail_windows.discard(window)
        if not window.events.loaded.wait(25):
            window.destroy()
            raise RuntimeError("职位详情加载超时")
        return window

    def close_browser_window(self, platform: str | None = None) -> None:
        with self._lock:
            if platform:
                window = self._browser_windows.pop(platform, None)
                if window is None and platform == "BOSS直聘" and not self._browser_windows:
                    window = self._browser_window
                windows = [window] if window is not None else []
            else:
                windows = list(self._browser_windows.values())
                if self._browser_window is not None and self._browser_window not in windows:
                    windows.append(self._browser_window)
                self._browser_windows.clear()
            if self._browser_window in windows:
                self._browser_window = next(iter(self._browser_windows.values()), None)
        for window in windows:
            if not window.events.closed.is_set():
                window.destroy()

    def ensure_controller(self, platform: str = "BOSS直聘"):
        with self._lock:
            controller = self.controllers.get(platform)
            if controller is None and self.controller is not None and self.controller.platform_name == platform:
                controller = self.controller
            if controller is None:
                if platform == "BOSS直聘":
                    from automation import AutomationController
                    from embedded_browser import EmbeddedBossPage
                    controller = AutomationController(
                        self._windows["index"], config_dir=bundle_dir() / "config",
                        page_factory=lambda: EmbeddedBossPage(self),
                    )
                else:
                    from site_adapters import EmbeddedSitePage, SITES
                    from site_automation import SiteAutomationController
                    site = SITES[platform]
                    controller = SiteAutomationController(
                        self._windows["index"], site=site,
                        config_dir=bundle_dir() / "config",
                        page_factory=lambda: EmbeddedSitePage(self, site),
                    )
                self.controllers[platform] = controller
            self.controller = controller
            return controller

    def start_automation(self, platform: str, mode: str | None = None) -> str:
        with self._launch_lock:
            if self._backfill_thread and self._backfill_thread.is_alive():
                return "正在补全旧记录，请等待完成后再开始任务"
            if mode not in {None, "apply_mode"}:
                return "运行方式仅支持自动投递"
            statuses = self.controller_statuses()
            active = {name for name, status in statuses.items() if status.get("running")}
            if platform in active:
                return "正在停止，请稍候重试" if statuses[platform].get("stopping") else "已运行"
            if len(active) >= 2:
                return "最多同时运行两个平台，请先停止其中一个"
            if self.current_browser_window(platform) is None:
                return f"请先打开{platform}内置浏览器，手动登录并准备网站简历"
            state = self._windows["index"].get_login_status(platform)
            if state != "logged_in":
                return f"请先在{platform}内置浏览器手动完成登录或安全验证"
            self._windows["index"].set_apply_config("work_mode", "apply_mode")
            try:
                return self.ensure_controller(platform).start(platform)
            except KeyError:
                return f"{platform} 的自动化适配器尚未完成"
            except Exception as exc:
                return f"启动失败：{exc}"

    def stop_automation(self, platform: str | None = None) -> str:
        with self._launch_lock:
            if platform:
                controller = self.controllers.get(platform)
                if controller is None and self.controller is not None and self.controller.platform_name == platform:
                    controller = self.controller
                return controller.stop() if controller else "已停止"
            controllers = list(dict.fromkeys([*self.controllers.values(), self.controller]))
            for controller in controllers:
                if controller is not None:
                    controller.stop()
            return "已停止"

    def update_timing(self) -> bool:
        if self.scheduler is None:
            return False
        self.scheduler.wake()
        return True

    def start_scheduler(self) -> None:
        from scheduler import DailyFilterScheduler

        with self._lock:
            if self.scheduler is None:
                self.scheduler = DailyFilterScheduler(
                    self._windows["index"], self.start_automation
                )
                self.scheduler.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全职高手独立客户端")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--check", action="store_true", help="check bundled assets without opening a window")
    args = parser.parse_args(argv)
    if args.check:
        index = bundle_dir() / "gui" / "templates" / "index.html"
        official = bundle_dir() / "gui" / "templates" / "official.html"
        required = [bundle_dir() / "config" / group / name
                    for group in ("boss", "zhilian", "qiancheng", "yjs", "liepin")
                    for name in ("code.json", "filter.json")]
        required.append(bundle_dir() / "config" / "lagou" / "filter.json")
        required.append(bundle_dir() / "config" / "niuke" / "filter.json")
        if not index.is_file() or not official.is_file() or any(not file.is_file() for file in required):
            raise SystemExit("Bundled UI or platform configuration missing")
        print(f"{VERSION}: assets present")
        return 0
    import webview
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False

    manager = WindowManager(args.data_dir)
    manager.open_window("index")
    webview.start(gui="edgechromium", private_mode=False,
                  storage_path=str(args.data_dir / "webview"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

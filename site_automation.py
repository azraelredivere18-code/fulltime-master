"""Shared filtering and auditable application workflow for recruitment sites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from automation import AutomationController, _job_tag
from site_adapters import SITES, Site, valid_site_url


def parse_site_card(card: Any, site: Site) -> dict[str, str] | None:
    if not isinstance(card, dict):
        return None
    link = str(card.get("link") or "").strip()
    title = str(card.get("title") or "").strip()
    if not title or not valid_site_url(site, link, detail=True):
        return None
    return {
        "title": title,
        "company": str(card.get("company") or "").strip(),
        "area": str(card.get("area") or "").strip(),
        "salary": str(card.get("salary") or "").strip(),
        "experience": _job_tag(str(card.get("experience") or ""), "experience"),
        "education": _job_tag(str(card.get("education") or ""), "education"),
        "employment_type": str(card.get("employment_type") or "").strip(),
        "hr_title": "", "activity": "",
        "summary": str(card.get("summary") or "").strip(),
        "link": link,
    }


class SiteAutomationController(AutomationController):
    """Reuse list filtering, sales checks, quotas, and receipt reconciliation."""

    # A local throttle for unverified sites, not a claimed platform limit.
    daily_limit = 30
    action_word = "投递"

    def __init__(self, store: Any, *, site: Site, page_factory, **kwargs: Any) -> None:
        self.site = site
        self.platform_name = site.name
        self.filter_group = {"智联招聘": "zhilian.filter", "前程无忧": "qiancheng.filter",
                             "应届生": "yjs.filter", "猎聘": "liepin.filter",
                             "拉勾": "lagou.filter", "牛客网": "niuke.filter"}[site.name]
        self.card_locator = "css:" + site.cards
        self.detail_locator = "css:" + site.detail
        self.card_parser = lambda card: parse_site_card(card, site)
        self.link_validator = lambda link: link if valid_site_url(site, link, detail=True) else ""
        super().__init__(store, page_factory=page_factory, **kwargs)

    def _validate_filters(self, active_filters: Any) -> None:
        if not isinstance(active_filters, dict):
            raise ValueError(f"{self.site.name} 筛选设置格式不正确")
        unsupported = [key for key, value in active_filters.items()
                       if value not in (None, "", "不限", [], "否")]
        if unsupported:
            raise ValueError(
                f"{self.site.name} 的网站筛选项尚未校准：{'、'.join(unsupported)}。"
                "请在平台设置清除这些选项，任务中的关键词、城市、正则及岗位类型筛选仍会执行"
            )

    def _city_code(self, city: str) -> str:
        group = {"智联招聘": "zhilian", "前程无忧": "qiancheng",
                 "应届生": "yjs", "猎聘": "liepin", "拉勾": "lagou",
                 "牛客网": "niuke"}[self.site.name]
        if group in {"lagou", "niuke"}:
            return city
        file = self.config_dir / group / "code.json"
        codes = json.loads(file.read_text(encoding="utf-8"))
        code = codes.get(city)
        if not isinstance(code, str) or not code:
            raise ValueError(f"{self.site.name} 城市配置中没有“{city}”")
        return city if group == "zhilian" else code

    def _navigate_plan(self, index: int) -> None:
        task, keyword, city, code = self._plans[index]
        if not hasattr(self._page, "navigate_search"):
            raise RuntimeError("网站搜索页导航失败")
        navigated = (self._page.navigate_search(keyword, city, code,
                                                str(task.get("employment_type") or "full_time"),
                                                str(task.get("recruitment_track") or "all"))
                     if self.site.name == "牛客网" else
                     self._page.navigate_search(keyword, city, code))
        if not navigated:
            raise RuntimeError("网站搜索页导航失败")
        self._task, self._search_city, self._plan_index = task, city, index
        self._last_card_count = 0
        self._detail_attempted.clear()
        self._metadata_attempted.clear()
        self._policy_rechecked.clear()
        self._seen_links_plan.clear()
        self._last_advance_seen = None
        self._result_advances = 0

    def _gate_message(self) -> str:
        current = str(getattr(self._page, "url", "") or "")
        if not current:
            return ""
        parsed = urlparse(current)
        if parsed.hostname not in self.site.hosts:
            return f"浏览器已离开{self.site.name}，请返回职位搜索页"
        state = self._page.login_state() if hasattr(self._page, "login_state") else "unknown"
        if state == "verification":
            return f"请在内置浏览器手动完成{self.site.name}安全验证"
        if state == "logged_out":
            return f"请在内置浏览器手动登录{self.site.name}，完成后会继续搜索"
        if self.mode == "apply_mode" and state != "logged_in":
            return f"尚未确认{self.site.name}登录状态；请手动登录后重试"
        if not parsed.path.startswith(self.site.search_path):
            return f"浏览器未在{self.site.name}搜索页，请返回搜索页"
        return ""

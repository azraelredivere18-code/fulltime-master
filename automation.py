"""Conservative BOSS job search and evidence-checked direct-chat adapter."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urljoin, urlparse

from backend import china_day
from application_filters import applied_company_reason, off_site_reason
from sales_roles import classify_sales_role
from employment_type import employment_type_reason, job_type
from recruitment_track import recruitment_track, recruitment_track_reason
from salary_codec import readable_salary


BOSS_HOME = "https://www.zhipin.com/"
BOSS_SEARCH = "https://www.zhipin.com/web/geek/jobs"
SUPPORTED_PLATFORM = "BOSS直聘"
DAILY_APPLICATION_LIMIT = 120
_TASK_SEPARATORS = re.compile(r"[\s,，|、;；-]+")


def boss_search_url(keyword: str, city_code: int) -> str:
    """Use the recovered BOSS city code in the public job-search URL."""
    return BOSS_SEARCH + "?" + urlencode({"query": keyword, "city": city_code})


def _task_terms(value: str, *, keyword: bool = False) -> list[str]:
    terms = [term for term in _TASK_SEPARATORS.split(value.strip()) if term]
    return [term.replace("_", " ") for term in terms] if keyword else terms


def _first_text(card: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            element = card.ele("css:" + selector, timeout=0)
            if element:
                value = str(element.text or "").strip()
                if value:
                    return value
        except Exception:
            continue
    return ""


def _first_link(card: Any) -> str:
    for selector in ('a[href*="/job_detail/"]', 'a[href*="job_detail"]', 'a[href]'):
        try:
            element = card.ele("css:" + selector, timeout=0)
            if not element:
                continue
            raw = element.attr("href") or ""
            link = _valid_job_link(raw)
            if link:
                return link
        except Exception:
            continue
    return ""


def _job_tag(value: str, field: str) -> str:
    value = value.strip()
    if field == "experience":
        return value if re.search(r"经验|应届|在校|实习|\d+\s*(?:[-~至]\s*\d+)?\s*年", value) else ""
    return value if re.search(r"学历|不限|初中|高中|中专|大专|专科|本科|硕士|博士|研究生", value) else ""


def parse_boss_card(card: Any) -> dict[str, str] | None:
    """Extract only fields visible in a BOSS job-list card."""
    if isinstance(card, Mapping):
        title = str(card.get("title") or "").strip()
        link = _valid_job_link(str(card.get("link") or ""))
        if not title or not link:
            return None
        return {
            "title": title,
            "company": str(card.get("company") or "").strip(),
            "salary": readable_salary(str(card.get("salary") or "")),
            "area": str(card.get("area") or "").strip(),
            "experience": _job_tag(str(card.get("experience") or ""), "experience"),
            "education": _job_tag(str(card.get("education") or ""), "education"),
            "hr_title": str(card.get("hr_title") or "").strip(),
            "activity": str(card.get("activity") or "").strip(),
            "summary": str(card.get("summary") or "").strip(),
            "link": link,
        }
    title = _first_text(card, (".job-name", ".job-title", "h3", "a.job-name"))
    company = _first_text(card, (".boss-name", ".company-name", ".company-text h3", ".company-text a", "h4"))
    link = _first_link(card)
    if not title or not link:
        return None
    try:
        summary = str(card.text or "").strip()
    except Exception:
        summary = title
    return {
        "title": title,
        "company": company,
        "salary": readable_salary(_first_text(card, (".job-salary", ".salary"))),
        "area": _first_text(card, (".company-location", ".job-area", ".job-area-wrapper", ".job-address")),
        "experience": _job_tag(_first_text(card, (".tag-list li:first-child", ".job-card-info li:first-child")), "experience"),
        "education": _job_tag(_first_text(card, (".tag-list li:nth-child(2)", ".job-card-info li:nth-child(2)")), "education"),
        "hr_title": _first_text(card, (".boss-info-attr", ".boss-title")),
        "activity": _first_text(card, (".boss-active-time",)),
        "summary": summary,
        "link": link,
    }


def _valid_job_link(raw: str) -> str:
    link = urljoin(BOSS_HOME, raw)
    parts = urlparse(link)
    if (parts.scheme == "https"
            and parts.hostname in {"www.zhipin.com", "zhipin.com"}
            and parts.path.startswith("/job_detail/")
            and not any(char in link for char in "'\"< >")):
        return link
    return ""


class AutomationController:
    """BOSS watcher with optional direct chat and auditable local results."""

    platform_name = SUPPORTED_PLATFORM
    filter_group = "boss.filter"
    card_locator = "css:.card-area .job-card-wrap, .job-card-wrapper"
    detail_locator = "css:.job-detail-section:nth-child(1) .job-sec-text"
    daily_limit = DAILY_APPLICATION_LIMIT
    action_word = "沟通"
    card_parser = staticmethod(parse_boss_card)
    link_validator = staticmethod(_valid_job_link)

    def __init__(
        self,
        store: Any,
        *,
        config_dir: str | Path | None = None,
        page_factory: Callable[[], Any],
        poll_seconds: float = 5.0,
        dwell_seconds: float = 15.0,
    ) -> None:
        self.store = store
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).resolve().parent / "config"
        self._page_factory = page_factory
        self.poll_seconds = poll_seconds
        self.dwell_seconds = dwell_seconds
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._page: Any = None
        self._task: dict[str, Any] | None = None
        self._plans: list[tuple[dict[str, Any], str, str, int]] = []
        self._plan_index = 0
        self._search_city = ""
        self._region_order: list[str] = []
        self._quota_day = china_day()
        self._region_allowance: dict[str, int] = {}
        self._region_baseline: dict[str, int] = {}
        self._region_effective = 0
        self._region_carry = 0
        self._metadata_attempted: set[tuple[Any, str]] = set()
        self._seen_links_plan: set[str] = set()
        self._last_advance_seen: int | None = None
        self._result_advances = 0
        self.last_error: str | None = None
        self.status_message = "未运行"
        self.saved_count = 0
        self._last_card_count = 0
        self._empty_plans = 0
        self._detail_attempted: set[tuple[Any, str]] = set()
        self._application_attempted: set[str] = set()
        self._sales_rechecked: set[tuple[Any, str]] = set()
        self._policy_rechecked: set[tuple[Any, str]] = set()
        self.mode = "filter_mode"
        self.applied_count = 0
        self._awaiting_login = False
        self._pending_application: dict[str, Any] | None = None
        self._known_cities: set[str] | None = None

    def _city_names(self) -> set[str]:
        if self._known_cities is None:
            names: set[str] = set()
            for group in ("boss", "zhilian", "qiancheng", "yjs"):
                file = self.config_dir / group / "code.json"
                if file.is_file():
                    codes = json.loads(file.read_text(encoding="utf-8"))
                    if isinstance(codes, dict):
                        names.update(str(city) for city in codes)
            self._known_cities = names
        return self._known_cities

    def _city_code(self, city: str) -> int:
        file = self.config_dir / "boss" / "code.json"
        if not file.is_file():
            raise RuntimeError("缺少 BOSS 城市代码配置")
        codes = json.loads(file.read_text(encoding="utf-8"))
        value = codes.get(city)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"BOSS 城市代码中没有“{city}”，请使用城市全名")
        return value

    def _build_plans(self) -> list[tuple[dict[str, Any], str, str, int]]:
        active_filters = self.store.get_apply_config(self.filter_group) or {}
        self._validate_filters(active_filters)
        plans = []
        for task in self.store.get_tasks():
            selected = task.get("platform")
            if selected is not None and self.platform_name not in str(selected).split(","):
                continue
            if task.get("search_prompt") or task.get("job_prompt"):
                raise ValueError(f"任务 {task['id']} 含未支持的 AI 提示词")
            if int(task.get("match_degree") or 0) > 0:
                raise ValueError(f"任务 {task['id']} 的 AI 匹配度需设为 0")
            keywords = _task_terms(str(task.get("keyword") or ""), keyword=True)
            cities = _task_terms(str(task.get("city") or ""))
            for keyword in keywords:
                for city in cities:
                    plans.append((dict(task), keyword, city, self._city_code(city)))
                    if len(plans) > 100:
                        raise ValueError("搜索组合超过 100 组，请拆分任务后运行")
        # Process all searches in one city before carrying unused slots onward.
        cities = list(dict.fromkeys(plan[2] for plan in plans))
        return [plan for city in cities for plan in plans if plan[2] == city]

    def _validate_filters(self, active_filters: Any) -> None:
        if not isinstance(active_filters, dict):
            raise ValueError("BOSS 筛选设置格式不正确")
        unsupported = [key for key, value in active_filters.items()
                       if key not in {"target", "liveness"} and value not in (None, "", "不限", [])]
        if unsupported:
            raise ValueError("当前尚未执行 BOSS 平台筛选项：" + "、".join(unsupported))
        valid_values = {
            "target": {None, "", "不限", "只投HR", "不投HR", "不投猎头"},
            "liveness": {None, "", "不限", "否", "是"},
        }
        for key, allowed in valid_values.items():
            if active_filters.get(key) not in allowed:
                raise ValueError(f"BOSS 平台筛选项 {key} 的取值尚未支持")

    def _plan_region_quota(self) -> None:
        self._region_order = list(dict.fromkeys(plan[2] for plan in self._plans))
        usage = self.store.daily_application_usage(platform=self.platform_name)
        self._quota_day = usage["day"]
        self._region_baseline = {city: usage["by_city"].get(city, 0) for city in self._region_order}
        target = dict(self._region_baseline)
        remaining = max(0, self.daily_limit - usage["total"])
        # Fill the least used selected region first; ties keep task order.
        for _ in range(remaining):
            city = min(self._region_order, key=lambda candidate: target[candidate])
            target[city] += 1
        self._region_allowance = {city: target[city] - self._region_baseline[city]
                                  for city in self._region_order}
        self._region_carry = 0
        self._region_effective = self._region_allowance[self._region_order[0]]

    def _city_slots_used(self, city: str) -> int:
        return self.store.daily_application_usage(platform=self.platform_name)["by_city"].get(city, 0)

    def _city_limit(self) -> int:
        if not self._region_order:
            return self.daily_limit
        return self._region_baseline.get(self._search_city, 0) + self._region_effective

    def _advance_plan(self) -> bool:
        current_city = self._search_city
        next_index = self._plan_index + 1
        while next_index < len(self._plans):
            next_city = self._plans[next_index][2]
            if next_city != current_city:
                used = self._city_slots_used(current_city) - self._region_baseline.get(current_city, 0)
                self._region_carry = max(0, self._region_effective - used)
                self._region_effective = self._region_allowance.get(next_city, 0) + self._region_carry
                self._navigate_plan(next_index)
                return True
            if self.mode != "apply_mode" or self._city_slots_used(current_city) < self._city_limit():
                self._navigate_plan(next_index)
                return True
            next_index += 1
        return False

    def _navigate_plan(self, index: int) -> None:
        task, keyword, city, city_code = self._plans[index]
        if self._page.get(boss_search_url(keyword, city_code)) is False:
            raise RuntimeError("浏览器导航失败")
        self._task = task
        self._search_city = city
        self._plan_index = index
        self._last_card_count = 0
        self._detail_attempted.clear()
        self._metadata_attempted.clear()
        self._policy_rechecked.clear()
        self._seen_links_plan.clear()
        self._last_advance_seen = None
        self._result_advances = 0

    def start(self, platform: str) -> str:
        if platform != self.platform_name:
            return f"{platform} 的自动化适配器尚未完成；目前只支持 BOSS直聘"
        with self._lock:
            if self._worker and self._worker.is_alive():
                return "正在停止，请稍候重试" if self._stop_event.is_set() else "已运行"
            self.mode = str(self.store.get_apply_config("work_mode") or "filter_mode")
            if self.mode not in {"filter_mode", "apply_mode"}:
                return "工作模式无效，请在投递设置中重新选择"
            try:
                plans = self._build_plans()
                if not plans:
                    return f"请先在设置中创建并选择{self.platform_name}任务"
                self._page = self._page or self._page_factory()
                self._plans = plans
                self._plan_region_quota()
                self._navigate_plan(0)
            except Exception as exc:
                self.last_error = str(exc)
                return f"打开{self.platform_name}职位页失败：{exc}"
            self._stop_event = threading.Event()
            self.last_error = None
            self.saved_count = 0
            self.applied_count = 0
            self._empty_plans = 0
            self._awaiting_login = False
            self._pending_application = None
            self._sales_rechecked.clear()
            self._application_attempted.clear()
            self.status_message = "正在等待职位列表或手动登录"
            self._worker = threading.Thread(target=self._watch, name="job-watcher", daemon=True)
            self._worker.start()
            return "已运行"

    def _gate_message(self) -> str:
        """Pause for manual login or challenge; never treat either as empty results."""
        raw_url = str(getattr(self._page, "url", "") or "")
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        if parsed.hostname not in {"www.zhipin.com", "zhipin.com"}:
            return "浏览器已离开 BOSS直聘，请返回职位搜索页"
        path = parsed.path.lower()
        if "verify" in path or "/passport/" in path:
            return "需要在浏览器中完成 BOSS直聘安全验证或登录"
        if "login" in path or "/user/" in path:
            return "需要在浏览器中登录 BOSS直聘"
        if hasattr(self._page, "login_state"):
            state = self._page.login_state()
            if state == "logged_out":
                return "请在内置浏览器手动登录 BOSS直聘，完成后会继续搜索"
            if state == "verification":
                return "请在内置浏览器手动完成 BOSS直聘安全验证"
            if self.mode == "apply_mode" and state != "logged_in":
                return "尚未确认登录状态；请在内置浏览器手动登录后重试"
        if not path.startswith("/web/geek/jobs"):
            return "浏览器未在 BOSS直聘职位搜索页，请返回搜索页"
        return ""

    def _watch(self) -> None:
        opened_at = time.monotonic()
        while not self._stop_event.is_set():
            try:
                if self._pending_application:
                    pending = self._pending_application
                    observed = (self._page.check_application_result(pending["link"])
                                if hasattr(self._page, "check_application_result") else "unknown")
                    if observed == "sent":
                        self.store.finalize_application_slot(
                            pending["link"], "confirmed", day=pending["day"],
                            platform=self.platform_name)
                        self.store.update_apply_record(pending["record_id"], {
                            "submit": "是", "submit_time": datetime.now().isoformat(timespec="seconds"),
                            "remarks": f"人工确认后页面显示已{self.action_word}", "attempt_state": "confirmed",
                        })
                        self.applied_count += 1
                        self._pending_application = None
                        self._navigate_plan(self._plan_index)
                        opened_at = time.monotonic()
                    else:
                        self.status_message = (
                            "请在内置浏览器手动完成安全验证" if observed == "verification" else
                            f"请在内置浏览器手动登录{self.platform_name}" if observed == "login" else
                            "平台今日沟通次数已达上限" if observed == "daily_limit" else
                            "投递结果待确认：请在内置浏览器检查当前职位，完成简历选择或确认弹窗后程序会核实回执"
                        )
                        if observed == "daily_limit":
                            break
                        self._stop_event.wait(self.poll_seconds)
                        continue
                if self.mode == "apply_mode" and china_day() != self._quota_day:
                    self._plan_region_quota()
                    self._navigate_plan(0)
                    opened_at = time.monotonic()
                gate = self._gate_message()
                if gate and self._awaiting_login and hasattr(self._page, "login_state"):
                    if self._page.login_state() == "logged_in":
                        self._navigate_plan(self._plan_index)
                        gate = self._gate_message()
                if gate:
                    self.status_message = gate
                    if "登录" in gate or "验证" in gate:
                        self._awaiting_login = True
                    opened_at = time.monotonic()
                else:
                    self._awaiting_login = False
                    verb = f"筛选并{self.action_word}" if self.mode == "apply_mode" else "筛选"
                    self.status_message = f"正在{verb} {self._plan_index + 1}/{len(self._plans)} 组搜索"
                    self.saved_count += self.scan_once()
                    used = self.store.daily_application_usage(platform=self.platform_name)["total"] if self.mode == "apply_mode" else 0
                    if self.mode == "apply_mode" and used >= self.daily_limit:
                        self.status_message = f"本工具今日 {self.daily_limit} 个{self.platform_name}名额已用完"
                        break
                    region_full = (self.mode == "apply_mode" and
                                   self._city_slots_used(self._search_city) >= self._city_limit())
                    if region_full or time.monotonic() - opened_at >= self.dwell_seconds:
                        max_segments = self.store.get_apply_config("max_page")
                        max_segments = max_segments if isinstance(max_segments, int) and max_segments > 0 else 30
                        can_advance = (not region_full and self._result_advances < max_segments - 1
                                       and (self._last_advance_seen is None or
                                            len(self._seen_links_plan) > self._last_advance_seen))
                        if can_advance and hasattr(self._page, "advance_search_results"):
                            if self._page.advance_search_results():
                                self._last_advance_seen = len(self._seen_links_plan)
                                self._result_advances += 1
                                opened_at = time.monotonic()
                                continue
                        if self._last_card_count == 0:
                            self._empty_plans += 1
                        if self._advance_plan():
                            opened_at = time.monotonic()
                        else:
                            self.status_message = (
                                f"本轮检索结束；{self._empty_plans} 组未检测到职位卡片，请检查页面"
                                if self._empty_plans else "本轮筛选已完成"
                            )
                            break
            except Exception as exc:
                self.last_error = str(exc)
                self.status_message = f"筛选中断：{exc}"
                break
            self._stop_event.wait(self.poll_seconds)

    def get_run_status(self) -> dict[str, Any]:
        worker = self._worker
        usage = self.store.daily_application_usage(platform=self.platform_name)
        return {
            "running": bool(worker and worker.is_alive() and not self._stop_event.is_set()),
            "message": self.status_message,
            "current": self._plan_index + 1 if self._plans else 0,
            "total": len(self._plans),
            "saved": self.saved_count,
            "applied": self.applied_count,
            "mode": self.mode,
            "platform": self.platform_name,
            "daily_used": usage["total"],
            "daily_limit": self.daily_limit,
            "search_city": self._search_city,
            "region_target": self._region_effective,
            "region_used": max(0, usage["by_city"].get(self._search_city, 0)
                               - self._region_baseline.get(self._search_city, 0)),
        }

    def scan_once(self) -> int:
        """Save unseen visible job cards matching the configured list-page regex."""
        page, task = self._page, self._task
        if page is None or task is None:
            return 0
        try:
            cards = list(page.eles(self.card_locator, timeout=0) or [])
        except Exception as exc:
            raise RuntimeError(f"无法读取职位列表：{exc}") from exc
        self._last_card_count = len(cards)
        pattern = re.compile(str(task.get("search_re") or "")) if task.get("search_re") else None
        banned = []
        for row in self.store.get_blocklist():
            expression = str(row.get("company", "")).strip()
            if expression:
                try:
                    banned.append(re.compile(expression, re.I))
                except re.error as exc:
                    raise ValueError(f"公司黑名单正则表达式无效：{expression}（{exc}）") from exc
        active_filters = self.store.get_apply_config(self.filter_group) or {}
        exclude_sales = self.store.get_apply_config("exclude_sales_roles") is True
        company_filter = str(self.store.get_apply_config("company_filter") or "不过滤")
        off_site_filter = self.store.get_apply_config("off_site_filter") == "过滤"
        task_cities = _task_terms(str(task.get("city") or ""))
        filter_city = self._search_city or (task_cities[0] if len(task_cities) == 1 else "")
        task_id = task.get("id")
        all_records = self.store.get_apply_record()
        known = {str(row.get("link", "")): row for row in all_records
                 if row.get("task_id") == task_id}
        other_contacted = {
            str(row.get("link", "")) for row in all_records if row.get("task_id") != task_id and
            (row.get("submit") == "是" or "未记录为成功" in str(row.get("remarks") or ""))
        }
        saved = 0
        for card in cards or []:
            if self._stop_event.is_set():
                break
            item = self.card_parser(card)
            if not item:
                continue
            item["employment_type"] = str(item.get("employment_type") or card.get("employment_type") or "") if isinstance(card, dict) else str(item.get("employment_type") or "")
            if isinstance(card, dict):
                item["recruitment_track"] = str(card.get("recruitment_track") or "")
            self._seen_links_plan.add(item["link"])
            existing = known.get(item["link"])
            detail = None
            metadata: dict[str, str] = {}
            missing = [field for field in ("company", "area", "salary", "experience", "education")
                       if not item[field] and not (existing and existing.get(field))]
            targeted_track = (task.get("recruitment_track") or "all") != "all"
            needs_type_evidence = job_type(item) == "unknown" or targeted_track
            if (missing or needs_type_evidence) and (task_id, item["link"]) not in self._metadata_attempted:
                self._metadata_attempted.add((task_id, item["link"]))
                detail, metadata = self._read_job_detail_data(item["link"])
                for field in missing:
                    value = metadata.get(field, "")
                    item[field] = _job_tag(value, field) if field in {"experience", "education"} else value
                if metadata.get("employment_type"):
                    item["employment_type"] = str(metadata["employment_type"])
                if metadata.get("recruitment_track"):
                    listed = recruitment_track({"recruitment_track": item.get("recruitment_track")})
                    detailed = recruitment_track({"recruitment_track": metadata["recruitment_track"]})
                    item["recruitment_track"] = (
                        "conflict" if listed != "unknown" and detailed != "unknown" and
                        listed != detailed else str(metadata["recruitment_track"]))
                if detail:
                    item["description"] = detail
            if existing:
                enrich = {field: item[field] for field in
                          ("company", "area", "salary", "experience", "education")
                          if item[field] and not existing.get(field)}
                if self._search_city and not existing.get("search_city"):
                    enrich["search_city"] = self._search_city
                if enrich:
                    self.store.update_apply_record(existing["id"], enrich)
                    existing.update(enrich)
            retry_detail = bool(existing and existing.get("remarks") in {
                "详情页未读取到职位描述", "销售性质待确认：职位描述未读取到"})
            retry_sales = bool(exclude_sales and existing and
                               existing.get("submit") != "是" and
                               (task_id, item["link"]) not in self._sales_rechecked and
                               not str(existing.get("remarks") or "").startswith("销售岗位已排除"))
            retry_apply = bool(self.mode == "apply_mode" and existing and
                               existing.get("submit") != "是" and
                               "未记录为成功" not in str(existing.get("remarks") or "") and
                               "需要人工确认" not in str(existing.get("remarks") or ""))
            retry_policy = bool(existing and existing.get("submit") != "是" and
                                existing.get("attempt_state") != "pending" and
                                (banned or company_filter != "不过滤" or off_site_filter) and
                                (task_id, item["link"]) not in self._policy_rechecked)
            if existing and not retry_detail and not retry_apply and not retry_sales and not retry_policy:
                continue
            if (retry_detail or retry_apply) and (task_id, item["link"]) in self._detail_attempted:
                continue
            already_attempted = self.mode == "apply_mode" and item["link"] in self._application_attempted
            if already_attempted and existing:
                continue
            recruiter_reason = self._recruiter_filter_reason(item, active_filters)
            prior_company_reason = applied_company_reason(
                item["company"] or (existing.get("company", "") if existing else ""),
                all_records, company_filter, self.platform_name, china_day())
            region_reason = (off_site_reason(
                item["area"] or (existing.get("area", "") if existing else ""),
                filter_city, self._city_names(), applying=self.mode == "apply_mode")
                if off_site_filter and filter_city else None)
            attempted_contact = False
            pending_confirmation = False
            effective_company = item["company"] or (existing.get("company", "") if existing else "")
            if effective_company and any(pattern.search(effective_company) for pattern in banned):
                remarks = "公司黑名单"
            elif employment_type_reason(str(task.get("employment_type") or "full_time"), item,
                                        strict_unknown=self.platform_name != "BOSS直聘"):
                remarks = employment_type_reason(str(task.get("employment_type") or "full_time"), item,
                                                 strict_unknown=self.platform_name != "BOSS直聘")
            elif targeted_track and detail is None:
                remarks = "仅投指定招聘渠道：详情页未能核对，暂不投递"
            elif recruitment_track_reason(str(task.get("recruitment_track") or "all"), item):
                remarks = recruitment_track_reason(str(task.get("recruitment_track") or "all"), item)
            elif prior_company_reason:
                remarks = prior_company_reason
            elif region_reason:
                remarks = region_reason
            elif pattern and not pattern.search(item["title"]):
                remarks = "正则筛选职位不符合"
            elif recruiter_reason:
                remarks = recruiter_reason
            else:
                preliminary = classify_sales_role(item["title"]) if exclude_sales else None
                if task.get("job_re") or (preliminary and preliminary.status == "unknown"):
                    self._detail_attempted.add((task_id, item["link"]))
                    if detail is None:
                        detail, metadata = self._read_job_detail_data(item["link"])
                        for field in ("company", "area", "salary", "experience", "education"):
                            if not item[field]:
                                value = metadata.get(field, "")
                                item[field] = (_job_tag(value, field)
                                               if field in {"experience", "education"} else value)
                if exclude_sales:
                    decision = (preliminary if preliminary.status != "unknown"
                                else classify_sales_role(item["title"], detail))
                    if decision.status == "sales":
                        remarks = "销售岗位已排除：" + decision.evidence
                    elif decision.status == "unknown":
                        remarks = "销售性质待确认：职位描述未读取到"
                    else:
                        remarks = ""
                else:
                    remarks = ""
                if not remarks and task.get("job_re"):
                    if detail is None:
                        remarks = "详情页未读取到职位描述"
                    elif not re.search(str(task["job_re"]), detail):
                        remarks = "详情正则筛选职位不符合"
                if not remarks and self.mode == "apply_mode":
                    if already_attempted or item["link"] in other_contacted:
                        remarks = "同一职位已在其他任务中沟通或待核实，跳过重复操作"
                    elif not hasattr(page, "apply_job"):
                        remarks = "未接入当前浏览器的沟通操作"
                    else:
                        slot_day = china_day()
                        reservation = self.store.reserve_application_slot(
                            item["link"], self._search_city,
                            day=slot_day, daily_limit=self.daily_limit,
                            city_limit=self._city_limit(), platform=self.platform_name)
                        if reservation == "duplicate":
                            remarks = "同一职位今日已沟通或待核实，跳过重复操作"
                        elif reservation == "daily_limit":
                            remarks = f"本工具今日{self.platform_name}的{self.daily_limit}个名额已用完"
                            self.status_message = remarks
                            self._stop_event.set()
                        elif reservation == "city_limit":
                            remarks = f"{self._search_city or '当前地区'}的本轮名额已用完，转到下个地区"
                        else:
                            try:
                                result = page.apply_job(item["link"])
                            except Exception as exc:
                                # The browser may have clicked before failing. Keep the slot and audit it.
                                result = {"state": "unknown", "clicked": True,
                                          "reason": f"浏览器操作中断：{exc}"}
                            attempted_contact = True
                            state = str(result.get("state") or "unknown")
                            clicked = result.get("clicked") is not False
                            self.store.finalize_application_slot(
                                item["link"], "confirmed" if state == "sent" else
                                ("unknown" if clicked else "released"), day=slot_day,
                                platform=self.platform_name)
                            if clicked:
                                self._application_attempted.add(item["link"])
                            reason = str(result.get("reason") or "")
                            if state == "sent":
                                remarks = f"已{self.action_word}；页面显示成功状态"
                                self.applied_count += 1
                            elif state in {"logged_out", "login"}:
                                remarks = "请手动登录后重试"
                                self.status_message = "请在内置浏览器手动登录 BOSS直聘"
                            elif state == "verification":
                                remarks = "请手动完成安全验证后重试"
                                self.status_message = "请在内置浏览器手动完成安全验证"
                            elif state == "daily_limit":
                                remarks = "平台今日沟通次数已达上限"
                                self.status_message = remarks
                                self._stop_event.set()
                            elif state == "needs_confirmation":
                                remarks = "投递需要人工确认；未记录为成功"
                                pending_confirmation = True
                            elif state == "needs_resume":
                                remarks = "平台提示先完善或选择简历；未记录为成功"
                                pending_confirmation = True
                            else:
                                remarks = (reason or "沟通状态未确认") + "；未记录为成功"
                                pending_confirmation = state == "unknown" and clicked
                if not remarks:
                    remarks = "仅筛选保存；未自动投递"
            record = {
                "source": self.platform_name,
                "task_id": task_id,
                "submit": "是" if remarks == f"已{self.action_word}；页面显示成功状态" else "否",
                "submit_time": datetime.now().isoformat(timespec="seconds") if remarks == f"已{self.action_word}；页面显示成功状态" else "",
                "title": item["title"],
                "company": item["company"] or (existing.get("company", "") if existing else ""),
                "area": item["area"] or (existing.get("area", "") if existing else ""),
                "salary": item["salary"] or (existing.get("salary", "") if existing else ""),
                "experience": item["experience"] or (existing.get("experience", "") if existing else ""),
                "education": item["education"] or (existing.get("education", "") if existing else ""),
                "search_city": self._search_city or (existing.get("search_city", "") if existing else ""),
                "application_day": slot_day if attempted_contact else
                    (existing.get("application_day", "") if existing else ""),
                "attempt_state": ("pending" if pending_confirmation else
                                  "confirmed" if remarks == f"已{self.action_word}；页面显示成功状态" else
                                  "unknown" if attempted_contact and clicked else
                                  "released" if attempted_contact else
                                  (existing.get("attempt_state", "") if existing else "")),
                "remarks": remarks,
                "employment_type": job_type(item),
                "recruitment_track": recruitment_track(item),
                "link": item["link"],
            }
            if existing:
                self.store.update_apply_record(existing["id"], record)
                record_id = existing["id"]
            else:
                record_id = self.store.add_apply_record(record)
                known[item["link"]] = {"id": record_id, **record}
                saved += 1
            if pending_confirmation:
                self._pending_application = {"link": item["link"], "record_id": record_id,
                                             "day": slot_day}
            if exclude_sales:
                self._sales_rechecked.add((task_id, item["link"]))
            self._policy_rechecked.add((task_id, item["link"]))
            if attempted_contact:
                break  # One site action per poll; avoid a burst of chat requests.
        return saved

    def reconcile_saved_record(self, record_id: int) -> dict[str, str]:
        """Check a pending BOSS record against visible site state after restart."""
        rows = [row for row in self.store.get_apply_record() if row["id"] == record_id]
        if not rows or rows[0].get("source") != self.platform_name:
            return {"state": "invalid", "reason": f"未找到{self.platform_name}投递记录"}
        row = rows[0]
        if row.get("attempt_state") != "pending":
            return {"state": "invalid", "reason": "该记录没有待核实的沟通操作"}
        if self._page is None:
            self._page = self._page_factory()
        if not hasattr(self._page, "login_state") or self._page.login_state() != "logged_in":
            return {"state": "login", "reason": f"请先在内置浏览器手动登录{self.platform_name}"}
        link = self.link_validator(str(row.get("link") or ""))
        if not link:
            return {"state": "invalid", "reason": "职位链接无效"}
        if urlparse(str(getattr(self._page, "url", ""))).path != urlparse(link).path:
            self._page.get(link)
        state = (self._page.check_application_result(link)
                 if hasattr(self._page, "check_application_result") else "unknown")
        if state != "sent":
            return {"state": state, "reason": "页面仍未显示已沟通；保留待核实状态和今日名额"}
        day = str(row.get("application_day") or china_day())
        self.store.finalize_application_slot(link, "confirmed", day=day,
                                             platform=self.platform_name)
        self.store.update_apply_record(record_id, {
            "submit": "是", "submit_time": datetime.now().isoformat(timespec="seconds"),
            "remarks": f"核实后页面显示已{self.action_word}", "attempt_state": "confirmed",
        })
        return {"state": "confirmed", "reason": "已核实页面成功回执"}

    @staticmethod
    def _recruiter_filter_reason(item: dict[str, str], filters: dict[str, Any]) -> str | None:
        target = str(filters.get("target") or "")
        role = item.get("hr_title", "").casefold()
        is_hr = any(word in role for word in ("hr", "人事", "人力", "招聘专员"))
        is_headhunter = "猎头" in role
        if target == "只投HR" and not is_hr:
            return "招聘者类型不符合或未显示"
        if target == "不投HR" and (is_hr or not role):
            return "招聘者类型不符合或未显示"
        if target == "不投猎头" and (is_headhunter or not role):
            return "招聘者类型不符合或未显示"
        if str(filters.get("liveness") or "") == "是":
            activity = item.get("activity", "")
            if not any(word in activity for word in ("在线", "刚刚活跃", "今日活跃", "昨天活跃", "本周活跃")):
                return "招聘者近期活跃状态未确认"
        return None

    def _read_job_detail(self, link: str) -> str | None:
        return self._read_job_detail_data(link)[0]

    def backfill_record_metadata(self, progress: Callable[[int, int, int], None] | None = None) -> dict[str, int]:
        """Read saved links for this platform without submitting applications."""
        if self._page is None:
            self._page = self._page_factory()
        if not hasattr(self._page, "login_state") or self._page.login_state() != "logged_in":
            raise RuntimeError(f"请先在内置浏览器手动登录{self.platform_name}，再补全旧记录")
        fields = ("company", "area", "salary", "experience", "education")
        rows = [row for row in self.store.get_apply_record()
                if row.get("source") == self.platform_name and self.link_validator(str(row.get("link") or ""))
                and (any(not row.get(field) for field in fields) or
                     row.get("employment_type") in (None, "", "unknown"))]
        cache: dict[str, tuple[str | None, dict[str, str]]] = {}
        updated = 0
        for index, row in enumerate(rows, 1):
            if self._page.login_state() != "logged_in":
                raise RuntimeError("登录状态已改变，请在内置浏览器手动处理后重试")
            link = str(row["link"])
            if link not in cache:
                cache[link] = self._read_job_detail_data(link)
            description, metadata = cache[link]
            enrich = {}
            for field in fields:
                if row.get(field):
                    continue
                value = str(metadata.get(field) or "").strip()
                if field in {"experience", "education"}:
                    value = _job_tag(value, field)
                if value:
                    enrich[field] = value
            if row.get("employment_type") in (None, "", "unknown"):
                observed_type = job_type({
                    "title": row.get("title"),
                    "employment_type": metadata.get("employment_type"),
                    "description": description,
                })
                if observed_type != "unknown":
                    enrich["employment_type"] = observed_type
            if enrich:
                self.store.update_apply_record(row["id"], enrich)
                updated += 1
            if progress:
                progress(index, len(rows), updated)
        return {"checked": len(rows), "updated": updated}

    def _read_job_detail_data(self, link: str) -> tuple[str | None, dict[str, str]]:
        """Read visible description and metadata from one disposable detail tab."""
        tab = None
        try:
            tab = self._page.new_tab(link, background=True)
            detail_url = str(getattr(tab, "url", "") or "")
            if detail_url and urlparse(detail_url).path.lower().find("verify") >= 0:
                return None, {}
            metadata = tab.metadata() if hasattr(tab, "metadata") else {}
            try:
                element = tab.ele(self.detail_locator, timeout=3)
                text = str(element.text or "").strip() if element else ""
            except Exception as exc:
                self.last_error = f"详情描述读取失败：{exc}"
                text = ""
            return text or None, metadata
        except Exception as exc:
            self.last_error = f"详情页读取失败：{exc}"
            return None, {}
        finally:
            if tab is not None:
                try:
                    tab.close()
                except Exception:
                    pass

    def stop(self) -> str:
        self._stop_event.set()
        worker = self._worker
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=2)
        with self._lock:
            self._worker = worker if worker and worker.is_alive() else None
            self._task = None
            self.status_message = "已停止"
        return "已停止"

    def close(self) -> None:
        self.stop()
        with self._lock:
            page, self._page = self._page, None
        if page is not None:
            try:
                page.quit(timeout=3, force=False)
            except Exception:
                pass

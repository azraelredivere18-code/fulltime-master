"""Local, auditable filters applied before any website submission action."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Iterable, Mapping


def _plain(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def company_key(value: Any) -> str:
    # Keep legal suffixes and punctuation: similar names are not the same employer.
    return re.sub(r"\s+", "", _plain(value)).casefold()


def applied_company_reason(
    company: str, records: Iterable[Mapping[str, Any]], mode: str,
    platform: str, today: str,
) -> str | None:
    if mode not in {"过滤10天内同一平台投递过的公司", "过滤10天内不同平台投递过的公司"}:
        return None
    key = company_key(company)
    if not key:
        return None
    current_day = date.fromisoformat(today)
    first_day = current_day - timedelta(days=9)
    for row in records:
        if row.get("submit") != "是" or company_key(row.get("company")) != key:
            continue
        if mode == "过滤10天内同一平台投递过的公司" and row.get("source") != platform:
            continue
        raw_day = str(row.get("submit_time") or row.get("create_time") or "")[:10]
        try:
            submitted_day = date.fromisoformat(raw_day)
        except ValueError:
            continue
        if first_day <= submitted_day <= current_day:
            return f"10天内已投递公司（{row.get('source') or '未知平台'}）"
    return None


def _city_key(value: Any) -> str:
    value = re.sub(r"\s+", "", _plain(value))
    return re.sub(r"(?:市|地区|自治州)$", "", value)


def off_site_reason(
    area: str, search_city: str, known_cities: Iterable[str], *, applying: bool,
) -> str | None:
    """Reject only a clear different city; unresolved locations block submission."""
    area_text = _plain(area)
    expected = _city_key(search_city)
    if not expected or not area_text or any(x in area_text for x in ("全国", "多地", "不限", "远程")):
        return "岗位地区未确认，请人工核对" if applying else None
    candidates = {_city_key(city) for city in known_cities if _city_key(city)}
    candidates.add(expected)
    matches = {city for city in candidates if city in area_text}
    if len(matches) != 1:
        return "岗位地区未确认，请人工核对" if applying else None
    actual = next(iter(matches))
    if actual != expected:
        return f"异地职位：岗位地区为{area_text}，搜索城市为{search_city}"
    return None

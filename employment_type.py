"""Conservative job type checks before a task sends an application."""

from __future__ import annotations

import re
from typing import Mapping, Any


_INTERNSHIP = re.compile(r"实习|见习|intern(?:ship)?", re.I)
_FULL_TIME = re.compile(r"全职|正式岗位|社会招聘|社招|full[ -]?time", re.I)
_LABELLED_TYPE = re.compile(
    r"(?:岗位性质|职位性质|工作性质|招聘类型|岗位类型|Employment Type)\s*[:：]\s*"
    r"(实习|见习|internship|全职|正式岗位|社会招聘|社招|full[ -]?time)", re.I,
)


def job_type(item: Mapping[str, Any]) -> str:
    """Use title, explicit badge, or a labelled type in visible page text."""
    title = str(item.get("title") or "")
    badge = str(item.get("employment_type") or "")
    if _INTERNSHIP.search(title) or _INTERNSHIP.search(badge):
        return "internship"
    if _FULL_TIME.search(title) or _FULL_TIME.search(badge):
        return "full_time"
    for field in ("summary", "description"):
        match = _LABELLED_TYPE.search(str(item.get(field) or ""))
        if match:
            return "internship" if _INTERNSHIP.search(match.group(1)) else "full_time"
    return "unknown"


def employment_type_reason(expected: str, item: Mapping[str, Any], *,
                           strict_unknown: bool = False) -> str | None:
    observed = job_type(item)
    if expected == "internship":
        return None if observed == "internship" else "仅投实习岗位：页面未明确标注实习"
    if expected == "full_time":
        if observed == "internship":
            return "仅投全职岗位：已排除实习职位"
        if observed == "unknown" and strict_unknown:
            return "仅投全职岗位：页面未明确标注全职"
    return None

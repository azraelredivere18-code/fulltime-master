"""Explicit campus/social recruitment evidence for automatic applications."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit


_CAMPUS = re.compile(r"校(?:园)?招(?:聘)?|应届(?:生|毕业生)(?:招聘|计划)|graduate\s*(?:program|recruitment)|campus\s*(?:recruitment|hiring)", re.I)
_SOCIAL = re.compile(r"社(?:会)?招(?:聘)?|社会人士招聘|experienced\s*(?:hire|recruitment)|social\s*(?:recruitment|hiring)", re.I)
_LABEL = re.compile(r"(?:招聘(?:渠道|类别|类型)|招录类型|招聘项目|Recruitment\s*Type)\s*[:：]\s*([^\n，,;；]{1,32})", re.I)


def recruitment_track(item: Mapping[str, Any]) -> str:
    """Return a track only when the listing itself supplies direct evidence."""
    direct = " ".join(str(item.get(key) or "") for key in
                      ("recruitment_track", "employment_type", "title", "category"))
    campus, social = bool(_CAMPUS.search(direct)), bool(_SOCIAL.search(direct))
    for key in ("summary", "description"):
        for match in _LABEL.finditer(str(item.get(key) or "")):
            campus = campus or bool(_CAMPUS.search(match.group(1)))
            social = social or bool(_SOCIAL.search(match.group(1)))
    path = urlsplit(str(item.get("link") or "")).path.lower()
    if re.search(r"/(campus|school-recruit|graduate)(?:/|$)", path):
        campus = True
    if re.search(r"/(social|experienced)(?:/|$)", path):
        social = True
    if campus != social:
        return "campus" if campus else "social"
    return "unknown"


def recruitment_track_reason(expected: str, item: Mapping[str, Any]) -> str | None:
    if expected == "all":
        return None
    if expected not in {"campus", "social"}:
        raise ValueError("Invalid recruitment track")
    actual = recruitment_track(item)
    if actual == expected:
        return None
    label = "校招" if expected == "campus" else "社招"
    return (f"仅投{label}岗位：页面标注了另一招聘渠道" if actual != "unknown" else
            f"仅投{label}岗位：页面未明确标注招聘渠道")

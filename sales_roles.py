"""Conservative, explainable sales-role classification for job applications."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SalesDecision:
    status: str  # sales, non_sales, unknown
    evidence: str


_NON_SALES_TITLE = re.compile(
    r"销售(?:运营|支持|数据|分析|内勤|行政|助理)|售前|售后|销售额分析|销售系统|"
    r"销售管理系统|sales\s+(?:operations|ops|support|analyst|analytics|engineer)", re.I
)
_DIRECT_TITLE = re.compile(
    r"(?<!非)销售(?:代表|专员|顾问|经理|主管|总监|工程师|精英|人员|岗|员)?|"
    r"电销|电话营销|电话销售|地推|业务员|推销|"
    r"\b(?:sales\s+(?:rep(?:resentative)?|executive|manager|consultant|associate)|"
    r"account\s+executive|[bs]dr)\b", re.I
)
_AMBIGUOUS_TITLE = re.compile(
    r"客户经理|客户顾问|商务拓展|业务拓展|渠道(?:经理|专员|拓展)|市场拓展|"
    r"获客|招商|营销|\bBD\b|business\s+development", re.I
)
_SALES_ACTIONS = (
    ("开发客户", re.compile(r"开发(?:新)?客户|拓展(?:新)?客户|客户开发|客户拓展|寻找(?:潜在)?客户|挖掘客户|获客")),
    ("销售业绩", re.compile(r"销售(?:目标|任务|业绩|指标)|业绩(?:目标|指标|考核)|完成(?:销售|业绩)|KPI", re.I)),
    ("成交签约", re.compile(r"签单|签约|促成交易|成交|转化客户|达成合作|合同谈判")),
    ("销售提成", re.compile(r"销售提成|业绩提成|底薪.{0,8}提成|佣金")),
    ("产品推介", re.compile(r"推销(?:产品|服务)|推介(?:产品|服务)|向客户推广|客户拜访")),
)


def classify_sales_role(title: str, detail: str | None = None) -> SalesDecision:
    """Use title first; require two duty signals for a generic/ambiguous title.

    Unknown means the description needed to resolve the title is unavailable.
    It must never be treated as permission to submit automatically.
    """
    title = str(title or "").strip()
    if not title:
        return SalesDecision("unknown", "缺少岗位名称")
    if _NON_SALES_TITLE.search(title):
        return SalesDecision("non_sales", "岗位名称为销售支持或非销售职能")
    direct = _DIRECT_TITLE.search(title)
    if direct:
        return SalesDecision("sales", f"岗位名称含“{direct.group(0).strip()}”")
    ambiguous = _AMBIGUOUS_TITLE.search(title)
    if detail is None:
        return SalesDecision("unknown", "职位描述尚未读取")
    signals = [label for label, pattern in _SALES_ACTIONS if pattern.search(detail)]
    if len(signals) >= 2:
        return SalesDecision("sales", "职责包含" + "、".join(signals[:3]))
    if ambiguous and not detail.strip():
        return SalesDecision("unknown", "岗位名称可能涉及销售，职位描述为空")
    return SalesDecision("non_sales", "未发现足够的销售职责证据")

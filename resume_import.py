"""Conservative, local-only extraction of reusable profile fields from resume text."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from official_apply import PROFILE_FIELDS


LABELS = {
    "full_name": ("姓名", "真实姓名", "中文姓名", "Name"),
    "phone": ("手机号码", "手机号", "联系电话", "手机", "Mobile", "Phone"),
    "email": ("电子邮箱", "电子邮件", "邮箱", "Email", "E-mail"),
    "id_number": ("身份证号码", "身份证号", "身份证", "证件号码"),
    "gender": ("性别", "Gender"),
    "birth_date": ("出生年月", "出生日期", "生日"),
    "ethnicity": ("民族",),
    "political_status": ("政治面貌",),
    "household_registration": ("户籍所在地", "户籍地址", "户籍"),
    "current_city": ("现居城市", "现居地", "当前城市"),
    "address": ("通信地址", "联系地址", "现居住址"),
    "university": ("毕业院校", "就读学校", "学校名称", "院校名称", "学校"),
    "degree": ("学位",),
    "education": ("最高学历", "学历", "Education"),
    "major": ("所学专业", "专业名称", "专业", "Major"),
    "graduation_date": ("毕业日期", "毕业时间", "毕业年月"),
    "school_start_date": ("入学日期", "入学时间"),
    "work_years": ("工作年限", "工作经验年限"),
    "self_intro": ("自我介绍", "自我评价", "个人总结"),
    "skills": ("技能特长", "专业技能", "个人技能"),
}

_UNSAFE_CONTEXT = re.compile(r"紧急联系人|紧急联络|家庭成员|家属|亲属|父亲|母亲|配偶|子女|推荐人|证明人|推荐信|银行|银行卡|开户", re.I)
_MOBILE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?(1[3-9]\d{9})(?!\d)")
_EMAIL = re.compile(r"(?<![\w.-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
_ALL_LABELS = tuple(sorted({label for labels in LABELS.values() for label in labels}, key=len, reverse=True))
_MARKER = re.compile(r"(?<![\w\u4e00-\u9fff])(" + "|".join(map(re.escape, _ALL_LABELS)) + r")\s*[:：]", re.I)
_EDUCATION_HEADING = re.compile(r"^教育(?:背景|经历|信息)$")
_NEXT_HEADING = re.compile(r"^(?:工作|实习|项目|校园|获奖|技能|专业技能|自我|个人|社会实践).{0,8}$")
_UNIVERSITY = re.compile(r"[\u4e00-\u9fff·]{2,24}(?:大学|学院)")
_LEVEL = re.compile(r"(?<![\u4e00-\u9fff])(?:大专|专科|本科|硕士研究生|硕士|博士研究生|博士)(?![\u4e00-\u9fff])")


def _plausible(key: str, value: str) -> bool:
    if not value or len(value) > (1200 if key in {"self_intro", "skills"} else 100):
        return False
    if _UNSAFE_CONTEXT.search(value):
        return False
    if key == "full_name":
        return bool(re.fullmatch(r"[\u4e00-\u9fff·]{2,8}|[A-Za-z][A-Za-z .'-]{2,49}", value))
    if key == "phone":
        return bool(re.fullmatch(r"1[3-9]\d{9}", value))
    if key == "email":
        return bool(_EMAIL.fullmatch(value))
    if key == "id_number":
        return bool(re.fullmatch(r"\d{17}[\dXx]", value))
    if key == "gender":
        return value in {"男", "女", "Male", "Female", "male", "female"}
    if key in {"birth_date", "graduation_date", "school_start_date"}:
        return bool(re.fullmatch(r"(?:19|20)\d{2}[-./年](?:0?[1-9]|1[0-2])(?:[-./月](?:[0-2]?\d|3[01])日?)?", value))
    if key == "university":
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z·（）()\s]{2,60}(?:大学|学院|学校|University|College)", value, re.I))
    if key == "education":
        return value in {"高中", "中专", "大专", "专科", "本科", "硕士", "硕士研究生", "博士", "博士研究生"}
    if key == "degree":
        return value in {"学士", "硕士", "博士", "无", "学士学位", "硕士学位", "博士学位"}
    if key == "work_years":
        return bool(re.fullmatch(r"\d{1,2}(?:\.\d)?年", value))
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value))


def extract_resume_candidates(text: str) -> dict:
    """Return reviewable candidates; never save them or send resume text online."""
    if not isinstance(text, str):
        raise TypeError("简历内容必须是文字")
    source = unicodedata.normalize("NFKC", text[:100_000]).replace("\r", "\n")
    lines = [re.sub(r"[\t\u00a0]+", " ", line).strip() for line in source.splitlines()]
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    safe_lines = [line for line in lines if line and not _UNSAFE_CONTEXT.search(line)]
    for line in safe_lines:
        markers = list(_MARKER.finditer(line))
        if not markers:
            for label in _ALL_LABELS:
                match = re.match(r"^(" + re.escape(label) + r")\s+", line, re.I)
                if match:
                    markers = [match]
                    break
        for index, match in enumerate(markers):
            key = next((name for name, labels in LABELS.items()
                        if match.group(1).lower() in {label.lower() for label in labels}), None)
            if key is None:
                continue
            end = markers[index + 1].start() if index + 1 < len(markers) else len(line)
            value = line[match.end():end].split("|", 1)[0].strip(" ：:;,，；。")
            if key == "phone":
                mobile = _MOBILE.search(value)
                value = mobile.group(1) if mobile else ""
            elif key == "email":
                email = _EMAIL.search(value)
                value = email.group() if email else ""
            if _plausible(key, value):
                found[key].append((value, "简历标签：" + match.group(1)))
    for key, pattern in (("phone", _MOBILE), ("email", _EMAIL)):
        for line in safe_lines:
            for match in pattern.finditer(line):
                value = match.group(1) if key == "phone" else match.group()
                found[key].append((value, "唯一联系方式"))
    education_lines = []
    inside_education = False
    for line in lines:
        if _EDUCATION_HEADING.fullmatch(line):
            inside_education = True
            continue
        if inside_education and _NEXT_HEADING.fullmatch(line):
            break
        if inside_education and line:
            education_lines.append(line)
        if len(education_lines) >= 12:
            break
    if education_lines:
        school_rows = []
        for line in education_lines:
            schools = _UNIVERSITY.findall(line)
            if len(schools) == 1:
                school_rows.append((schools[0], line))
        unique_schools = {school for school, _ in school_rows}
        if len(unique_schools) == 1 and not found["university"]:
            school, row = school_rows[0]
            found["university"].append((school, "教育经历推断，需核对"))
            levels = _LEVEL.findall(row)
            if len(set(levels)) == 1 and not found["education"]:
                found["education"].append((levels[0], "教育经历推断，需核对"))
            after_school = row.split(school, 1)[1]
            major = re.split(r"\s+(?:大专|专科|本科|硕士|博士)|[|｜]", after_school, 1)[0].strip(" ，,;；")
            if not found["major"] and re.fullmatch(r"[\u4e00-\u9fff·]{2,30}", major):
                found["major"].append((major, "教育经历推断，需核对"))
    if not found["full_name"] and lines and re.fullmatch(r"[\u4e00-\u9fff·]{2,4}", lines[0]):
        if any(_MOBILE.search(line) or _EMAIL.search(line) for line in lines[1:8]):
            found["full_name"].append((lines[0], "简历首页候选，需核对"))
    warnings = []
    candidates = []
    for key in PROFILE_FIELDS:
        values = {value: reason for value, reason in found.get(key, [])}
        if len(values) > 1:
            warnings.append(f"{PROFILE_FIELDS[key]}出现多个不同值，未自动选择")
            continue
        if values:
            value, reason = next(iter(values.items()))
            candidates.append({"field": key, "value": value, "evidence": reason,
                               "default_selected": key != "id_number" and "需核对" not in reason})
    if not candidates:
        warnings.append("未识别到可靠字段；扫描版 PDF 可能需要先做 OCR")
    return {"candidates": candidates, "warnings": warnings}

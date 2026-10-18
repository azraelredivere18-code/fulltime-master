"""User-directed official career-site form helper; it never submits a form."""

from __future__ import annotations

import ctypes
import ipaddress
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


PROFILE_FIELDS = {
    "full_name": "姓名", "phone": "手机号", "email": "电子邮箱",
    "id_number": "身份证号", "gender": "性别", "birth_date": "出生日期",
    "ethnicity": "民族", "political_status": "政治面貌",
    "household_registration": "户籍所在地", "current_city": "现居城市",
    "address": "通信地址", "university": "毕业院校", "degree": "学位",
    "education": "最高学历", "major": "专业", "graduation_date": "毕业日期",
    "school_start_date": "入学日期", "work_years": "工作年限",
    "self_intro": "自我介绍", "skills": "技能特长",
}


def normalize_official_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or len(url) > 4096 or
            any(ord(ch) < 32 or ch.isspace() for ch in url)):
        raise ValueError("请填写完整的 HTTPS 企业招聘网址")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("网址端口无效") from exc
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("请填写企业招聘网站，不要填写本机网址")
    host = parsed.hostname or ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".local", ".internal", ".localhost")):
            raise ValueError("请填写公开的企业招聘网站域名")
    else:
        if not address.is_global:
            raise ValueError("请填写公开的企业招聘网站网址")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))


_JOB_ID_KEYS = {"id", "jobid", "job_id", "positionid", "position_id",
                "requisitionid", "requisition_id", "jobcode", "job_code"}


def safe_record_url(value: str) -> str:
    """Keep job identity while dropping session and tracking parameters."""
    import re

    parsed = urlsplit(normalize_official_url(value))

    def job_query(query: str) -> str:
        pairs = []
        for key, item in parse_qsl(query, keep_blank_values=False):
            if key.lower() in _JOB_ID_KEYS and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", item):
                pairs.append((key, item))
        return urlencode(pairs)

    fragment = ""
    if parsed.fragment.startswith("/"):
        route = urlsplit(parsed.fragment)
        if (re.fullmatch(r"/[A-Za-z0-9_./-]{1,255}", route.path) and
                re.search(r"(?:^|/)(?:job|jobs|position|positions|requisition|apply)(?:/|$)",
                          route.path, re.I)):
            fragment = route.path
            safe_query = job_query(route.query)
            if safe_query:
                fragment += "?" + safe_query
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       job_query(parsed.query), fragment))


def clean_profile(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("资料必须是字段列表")
    unknown = set(value) - set(PROFILE_FIELDS)
    if unknown:
        raise ValueError("资料包含不支持的字段")
    result = {}
    for key in PROFILE_FIELDS:
        item = value.get(key, "")
        if not isinstance(item, str):
            raise TypeError(f"{key} 必须填写文字")
        item = item.strip()
        if len(item) > (2000 if key in {"self_intro", "skills"} else 200):
            raise ValueError(f"{PROFILE_FIELDS[key]}内容过长")
        result[key] = item
    return result


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("个人资料加密仅支持 Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _DataBlob(len(data), source_buffer)
    output = _DataBlob()
    name = "CryptUnprotectData" if decrypt else "CryptProtectData"
    method = getattr(crypt32, name)
    method.restype = wintypes.BOOL
    method.argtypes = ([ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                        ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
                       if decrypt else
                       [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR,
                        ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)])
    arguments = (ctypes.byref(source), None, None, None, None, 1,
                 ctypes.byref(output))
    if not method(*arguments):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


class OfficialProfileStore:
    """DPAPI protection binds saved profile data to the current Windows user."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, str]:
        if not self.path.is_file():
            return clean_profile({})
        try:
            raw = json.loads(_dpapi(self.path.read_bytes(), decrypt=True).decode("utf-8"))
            return clean_profile(raw)
        except Exception as exc:
            raise RuntimeError("无法读取已加密资料；请在当前 Windows 账号下重试") from exc

    def save(self, profile: Mapping[str, Any]) -> None:
        payload = json.dumps(clean_profile(profile), ensure_ascii=False).encode("utf-8")
        encrypted = _dpapi(payload, decrypt=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        os.replace(temporary, self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


_FORM_SCRIPT = r"""(() => {
  const profile = PROFILE_JSON;
  const aliases = {
    full_name:['姓名','真实姓名','中文姓名','应聘人姓名','full name'],
    phone:['手机号','手机号码','联系电话','移动电话','mobile phone','phone number'],
    email:['电子邮箱','邮箱地址','电子邮件','email','e-mail'],
    id_number:['身份证号','身份证号码','证件号码','身份证'],
    gender:['性别','gender'], birth_date:['出生日期','出生年月','生日','date of birth'],
    ethnicity:['民族'], political_status:['政治面貌'],
    household_registration:['户籍所在地','户籍地址','户籍'],
    current_city:['现居城市','现居地','当前城市'],
    address:['通信地址','联系地址','现居住址'],
    university:['毕业院校','就读学校','学校名称','院校名称','university'],
    degree:['学位','degree'], education:['最高学历','学历','education level'],
    major:['所学专业','专业名称','专业','major'],
    graduation_date:['毕业日期','毕业时间','毕业年月','graduation date'],
    school_start_date:['入学日期','入学时间'],
    work_years:['工作年限','工作经验年限'],
    self_intro:['自我介绍','个人介绍','自我评价','个人总结'],
    skills:['技能特长','个人技能','专业技能']
  };
  const clean = value => String(value || '').toLowerCase().replace(/^请(?:输入|填写|选择)/,'')
    .replace(/[\s:：*＊（()）【】\[\]必填]/g,'');
  const visible = el => !!(el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden' && !el.disabled && !el.readOnly);
  const fieldInfo = el => {
    const labelled = el.labels ? Array.from(el.labels).map(x => x.innerText || '').join(' ') : '';
    const group = el.closest('.ant-form-item,.el-form-item,.form-group,.form-item,tr,li');
    const groupLabel = group && group.querySelector('label,.ant-form-item-label,.el-form-item__label,th');
    const displayed = [labelled,el.getAttribute('aria-label'),groupLabel && groupLabel.innerText,
      el.placeholder].filter(Boolean);
    return {labels:displayed.map(clean),machine:[el.name,el.id].filter(Boolean).map(clean),
      display:displayed[0] || el.name || el.id || '', context:group && group.innerText || ''};
  };
  if (location.protocol !== 'https:' || location.hostname !== TRUSTED_HOST)
    return {state:'wrong_site', filled:[], available:[], skipped:[], frames:0};
  const unsafe = (el,info) => /password|captcha|verify|验证码|密码|银行卡|银行账号|短信|otp|one.time|紧急联系人|紧急联络|家属|家庭成员|推荐人|父母|配偶|子女|监护人|开户/i.test(
    [el.name,el.id,el.autocomplete,el.placeholder,info.display,info.context].join(' '));
  const controls = Array.from(document.querySelectorAll('input,textarea,select'))
    .filter(el => visible(el) &&
      (el.matches('textarea,select') || ['text','tel','email','date','number','search'].includes(el.type)))
    .map(el => ({el,info:fieldInfo(el)}));
  const signature=JSON.stringify([location.href || '',controls.map(({el,info}) =>
    [el.tagName,el.type,el.name,el.id,info.labels,info.context])]);
  let hash=2166136261;
  for (let i=0;i<signature.length;i++) hash=Math.imul(hash ^ signature.charCodeAt(i),16777619);
  const fingerprint=(hash>>>0).toString(16);
  if (EXPECTED_FINGERPRINT && fingerprint !== EXPECTED_FINGERPRINT)
    return {state:'stale_preview',reason:'网页表单已变化，请重新识别后填写'};
  const candidates=controls.filter(({el,info}) => !unsafe(el,info));
  const filled=[], available=[], skipped=[], targets=[];
  for (const [key,value] of Object.entries(profile)) {
    if (!value) continue;
    const names=aliases[key] || [];
    const matches=candidates.filter(({info}) => (info.labels.length ? info.labels : info.machine)
      .some(text => [...names,key].some(name => text === clean(name))));
    if (matches.length !== 1) { skipped.push({field:key,reason:matches.length?'字段不唯一':'未找到字段'}); continue; }
    const {el,info}=matches[0];
    if (String(el.value || '').trim()) { skipped.push({field:key,reason:'已有内容'}); continue; }
    let selected=value;
    if (FILL_MODE && el.tagName === 'SELECT') {
      const option=Array.from(el.options).find(opt => clean(opt.textContent) === clean(value) || clean(opt.value) === clean(value));
      if (!option) { skipped.push({field:key,reason:'未找到对应选项'}); continue; }
      selected=option.value;
    }
    available.push(key);
    targets.push({field:key,label:info.display});
    if (FILL_MODE) {
      const proto=el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype :
        el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      const setter=Object.getOwnPropertyDescriptor(proto,'value').set;
      setter.call(el,selected);
      el.dispatchEvent(new Event('input',{bubbles:true}));
      el.dispatchEvent(new Event('change',{bubbles:true}));
      if (String(el.value) === String(selected)) filled.push(key);
      else skipped.push({field:key,reason:'网页不接受该格式，请手动填写'});
    }
  }
  return {state:'ok',fingerprint,filled,available,targets,skipped,
    frames:document.querySelectorAll('iframe').length};
})()"""


def build_form_script(profile: Mapping[str, Any], trusted_host: str, *, fill: bool,
                      expected_fingerprint: str = "") -> str:
    values = {key: value if fill else True
              for key, value in clean_profile(profile).items() if value}
    return (_FORM_SCRIPT.replace("FILL_MODE", "true" if fill else "false")
            .replace("TRUSTED_HOST", json.dumps(trusted_host, ensure_ascii=True))
            .replace("EXPECTED_FINGERPRINT", json.dumps(expected_fingerprint))
            .replace("PROFILE_JSON", json.dumps(values, ensure_ascii=True)))

"""BOSS browser adapter backed by the app's persistent WebView2 session.

The window is owned by pywebview and has no application JS API. A user can
complete login and challenges in it; job reads use that same browser session.
"""

from __future__ import annotations

import time
import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from salary_codec import readable_salary


CARD_LOCATOR = "css:.card-area .job-card-wrap, .job-card-wrapper"
DETAIL_LOCATOR = "css:.job-detail-section:nth-child(1) .job-sec-text"
CARD_SCRIPT = """(() => {
    const text = (card, selectors) => {
        for (const selector of selectors) {
            const node = card.querySelector(selector);
            const value = node && (node.innerText || node.textContent || '').trim();
            if (value) return value;
        }
        return '';
    };
    const link = card => {
        for (const selector of ['a[href*="/job_detail/"]', 'a[href*="job_detail"]', 'a[href]']) {
            const node = card.querySelector(selector);
            if (node && node.href) return node.href;
        }
        return '';
    };
    return Array.from(document.querySelectorAll('.card-area .job-card-wrap, .job-card-wrapper'))
        .map(card => ({
            title: text(card, ['.job-name', '.job-title', 'h3', 'a.job-name']),
            company: text(card, ['.boss-name', '.company-name', '.company-text h3', '.company-text a', 'h4']),
            salary: text(card, ['.job-salary', '.salary']),
            area: text(card, ['.company-location', '.job-area', '.job-area-wrapper', '.job-address']),
            experience: text(card, ['.tag-list li:first-child', '.job-card-info li:first-child']),
            education: text(card, ['.tag-list li:nth-child(2)', '.job-card-info li:nth-child(2)']),
            employment_type: text(card, ['.job-type', '.job-labels .job-type', '[data-job-type]']),
            hr_title: text(card, ['.boss-info-attr', '.boss-title']),
            activity: text(card, ['.boss-active-time']),
            summary: (card.innerText || card.textContent || '').trim(),
            link: link(card)
        }));
})()"""

DETAIL_METADATA_SCRIPT = """(() => {
    const text = selectors => {
        for (const selector of selectors) {
            const el = document.querySelector(selector);
            const value = el && (el.innerText || el.textContent || '').trim();
            if (value) return value;
        }
        return '';
    };
    return {
        company: text(['.company-info a', '.company-name', '.boss-name']),
        area: text(['.location-address', '.job-location', '.company-location', '.job-area']),
        salary: text(['.job-salary', '.salary']),
        experience: text(['.job-banner .tag-list li:first-child', '.job-info .tag-list li:first-child', '.tag-list li:first-child']),
        education: text(['.job-banner .tag-list li:nth-child(2)', '.job-info .tag-list li:nth-child(2)', '.tag-list li:nth-child(2)']),
        employment_type: text(['.job-type', '.job-labels .job-type', '[data-job-type]'])
    };
})()"""

ADVANCE_RESULTS_SCRIPT = """(() => {
    const visible = el => !!(el && el.getClientRects().length &&
        getComputedStyle(el).visibility !== 'hidden');
    const next = Array.from(document.querySelectorAll(
        '.pagination a, .pagination button, .page-wrap a, .page-wrap button'))
        .filter(el => visible(el) && !el.disabled &&
            !el.classList.contains('disabled') && /下一页/.test(
                (el.innerText || el.textContent || '').trim()));
    if (next.length === 1) { next[0].click(); return 'advanced'; }
    const root = document.scrollingElement || document.documentElement;
    if (root.scrollTop + innerHeight < root.scrollHeight - 30) {
        root.scrollTo(0, root.scrollHeight);
        return 'advanced';
    }
    return 'end';
})()"""

LOGIN_SCRIPT = """(() => {
    const visible = el => !!(el && el.getClientRects().length &&
        getComputedStyle(el).visibility !== 'hidden');
    const login = Array.from(document.querySelectorAll(
        '.header-login-btn, a[href*="/login"], a[href*="passport"]'))
        .filter(visible).some(el => /登录|注册/.test((el.innerText || el.textContent || '').trim()));
    if (login) return 'logged_out';
    if (Array.from(document.querySelectorAll('.nav-figure')).some(visible))
        return 'logged_in';
    const user = Array.from(document.querySelectorAll(
        '.nav-figure, .user-nav, .nav-user, .header-user, header .user-info'))
        .filter(visible).some(el => {
            const value = (el.innerText || el.textContent || '').trim();
            return !!value && !/登录|注册/.test(value);
        });
    return user ? 'logged_in' : 'unknown';
})()"""

START_CHAT_SCRIPT = """(() => {
    const visible = el => !!(el && el.getClientRects().length &&
        getComputedStyle(el).visibility !== 'hidden' && !el.disabled);
    const candidates = Array.from(document.querySelectorAll(
        'button, a, [role="button"]'))
        .filter(el => visible(el) && /^(立即沟通|发起沟通|打招呼)$/.test(
            (el.innerText || el.textContent || '').trim()));
    if (candidates.length !== 1) return {state:'unavailable', count:candidates.length};
    candidates[0].click();
    return {state:'clicked'};
})()"""

CHAT_RESULT_SCRIPT = r"""(() => {
    const visible = el => !!(el && el.getClientRects().length &&
        getComputedStyle(el).visibility !== 'hidden');
    const text = (document.body && document.body.innerText || '').slice(0, 40000);
    if (/安全验证|请完成验证|拖动滑块/.test(text)) return 'verification';
    if (/请登录后使用|登录\/注册/.test(text) &&
        Array.from(document.querySelectorAll('.header-login-btn')).some(visible)) return 'login';
    if (/今日沟通.{0,12}(?:上限|限制)|打招呼.{0,12}(?:上限|次数)/.test(text)) return 'daily_limit';
    if (/已向BOSS发送消息|已打招呼/.test(text)) return 'sent';
    const buttons = Array.from(document.querySelectorAll(
        '.btn-startchat, .btn-start-chat, [class*="startchat"], button, a'))
        .filter(visible);
    if (buttons.some(el => /已沟通|继续沟通/.test((el.innerText || el.textContent || '').trim())))
        return 'sent';
    if (Array.from(document.querySelectorAll('.boss-dialog, .dialog-wrap, .modal')).filter(visible)
        .some(el => /未上传简历|未上传附件简历|请完善简历/.test(el.innerText || ''))) return 'needs_resume';
    if (Array.from(document.querySelectorAll('.boss-dialog, .dialog-wrap, .modal')).filter(visible)
        .some(el => /确认|发送|招呼/.test(el.innerText || ''))) return 'needs_confirmation';
    return 'unknown';
})()"""


def build_resume_upload_script(file: Path) -> str:
    """Build a DOM file-change event for a single selected resume input."""
    mime = "application/pdf" if file.suffix.lower() == ".pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    payload = base64.b64encode(file.read_bytes()).decode("ascii")
    return """(() => {
        const inputs = Array.from(document.querySelectorAll('input[type="file"]'))
            .filter(el => !el.disabled);
        if (inputs.length !== 1) return {state:'ambiguous_input', count:inputs.length};
        const input = inputs[0];
        const label = input.labels && Array.from(input.labels).map(el => el.innerText || '').join(' ');
        const context = [input.name, input.id, input.getAttribute('aria-label'), label,
            input.parentElement && input.parentElement.innerText,
            input.parentElement && input.parentElement.parentElement &&
                input.parentElement.parentElement.innerText].filter(Boolean).join(' ').slice(0,500);
        if (/头像|照片|证件照|营业执照|avatar|photo|logo/i.test(context) ||
            !/简历|附件|resume|curriculum|\\bcv\\b/i.test(context))
            return {state:'not_resume_input'};
        if (input.accept && !/pdf|doc|word/i.test(input.accept))
            return {state:'unsupported_file_type'};
        const binary = atob(PAYLOAD);
        const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
        const file = new File([bytes], NAME, {type:MIME});
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event('change', {bubbles:true}));
        return {state:'submitted_to_form'};
    })()""".replace("MIME", json.dumps(mime)).replace(
        "NAME", json.dumps(file.name, ensure_ascii=False)).replace("PAYLOAD", json.dumps(payload))


RESUME_RECEIPT_SCRIPT = r"""(() => {
  const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  return Array.from(document.querySelectorAll('span,div,p,strong,li,[role=status],[role=alert]'))
    .filter(e=>visible(e)&&e.children.length===0)
    .map(e=>(e.innerText||e.textContent||'').trim())
    .filter(t=>/^(?:上传成功|简历上传成功|附件简历已上传|已上传附件简历|上传完成)[！!。]?$/.test(t))
    .slice(0,20);
})()"""


def new_resume_receipt(before: object, after: object) -> bool:
    """An old success message on the page cannot confirm a new upload."""
    if not isinstance(before, list) or not isinstance(after, list):
        return False
    return any(isinstance(item, str) and after.count(item) > before.count(item)
               for item in after)


def _boss_url(url: str, *, detail: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"zhipin.com", "www.zhipin.com"}:
        return False
    return parsed.path.startswith("/job_detail/") if detail else True


class EmbeddedBossPage:
    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def _current_window(self) -> Any:
        window = self.manager.current_browser_window("BOSS直聘")
        if window is None:
            raise RuntimeError("内置浏览器已关闭，请点击“内置浏览器”重新打开")
        return window

    @property
    def url(self) -> str:
        return str(self._current_window().get_current_url() or "")

    def get(self, url: str) -> bool:
        if not _boss_url(url):
            raise ValueError("内置浏览器只能导航至 BOSS直聘")
        window = self.manager.open_browser_window(platform="BOSS直聘")
        window.load_url(url)
        if not window.events.loaded.wait(30):
            raise RuntimeError("内置浏览器加载超时，请查看浏览器窗口")
        return True

    def eles(self, locator: str, timeout: float = 0) -> list[dict[str, str]]:
        if locator != CARD_LOCATOR:
            raise ValueError("不支持的职位列表选择器")
        result = self._current_window().run_js(CARD_SCRIPT)
        if not isinstance(result, list) or any(not isinstance(card, dict) for card in result):
            raise RuntimeError("内置浏览器没有返回可读取的职位列表")
        return result

    def login_state(self) -> str:
        """Report visible login evidence without touching credentials or challenges."""
        current = self.url
        if not _boss_url(current):
            return "unknown"
        parsed = urlparse(current)
        if "verify" in parsed.path or "security" in parsed.path:
            return "verification"
        if "login" in parsed.path or "/passport/" in parsed.path:
            return "logged_out"
        result = self._current_window().run_js(LOGIN_SCRIPT)
        return result if result in {"logged_in", "logged_out", "unknown"} else "unknown"

    def diagnostics(self) -> dict[str, Any]:
        """Capture selector evidence without page text, account data or cookies."""
        report = self._current_window().run_js("""(() => {
          const count = selector => document.querySelectorAll(selector).length;
          const first = document.querySelector('.card-area .job-card-wrap, .job-card-wrapper');
          const link = first && first.querySelector('a[href*="/job_detail/"]');
          const salary = first && first.querySelector('.job-salary, .salary');
          const codepoints = salary ? Array.from((salary.textContent || '').trim())
            .slice(0, 20).map(ch => ch.codePointAt(0).toString(16)) : [];
          const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'))
            .filter(el => el.getClientRects().length &&
              /^(立即沟通|发起沟通|打招呼)$/.test((el.innerText || '').trim()));
          return {path:location.pathname, selectors:{
            cards:count('.card-area .job-card-wrap, .job-card-wrapper'),
            login:count('.header-login-btn'), user:count('.nav-figure, .user-nav, .nav-user'),
            chatButtons:buttons.length},
            firstJobPath:link ? new URL(link.href).pathname : '', salaryCodepoints:codepoints,
            salaryFont:salary ? getComputedStyle(salary).fontFamily : ''};
        })()""")
        if not isinstance(report, dict):
            raise RuntimeError("页面未返回诊断数据")
        report["loginState"] = self.login_state()
        return report

    def advance_search_results(self) -> bool:
        """Read another visible batch before declaring a search group exhausted."""
        result = self._current_window().run_js(ADVANCE_RESULTS_SCRIPT)
        return result == "advanced"

    def check_application_result(self, link: str) -> str:
        """Observe the current detail page after a pending site confirmation."""
        if not _boss_url(link, detail=True):
            raise ValueError("职位详情链接无效")
        current = urlparse(self.url)
        expected = urlparse(link)
        if current.hostname not in {"www.zhipin.com", "zhipin.com"}:
            return "away"
        if "verify" in current.path or "passport" in current.path:
            return "verification"
        if current.path != expected.path:
            return "away"
        observed = self._current_window().run_js(CHAT_RESULT_SCRIPT)
        return observed if observed in {
            "sent", "verification", "login", "daily_limit", "needs_confirmation", "unknown"
        } else "unknown"

    def apply_job(self, link: str) -> dict[str, Any]:
        """Click one visible direct-chat button; only visible success counts as sent."""
        if not _boss_url(link, detail=True):
            raise ValueError("职位详情链接无效")
        search_url = self.url
        if not _boss_url(search_url):
            return {"state": "unavailable", "reason": "内置浏览器不在 BOSS直聘", "clicked": False}
        restore_search = True
        try:
            self.get(link)
            state = self.login_state()
            if state != "logged_in":
                restore_search = state not in {"logged_out", "verification"}
                return {"state": state, "reason": "请在内置浏览器手动登录或完成验证", "clicked": False}
            result = self._current_window().run_js(START_CHAT_SCRIPT)
            if not isinstance(result, dict) or result.get("state") != "clicked":
                return {"state": "unavailable", "reason": "未找到唯一的“立即沟通”按钮", "clicked": False}
            for _ in range(12):
                observed = self._current_window().run_js(CHAT_RESULT_SCRIPT)
                if observed in {"sent", "verification", "login", "daily_limit", "needs_confirmation", "needs_resume"}:
                    restore_search = observed not in {"verification", "login", "needs_confirmation", "needs_resume"}
                    return {"state": str(observed), "reason": "页面可见状态：" + str(observed), "clicked": True}
                time.sleep(0.5)
            restore_search = False
            return {"state": "unknown", "reason": "已点击沟通按钮，但未观察到发送成功回执", "clicked": True}
        finally:
            if restore_search and _boss_url(search_url) and search_url != link:
                try:
                    self.get(search_url)
                except Exception:
                    pass

    def upload_resume_file(self, path: str) -> dict[str, str]:
        """Offer a local file to the site's resume form; require visible confirmation."""
        file = Path(path)
        if not file.is_file() or file.suffix.lower() not in {".pdf", ".docx"}:
            return {"state": "invalid_file", "reason": "请选择存在的 PDF 或 DOCX 简历"}
        if file.stat().st_size > 8 * 1024 * 1024:
            return {"state": "invalid_file", "reason": "简历超过本程序支持的 8 MB"}
        if self.login_state() != "logged_in":
            return {"state": "login", "reason": "请先在内置浏览器手动登录"}
        if "resume" not in urlparse(self.url).path.lower():
            return {"state": "wrong_page", "reason": "请先在内置浏览器打开 BOSS 的附件简历管理页"}
        before = self._current_window().run_js(RESUME_RECEIPT_SCRIPT)
        outcome = self._current_window().run_js(build_resume_upload_script(file))
        if not isinstance(outcome, dict) or outcome.get("state") != "submitted_to_form":
            return {"state": "unavailable", "reason": "未找到唯一的简历文件输入框"}
        for _ in range(12):
            after = self._current_window().run_js(RESUME_RECEIPT_SCRIPT)
            if new_resume_receipt(before, after):
                return {"state": "confirmed", "reason": "网页新增了简历上传成功提示"}
            time.sleep(0.5)
        return {"state": "unverified", "reason": "文件已交给页面，但未看到上传成功提示，请在 BOSS 页面确认"}

    def new_tab(self, url: str, background: bool = True) -> "EmbeddedDetailTab":
        if not _boss_url(url, detail=True):
            raise ValueError("职位详情链接无效")
        return EmbeddedDetailTab(self.manager.open_detail_window(url))

    def quit(self, **kwargs: Any) -> None:
        self.manager.close_browser_window("BOSS直聘")


class EmbeddedDetailTab:
    def __init__(self, window: Any) -> None:
        self.window = window

    @property
    def url(self) -> str:
        return str(self.window.get_current_url() or "")

    def ele(self, locator: str, timeout: float = 0) -> "EmbeddedTextElement | None":
        if locator != DETAIL_LOCATOR:
            raise ValueError("不支持的职位详情选择器")
        text = self.window.run_js(
            "(() => { const element = document.querySelector("
            "'.job-detail-section:nth-child(1) .job-sec-text, .job-detail-section .job-sec-text'); "
            "return element ? (element.innerText || element.textContent || '').trim() : ''; })()"
        )
        return EmbeddedTextElement(str(text)) if text else None

    def metadata(self) -> dict[str, str]:
        result = self.window.run_js(DETAIL_METADATA_SCRIPT)
        if not isinstance(result, dict):
            return {}
        fields = {key: str(result.get(key) or "").strip()
                  for key in ("company", "area", "salary", "experience", "education", "employment_type")}
        fields["salary"] = readable_salary(fields["salary"])
        return fields

    def close(self) -> None:
        self.window.destroy()


class EmbeddedTextElement:
    def __init__(self, text: str) -> None:
        self.text = text

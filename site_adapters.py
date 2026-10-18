"""Conservative browser adapters for supported recruitment sites.

The selectors were recovered from the supplied 6.6.2 binary. All reads and
actions occur in the user's visible WebView2 session. A click is never a receipt.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from embedded_browser import EmbeddedTextElement, build_resume_upload_script


@dataclass(frozen=True)
class Site:
    name: str
    home: str
    hosts: frozenset[str]
    search_path: str
    cards: str
    title: tuple[str, ...]
    company: tuple[str, ...]
    area: tuple[str, ...]
    salary: tuple[str, ...]
    experience: tuple[str, ...]
    education: tuple[str, ...]
    detail: str
    apply: str


SITES = {
    "智联招聘": Site(
        "智联招聘", "https://www.zhaopin.com/sou/jl530", frozenset({"www.zhaopin.com", "zhaopin.com", "passport.zhaopin.com"}),
        "/sou/", ".job-card, .joblist-box__item",
        (".vue-clamp__text", ".job-card__job-name", ".job-card__name", ".jobinfo__name", "a[href*='/jobdetail/']"),
        (".job-card__company-name", ".companyinfo__name"),
        (".job-card__location span", ".jobinfo__other-info-item:nth-of-type(1) span", ".jobinfo__area"),
        (".job-card__salary", ".jobinfo__salary"),
        (".jobinfo__other-info-item:nth-of-type(2)",),
        (".jobinfo__other-info-item:nth-of-type(3)",),
        ".job-description__content, .describtion-card__detail-content",
        ".a-button.a--bordered.a--filled",
    ),
    "前程无忧": Site(
        "前程无忧", "https://we.51job.com/pc/search", frozenset({"we.51job.com", "www.51job.com", "login.51job.com"}),
        "/pc/search", ".joblist .joblist-item",
        (".joblist-item-left .jname",), (".joblist-item-right .cname",),
        (".joblist-item-left .d.at", ".joblist-item-left .area", ".job_area",
         ".joblist-item-left [class*='area']", ".joblist-item-left [class*='location']"),
        (".joblist-item-left .sal",), (".joblist-item-left .tags span:nth-child(1)",),
        (".joblist-item-left .tags span:nth-child(2)",),
        ".job_msg", ".apply-btn-new",
    ),
    "应届生": Site(
        "应届生", "https://q.yingjiesheng.com/jobs/search/",
        frozenset({"q.yingjiesheng.com", "www.yingjiesheng.com", "my.yingjiesheng.com"}),
        "/jobs/search/", "#list .search-list > div:not(.search-list-pagination)",
        (".left-detail-job", ".job-name", "a[href*='/job']"),
        (".left-detail-company",),
        (".left-detail-area", ".left-tag-item"),
        (".right-salary",),
        (".left-tag-item:nth-of-type(1)",),
        (".left-tag-item:nth-of-type(2)",),
        ".jobinfo div.text", ".delivery-btn",
    ),
    "猎聘": Site(
        "猎聘", "https://www.liepin.com/zhaopin/",
        frozenset({"www.liepin.com", "liepin.com", "passport.liepin.com", "safe.liepin.com"}),
        "/zhaopin/", ".job-list-box .jobCardPcContainer[style*='display: flex'], .job-list-box .jobCardPcContainer",
        (".jobDetailBox .ellipsis-1:first-child", ".job-title", "a[href*='/job/']"),
        (".jobDetailBox div[data-nick=job-detail-company-info] span.ellipsis-1", ".company-name"),
        (".job-area", ".job-dq-box", ".job-detail-box .ellipsis-1"),
        (".job-salary", ".job-salary-box"),
        (".job-labels-box span:nth-child(1)", ".job-info-tag span:nth-child(1)"),
        (".job-labels-box span:nth-child(2)", ".job-info-tag span:nth-child(2)"),
        ".job-intro-container dd", ".apply-box .btn-main",
    ),
    "拉勾": Site(
        "拉勾", "https://www.lagou.com/wn/jobs?fromSearch=true",
        frozenset({"www.lagou.com", "lagou.com", "x.lagou.com", "passport.lagou.com"}),
        "/wn/jobs", "#jobList .item__10RTO, #jobList [class*='item__']",
        (".p-top__1F7CL a", "[class*='p-top'] a", "a[href*='/jobs/']"),
        (".company-name__2-SjF a", "[class*='company-name'] a"),
        (".position-address", "[class*='city']", "[class*='address']"),
        (".money", "[class*='salary']", "[class*='money']"),
        ("[class*='job-detail'] span:nth-child(1)", "[class*='label'] span:nth-child(1)"),
        ("[class*='job-detail'] span:nth-child(2)", "[class*='label'] span:nth-child(2)"),
        "#job_detail .job-detail", ".resume-deliver, .btn_apply",
    ),
    "牛客网": Site(
        "牛客网", "https://www.nowcoder.com/jobs/fulltime/center",
        frozenset({"www.nowcoder.com", "nowcoder.com"}),
        "/jobs/", ".job-card-item",
        (".job-name",), (".company-name",),
        (".job-info-item", ".job-city"), (".job-salary",),
        (".job-info-item:nth-of-type(2)",), (".job-info-item:nth-of-type(3)",),
        ".job-detail-word", "button.el-button--primary.el-button--xl",
    ),
}

DETAIL_METADATA_SELECTORS = {
    "智联招聘": {
        "company": (".companyinfo__name", ".job-card__company-name"),
        "area": (".jobinfo__other-info-item:nth-of-type(1) span", ".job-card__location span"),
        "salary": (".jobinfo__salary", ".job-card__salary"),
        "experience": (".jobinfo__other-info-item:nth-of-type(2)",),
        "education": (".jobinfo__other-info-item:nth-of-type(3)",),
        "employment_type": (".job-type", "[data-job-type]"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
    "前程无忧": {
        "company": (".joblist-item-right .cname", ".company-name", ".com-name"),
        "area": (".job_area", ".joblist-item-left .area", ".job-location"),
        "salary": (".joblist-item-left .sal", ".job-salary", ".job_sal"),
        "experience": ("[data-field='jobYear']", ".job-year"),
        "education": ("[data-field='jobDegree']", ".job-degree"),
        "employment_type": ("[data-field='jobType']", ".job-type"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
    "应届生": {
        "company": (".left-detail-company",),
        "area": (".left-detail-area", ".job-area"),
        "salary": (".right-salary",),
        "experience": (".job-year",),
        "education": (".job-degree",),
        "employment_type": (".job-type", "[data-job-type]"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
    "猎聘": {
        "company": (".company-info-box .company-name", "[data-nick='job-detail-company-info'] .ellipsis-1"),
        "area": (".job-info-box .job-dq-box", ".job-area"),
        "salary": (".job-title-box .job-salary", ".job-salary"),
        "experience": (".job-info-box .job-labels-box span:nth-child(1)",),
        "education": (".job-info-box .job-labels-box span:nth-child(2)",),
        "employment_type": (".job-type", "[data-job-type]"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
    "拉勾": {
        "company": ("[class*='company-name']", ".company-name"),
        "area": (".job_request .area", "[class*='position-address']"),
        "salary": (".job_request .salary", "[class*='salary']"),
        "experience": (".job_request .experience", "[class*='experience']"),
        "education": (".job_request .education", "[class*='education']"),
        "employment_type": (".job-type", "[data-job-type]"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
    "牛客网": {
        "company": (".company-name", ".company-info"),
        "area": (".job-info-item", ".job-city"),
        "salary": (".job-salary", "[class*='salary']"),
        "experience": (".job-exp",),
        "education": (".job-edu",),
        "employment_type": (".job-type", "[data-job-type]"),
        "recruitment_track": (".recruitment-track", "[data-recruitment-type]"),
    },
}


def valid_site_url(site: Site, url: str, *, detail: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in site.hosts or any(c in url for c in "'\"< >"):
        return False
    if detail:
        if site.name == "前程无忧":
            return "/job/" in parsed.path or "/jobdetail/" in parsed.path
        if site.name == "应届生":
            return "/job" in parsed.path
        if site.name == "猎聘":
            return parsed.path.startswith(("/job/", "/a/"))
        if site.name == "拉勾":
            return parsed.path.startswith("/jobs/") and parsed.path != "/jobs/"
        if site.name == "牛客网":
            return parsed.path.startswith("/jobs/detail/")
        return "/jobdetail/" in parsed.path or "/job_detail/" in parsed.path
    return True


def _js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class EmbeddedSitePage:
    def __init__(self, manager: Any, site: Site) -> None:
        self.manager, self.site = manager, site

    def _window(self):
        window = self.manager.current_browser_window()
        if window is None:
            raise RuntimeError("内置浏览器已关闭，请先打开并手动登录")
        return window

    @property
    def url(self) -> str:
        return str(self._window().get_current_url() or "")

    def get(self, url: str) -> bool:
        if not valid_site_url(self.site, url):
            raise ValueError("浏览器链接不属于当前招聘网站")
        window = self.manager.open_browser_window(initial_url=url)
        if window.get_current_url() != url:
            window.load_url(url)
        if not window.events.loaded.wait(30):
            raise RuntimeError("网页加载超时，请查看内置浏览器")
        return True

    def login_state(self) -> str:
        current = urlparse(self.url)
        if current.hostname not in self.site.hosts:
            return "unknown"
        if current.hostname == "safe.liepin.com":
            return "verification"
        if any(word in current.path.lower() for word in ("verify", "security", "captcha")):
            return "verification"
        if current.hostname in {"passport.zhaopin.com", "login.51job.com", "passport.liepin.com", "passport.lagou.com"} or "login" in current.path.lower():
            return "logged_out"
        if self.site.name == "牛客网":
            state = self._window().run_js("""(() => {
              const header=document.querySelector('header');
              if(!header)return 'unknown';
              const visible=e=>!!(e&&e.getClientRects().length);
              if(Array.from(header.querySelectorAll('.loginRegisterBtn')).some(visible))return 'logged_out';
              if(Array.from(header.querySelectorAll('.header-user,.user-info,.user-avatar,.user-name,[class*=avatar]')).some(visible))return 'logged_in';
              return 'unknown';
            })()""")
            return state if state in {"logged_in", "logged_out"} else "unknown"
        script = """(() => {
          const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          const text=e=>(e.innerText||e.textContent||'').trim();
          const body=(document.body&&document.body.innerText||'').slice(0,12000);
          if(/安全验证|访问验证|您的访问被阻断|正在验证连接安全性|为了更好的访问体验，请进行验证/.test(body)) return 'verification';
          if(/应届生求职登录/.test(body)) return 'logged_out';
          const login=Array.from(document.querySelectorAll(SEL)).filter(visible)
            .some(e=>/登录|注册/.test(text(e)));
          if(login) return 'logged_out';
          const user=Array.from(document.querySelectorAll('.user-info,.user-center,.user-avatar,.personal-center,.nav-user,.home-header__right,.right-menu,.head-nav-right,.user-name,.user-menu,.header-avatar'))
            .filter(visible).some(e=>!!text(e)&&!/登录|注册/.test(text(e)));
          return user?'logged_in':'unknown';
        })()""".replace("SEL", _js(
            ".home-header__c-no-login, a[href*='login']" if self.site.name == "智联招聘"
            else ".head-nav-right .login-text, .head-nav-right a[href*='login']" if self.site.name == "应届生"
            else "a[href*='login'],.login-btn" if self.site.name in {"猎聘", "拉勾"}
            else ".right-menu .login, a[href*='login']"))
        result = self._window().run_js(script)
        return result if result in {"logged_in", "logged_out", "verification"} else "unknown"

    def navigate_search(self, keyword: str, city: str, city_code: str,
                        employment_type: str = "full_time",
                        recruitment_track: str = "all") -> bool:
        if self.site.name == "牛客网":
            url = ("https://www.nowcoder.com/jobs/school/jobs" if recruitment_track == "campus"
                   else "https://www.nowcoder.com/jobs/intern/center" if employment_type == "internship"
                   else "https://www.nowcoder.com/jobs/fulltime/center")
            self.get(url)
            result = self._window().run_js("""(() => {
              const input=document.querySelector('.input-search-filter .el-input__inner');
              if(!input||!input.getClientRects().length)return false;
              input.focus();
              Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,KEYWORD);
              input.dispatchEvent(new Event('input',{bubbles:true}));
              input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
              return true;
            })()""".replace("KEYWORD", _js(keyword)))
            if result is not True:
                raise RuntimeError("牛客职位搜索框未找到；请在页面诊断中检查网站更新")
            return True
        if self.site.name == "猎聘":
            return self.get(self.site.home + "?key=" + quote(keyword) + "&dqs=" + quote(city_code))
        if self.site.name == "拉勾":
            return self.get(self.site.home + "&kd=" + quote(keyword) + "&city=" + quote(city))
        if self.site.name == "前程无忧":
            return self.get(self.site.home + "?jobArea=" + quote(city_code) + "&keyword=" + quote(keyword))
        if self.site.name == "应届生":
            return self.get(self.site.home + "?jobarea=" + quote(city_code) + "&keyword=" + quote(keyword))
        # The original 智联 city table has province labels, not URL codes.
        self.get(self.site.home)
        result = self._window().run_js("""(() => {
          let input=document.querySelector('.s-region__search input');
          if(!input||!input.getClientRects().length){
            const opener=document.querySelector('.s-region__choose,.s-region__text,.s-region');
            if(opener)opener.click();
            input=document.querySelector('.s-region__search input');
          }
          if(!input||!input.getClientRects().length) return 'city_input_missing';
          input.focus();
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,CITY);
          input.dispatchEvent(new Event('input',{bubbles:true}));
          return 'city_input_ready';
        })()""".replace("CITY", _js(city)))
        if result != "city_input_ready":
            raise RuntimeError("智联城市选择控件未找到；请在浏览器手动选择城市后重试")
        time.sleep(0.4)
        result = self._window().run_js("""(() => {
          const city=CITY;
          const visible=e=>!!(e&&e.getClientRects().length);
          const matches=Array.from(document.querySelectorAll('.s-region__list li,.s-region__result li,.s-region__city li'))
            .filter(e=>visible(e)&&(e.innerText||'').trim()===city);
          if(matches.length!==1) return 'city_ambiguous';
          matches[0].click(); return 'city_selected';
        })()""".replace("CITY", _js(city)))
        if result != "city_selected":
            raise RuntimeError("智联未找到唯一的目标城市；请在浏览器手动选择城市后重试")
        time.sleep(0.5)
        result = self._window().run_js("""(() => {
          const input=document.querySelector('.query-sug__input,.query-search__content-input');
          if(!input) return 'keyword_input_missing';
          input.focus();
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,KEYWORD);
          input.dispatchEvent(new Event('input',{bubbles:true}));
          input.dispatchEvent(new Event('change',{bubbles:true}));
          input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
          return 'search_requested';
        })()""".replace("KEYWORD", _js(keyword)))
        if result != "search_requested":
            raise RuntimeError("智联关键词输入框未找到；请检查当前网页")
        return True

    def eles(self, locator: str, timeout: float = 0) -> list[dict[str, str]]:
        if locator != "css:" + self.site.cards:
            raise ValueError("不支持的职位卡片选择器")
        selectors = {k: getattr(self.site, k) for k in
                     ("title", "company", "area", "salary", "experience", "education")}
        script = """(() => {
          const pick=(card,sels)=>{for(const s of sels){const e=card.querySelector(s);
            const t=e&&(e.innerText||e.textContent||'').trim();if(t)return t;}return '';};
          return Array.from(document.querySelectorAll(CARDS)).map(card=>{
            const a=Array.from(card.querySelectorAll('a[href]')).find(a=>/jobdetail|job_detail|\\/job\\/|\\/jobs\\/|\\/a\\//.test(a.href));
            const kind=pick(card,['.job-type','[data-job-type]','[class*=job-type]']);
            const track=pick(card,['.recruitment-track','[data-recruitment-type]']);
            return {title:pick(card,SEL.title),company:pick(card,SEL.company),
              area:pick(card,SEL.area),salary:pick(card,SEL.salary),
              experience:pick(card,SEL.experience),education:pick(card,SEL.education),
              employment_type:kind,recruitment_track:track,
              hr_title:'',activity:'',summary:(card.innerText||'').trim(),link:a?a.href:''};
          });
        })()""".replace("CARDS", _js(self.site.cards)).replace("SEL", _js(selectors)).replace("SITE", _js(self.site.name))
        result = self._window().run_js(script)
        if not isinstance(result, list) or any(not isinstance(x, dict) for x in result):
            raise RuntimeError("网站没有返回可读取的职位卡片")
        return result

    def diagnostics(self) -> dict[str, Any]:
        """Collect site-control structure without names, resume files or page text."""
        script = """(() => {
          const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          const count=s=>Array.from(document.querySelectorAll(s)).filter(visible).length;
          const first=Array.from(document.querySelectorAll(CARDS)).filter(visible)[0];
          const selectors=SEL;
          const fields={};
          for(const [name,options] of Object.entries(selectors))
            fields[name]=options.filter(s=>first&&first.querySelector(s)).slice(0,5);
          const detailLink=first&&Array.from(first.querySelectorAll('a[href]'))
            .find(a=>/jobdetail|job_detail|\\/job\\/|\\/jobs\\/|\\/a\\//.test(a.href));
          const buttons=Array.from(document.querySelectorAll('button,a')).filter(visible)
            .map(e=>({text:(e.innerText||'').trim(),selector:e.tagName.toLowerCase()+
              (e.className&&typeof e.className==='string'?'.'+e.className.trim().split(/\\s+/).slice(0,3).join('.'): '')}))
            .filter(x=>/^(立即投递|立即申请|申请职位|投递简历|投简历|确认投递|投递|发送|已投递|已申请|上传简历|选择简历|我的简历|登录|注册|下一页)$/.test(x.text))
            .slice(0,20);
          const dialogs=Array.from(document.querySelectorAll('.a-modal,.deliver-greeting-modal,.el-dialog,.operate-popup,.ant-modal,.position-modal,[role=dialog]'))
            .filter(visible).map(d=>({
              tag:d.tagName.toLowerCase(),className:typeof d.className==='string'?d.className.slice(0,100):'',
              resumePrompt:/请选择.*简历|选择简历/.test(d.innerText||''),
              success:/投递成功|申请成功/.test(d.innerText||''),
              enterpriseQuestions:/需补充企业要求的信息/.test(d.innerText||''),
              resumeChoices:d.querySelectorAll('input[type=radio],[role=radio],.resume-item,.a-attachment-select__item').length,
              selectedRadio:d.querySelectorAll('input[type=radio]:checked,[aria-checked=true],.resume-item.active,.resume-item.selected,.a-attachment-select__item--active').length,
              actionButtons:Array.from(d.querySelectorAll('button')).filter(visible)
                .map(b=>(b.innerText||'').trim()).filter(t=>/^(立即申请|立即投递|投递简历|发送|确认投递|确定|下一步)$/.test(t)).slice(0,8)
            })).slice(0,5);
          const successMarkers=Array.from(document.querySelectorAll('h1,h2,h3,strong,span,div'))
            .filter(e=>visible(e)&&e.children.length===0&&
              /^(投递成功|申请成功|已向对方发送简历和打招呼语)$/.test((e.innerText||'').trim())).length;
          const url=new URL(location.href);
          return {host:url.hostname,path:url.pathname,cardCount:count(CARDS),
            applyButtonCount:count(APPLY),detailCount:count(DETAIL),
            fields:fields,firstCardLinkHost:detailLink?new URL(detailLink.href).hostname:'',
            firstCardLinkPath:detailLink?new URL(detailLink.href).pathname:'',
            buttons:buttons,dialogs:dialogs,successMarkers:successMarkers,
            keywordInputCount:count('#keywordInput,.query-sug__input,.query-search__content-input'),
            cityInputCount:count('.s-region__search input')};
        })()""".replace("CARDS", _js(self.site.cards)).replace("APPLY", _js(self.site.apply))
        script = script.replace("DETAIL", _js(self.site.detail)).replace("SEL", _js({
            key: getattr(self.site, key) for key in
            ("title", "company", "area", "salary", "experience", "education")
        }))
        result = self._window().run_js(script)
        if not isinstance(result, dict):
            raise RuntimeError("未能读取当前网页控件结构")
        result["platform"] = self.site.name
        result["loginState"] = self.login_state()
        return result

    def advance_search_results(self) -> bool:
        result = self._window().run_js("""(() => {
          const els=Array.from(document.querySelectorAll('a,button,.search-list-pagination .btn-next')).filter(e=>
            e.getClientRects().length&&!e.disabled&&/下一页/.test((e.innerText||'').trim()));
          if(els.length===1){els[0].click();return true;}
          const root=document.scrollingElement||document.documentElement;
          if(root.scrollTop+innerHeight<root.scrollHeight-30){root.scrollTo(0,root.scrollHeight);return true;}
          return false;
        })()""")
        return result is True

    def new_tab(self, url: str, background: bool = True):
        if not valid_site_url(self.site, url, detail=True):
            raise ValueError("职位详情链接无效")
        return SiteDetailTab(self.manager.open_detail_window(url), self.site)

    def check_application_result(self, link: str) -> str:
        if not valid_site_url(self.site, link, detail=True):
            raise ValueError("职位详情链接无效")
        current, expected = urlparse(self.url), urlparse(link)
        if current.hostname not in self.site.hosts:
            return "away"
        if any(x in current.path for x in ("verify", "login", "security")):
            return "verification"
        if current.path != expected.path:
            return "away"
        script = """(() => {
          const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          const text=e=>(e.innerText||e.textContent||'').trim();
          const body=(document.body&&document.body.innerText||'').slice(0,20000);
          if(/安全验证|访问验证|您的访问被阻断|为了更好的访问体验，请进行验证/.test(body))return 'verification';
          if(/今日投递太多|已超过上限|已达到上限/.test(body))return 'daily_limit';
          if(/请完善简历/.test(body))return 'needs_resume';
          if(/需补充企业要求的信息/.test(body))return 'needs_confirmation';
          const buttons=Array.from(document.querySelectorAll(APPLY)).filter(visible);
          if(buttons.filter(b=>/已申请|已投递|已投简历/.test(text(b))).length===1)return 'sent';
          const dialogs=Array.from(document.querySelectorAll(DIALOGS)).filter(visible);
          if(dialogs.some(d=>/请选择.*简历|选择简历|选择附件简历|确认投递|投递确认|确认申请|打招呼/.test(text(d))))
            return 'needs_confirmation';
          if(dialogs.some(d=>/投递成功|申请成功|已向对方发送简历/.test(text(d))))return 'sent';
          if(Array.from(document.querySelectorAll('h1,h2,h3,strong,span,div')).some(e=>
            visible(e)&&e.children.length===0&&
            /^(投递成功|申请成功|已向对方发送简历和打招呼语)$/.test(text(e))))return 'sent';
          return 'unknown';
        })()""".replace("APPLY", _js(self.site.apply)).replace("DIALOGS", _js(
            ".a-modal,.deliver-greeting-modal,[role=dialog]" if self.site.name == "智联招聘"
            else ".operate-popup,.el-dialog,[role=dialog]" if self.site.name == "应届生"
            else ".ant-modal,[role=dialog]" if self.site.name == "猎聘"
            else ".position-modal,[role=dialog]" if self.site.name == "拉勾"
            else ".el-dialog,[role=dialog]" if self.site.name == "牛客网"
            else "#apply_now,.dialog,.modal,[role=dialog],.el-dialog"))
        state = self._window().run_js(script)
        return state if state in {"sent", "verification", "daily_limit", "needs_resume", "needs_confirmation"} else "unknown"

    def _confirm_selected_resume(self) -> bool:
        """Submit only the resume already selected by the site's own dialog."""
        if self.site.name in {"猎聘", "拉勾"}:
            dialogs = ".ant-modal,[role=dialog]" if self.site.name == "猎聘" else ".position-modal,[role=dialog]"
            button = ".ant-modal-footer .ant-btn-primary" if self.site.name == "猎聘" else ".position-modal .lg-design-btn-primary"
            script = """(() => {
              const visible=e=>!!(e&&e.getClientRects().length&&!e.disabled);
              const dialogs=Array.from(document.querySelectorAll(DIALOGS)).filter(d=>visible(d)&&
                /确认投递|投递确认|选择附件简历|选择简历/.test(d.innerText||''));
              if(dialogs.length!==1)return false;
              const d=dialogs[0];
              const choices=Array.from(d.querySelectorAll('input[type=radio],.resume-item,[role=radio]')).filter(visible);
              const selected=choices.filter(e=>e.checked||e.getAttribute('aria-checked')==='true'||
                e.classList.contains('active')||e.classList.contains('selected'));
              if(choices.length===0||selected.length!==1)return false;
              const buttons=Array.from(d.querySelectorAll(BUTTON)).filter(e=>visible(e)&&
                /^(确认投递|投递简历|确认|确定)$/.test((e.innerText||'').trim()));
              if(buttons.length!==1)return false;
              buttons[0].click();return true;
            })()""".replace("DIALOGS", _js(dialogs)).replace("BUTTON", _js(button))
            return self._window().run_js(script) is True
        if self.site.name != "智联招聘":
            return False
        script = """(() => {
          const visible=e=>!!(e&&e.getClientRects().length&&!e.disabled);
          const dialogs=Array.from(document.querySelectorAll('.a-modal,[role=dialog]'))
            .filter(e=>visible(e)&&/请选择要投递的简历/.test(e.innerText||''));
          if(dialogs.length!==1)return false;
          const d=dialogs[0];
          const selected=Array.from(d.querySelectorAll('input[type=radio]:checked,[aria-checked=true],.a-attachment-select__item--active,.resume-item.active'))
            .filter(visible);
          if(selected.length!==1)return false;
          const buttons=Array.from(d.querySelectorAll('button')).filter(e=>
            visible(e)&&(e.innerText||'').trim()==='投递简历');
          if(buttons.length!==1)return false;
          buttons[0].click();return true;
        })()"""
        return self._window().run_js(script) is True

    def upload_resume_file(self, path: str) -> dict[str, str]:
        file = Path(path)
        if not file.is_file() or file.suffix.lower() not in {".pdf", ".docx"}:
            return {"state": "invalid_file", "reason": "请选择存在的 PDF 或 DOCX 简历"}
        if file.stat().st_size > 8 * 1024 * 1024:
            return {"state": "invalid_file", "reason": "简历超过本程序支持的 8 MB"}
        if self.login_state() != "logged_in":
            return {"state": "login", "reason": f"请先在内置浏览器手动登录{self.site.name}"}
        if not any(word in urlparse(self.url).path.lower() for word in ("resume", "profile", "my")):
            return {"state": "wrong_page", "reason": f"请先在{self.site.name}打开个人简历或附件简历管理页"}
        outcome = self._window().run_js(build_resume_upload_script(file))
        if not isinstance(outcome, dict) or outcome.get("state") != "submitted_to_form":
            return {"state": "unavailable", "reason": "未找到唯一的简历文件输入框；请在网站上手动上传"}
        for _ in range(12):
            visible = self._window().run_js(
                "(() => /上传成功|简历上传成功|附件简历已上传/.test(document.body.innerText || ''))()")
            if visible is True:
                return {"state": "confirmed", "reason": "网站显示简历上传成功"}
            time.sleep(0.5)
        return {"state": "unverified", "reason": "文件已交给网页，但未看到上传成功提示；请在网站核实"}

    def apply_job(self, link: str) -> dict[str, Any]:
        if not valid_site_url(self.site, link, detail=True):
            raise ValueError("职位详情链接无效")
        search_url = self.url
        restore = True
        try:
            self.get(link)
            state = self.login_state()
            if state != "logged_in":
                restore = state not in {"logged_out", "verification"}
                return {"state": state, "clicked": False,
                        "reason": "请在内置浏览器手动登录并完成安全验证"}
            if self.check_application_result(link) == "sent":
                return {"state": "already_applied", "clicked": False,
                        "reason": "页面显示此前已申请；本次未重复投递"}
            script = """(() => {
              const visible=e=>!!(e&&e.getClientRects().length&&!e.disabled);
              const candidates=Array.from(document.querySelectorAll(APPLY)).filter(visible);
              if(candidates.some(e=>/绑定官网账号并投递|前往官网投递/.test((e.innerText||e.textContent||'').trim())))
                return {state:'external'};
              const els=candidates.filter(e=>
                /立即投递|申请职位|立即申请|投递简历|^投简历$|^投递$/.test((e.innerText||e.textContent||'').trim()));
              if(els.length!==1)return {state:'unavailable',count:els.length};
              els[0].click();return {state:'clicked'};
            })()""".replace("APPLY", _js(self.site.apply))
            click = self._window().run_js(script)
            if isinstance(click, dict) and click.get("state") == "external":
                return {"state": "unavailable", "clicked": False,
                        "reason": "该职位需要绑定企业官网账号；请核对岗位网址后使用企业官网投递助手"}
            if not isinstance(click, dict) or click.get("state") != "clicked":
                return {"state": "unavailable", "clicked": False,
                        "reason": "未找到唯一的投递按钮；请检查网站当前页面"}
            for _ in range(12):
                observed = self.check_application_result(link)
                if observed == "needs_confirmation" and self._confirm_selected_resume():
                    time.sleep(0.5)
                    continue
                if observed in {"sent", "verification", "daily_limit", "needs_resume", "needs_confirmation"}:
                    restore = observed in {"sent", "daily_limit"}
                    return {"state": observed, "clicked": True,
                            "reason": "页面可见状态：" + observed}
                time.sleep(0.5)
            restore = False
            return {"state": "unknown", "clicked": True,
                    "reason": "已点击投递按钮，但未见成功回执；请手动核实"}
        finally:
            if restore and valid_site_url(self.site, search_url) and search_url != link:
                try:
                    self.get(search_url)
                except Exception:
                    pass

    def quit(self, **_: Any) -> None:
        self.manager.close_browser_window()


class SiteDetailTab:
    def __init__(self, window: Any, site: Site) -> None:
        self.window, self.site = window, site

    @property
    def url(self) -> str:
        return str(self.window.get_current_url() or "")

    def ele(self, locator: str, timeout: float = 0):
        if locator != "css:" + self.site.detail:
            raise ValueError("详情选择器无效")
        script = """(() => {const e=document.querySelector(SEL);
          return e?(e.innerText||e.textContent||'').trim():'';})()""".replace("SEL", _js(self.site.detail))
        value = self.window.run_js(script)
        return EmbeddedTextElement(str(value)) if value else None

    def metadata(self) -> dict[str, str]:
        selectors = DETAIL_METADATA_SELECTORS[self.site.name]
        script = """(() => {
          const result={};
          const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          for(const [field,options] of Object.entries(SEL)){
            result[field]='';
            for(const selector of options){
              const nodes=Array.from(document.querySelectorAll(selector)).filter(visible);
              if(nodes.length!==1)continue;
              const value=(nodes[0].innerText||nodes[0].textContent||
                (field==='recruitment_track'&&nodes[0].getAttribute('data-recruitment-type'))||'').trim();
              if(value&&value.length<=80){result[field]=value;break;}
            }
          }
          if(SITE==='牛客网'&&!result.recruitment_track){
            const title=document.title||'';
            const campus=/校招/.test(title),social=/社招/.test(title);
            if(campus!==social)result.recruitment_track=campus?'校招':'社招';
          }
          return result;
        })()""".replace("SEL", _js(selectors)).replace("SITE", _js(self.site.name))
        result = self.window.run_js(script)
        return ({field: str(result.get(field) or "").strip() for field in selectors}
                if isinstance(result, dict) else {})

    def close(self) -> None:
        self.window.destroy()

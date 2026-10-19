"""Visible guidance inside the user's recruitment-site browser window."""

from __future__ import annotations

import json


GUIDANCE = {
    "login": (
        "请先登录或注册",
        "请在当前招聘网站手动登录；新用户先完成注册。短信、扫码和安全验证由你操作。登录后请到网站个人中心准备简历。",
    ),
    "verification": (
        "请完成网站安全验证",
        "请在当前浏览器手动完成验证码或安全检查。验证通过后，全职高手会继续检查登录状态。",
    ),
    "resume": (
        "请先准备网站简历",
        "请到当前网站的个人中心创建在线简历，或打开简历管理页上传 PDF/DOCX。全职高手的“任务与设置”可尝试上传附件和填写空白资料；请以网站显示的结果为准。",
    ),
    "unknown": (
        "请确认账号状态",
        "当前页面尚未显示可确认的登录状态。请在网站检查是否已登录或注册，并准备网站简历。",
    ),
}


def browser_guidance_script(platform: str, kind: str) -> str:
    if kind not in GUIDANCE:
        raise ValueError("不支持的浏览器提醒类型")
    title, message = GUIDANCE[kind]
    return """(() => {
      const id='fulltime-master-guidance';
      const kind=KIND;
      const prior=document.getElementById(id);
      if(prior && prior.dataset.kind===kind)return true;
      if(prior)prior.remove();
      const box=document.createElement('aside');
      box.id=id;box.dataset.kind=kind;box.setAttribute('role','alertdialog');
      box.setAttribute('aria-label',TITLE);
      box.style.cssText='position:fixed;top:18px;right:18px;z-index:2147483647;width:min(390px,calc(100vw - 36px));padding:18px 19px;background:#111e30;color:#effbff;border:1px solid #52d8dc;border-radius:12px;box-shadow:0 20px 50px rgba(0,0,0,.35);font:14px/1.6 Microsoft YaHei UI,Segoe UI,sans-serif;text-align:left;';
      const top=document.createElement('div');top.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:12px';
      const heading=document.createElement('strong');heading.textContent='全职高手 · '+PLATFORM+' · '+TITLE;
      heading.style.cssText='font-size:16px;color:#83f4e8';top.appendChild(heading);
      const close=document.createElement('button');close.type='button';close.textContent='关闭';
      close.setAttribute('aria-label','关闭提醒');
      close.style.cssText='padding:4px 9px;background:#20364b;color:#fff;border:1px solid #5d7e91;border-radius:5px;cursor:pointer;flex:none';
      close.addEventListener('click',()=>box.remove());top.appendChild(close);box.appendChild(top);
      const body=document.createElement('p');body.textContent=MESSAGE;
      body.style.cssText='margin:10px 0 0;white-space:normal';box.appendChild(body);
      (document.body||document.documentElement).appendChild(box);
      return true;
    })()""".replace("KIND", json.dumps(kind)).replace(
        "TITLE", json.dumps(title, ensure_ascii=True)).replace(
        "PLATFORM", json.dumps(platform, ensure_ascii=True)).replace(
        "MESSAGE", json.dumps(message, ensure_ascii=True))

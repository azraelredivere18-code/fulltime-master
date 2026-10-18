import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

from official_apply import (OfficialProfileStore, build_form_script,
                            clean_profile, normalize_official_url, safe_record_url)
from app import WindowAPI, WindowManager


NODE = shutil.which("node")


class OfficialApplyTests(unittest.TestCase):
    def test_url_validation_and_profile_limits(self):
        self.assertEqual(normalize_official_url("https://careers.example.com/jobs/1#details"),
                         "https://careers.example.com/jobs/1#details")
        self.assertEqual(normalize_official_url("https://careers.example.com/#/job/123"),
                         "https://careers.example.com/#/job/123")
        self.assertEqual(safe_record_url("https://careers.example.com/job?id=123&session=secret"),
                         "https://careers.example.com/job?id=123")
        self.assertEqual(safe_record_url("https://careers.example.com/#/position/detail?jobId=456&token=secret"),
                         "https://careers.example.com/#/position/detail?jobId=456")
        for value in ("http://careers.example.com/", "javascript:alert(1)",
                      "https://localhost/form", "https://192.168.1.1/form",
                      "https://a.local/form", "https://user:password@example.com/form"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_official_url(value)
        self.assertEqual(clean_profile({"full_name": " 张三 "})["full_name"], "张三")
        with self.assertRaises(ValueError):
            clean_profile({"password": "secret"})

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI required")
    def test_profile_is_encrypted_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.dpapi"
            store = OfficialProfileStore(path)
            store.save({"full_name": "Demo Candidate", "id_number": "123456789012345678"})
            self.assertNotIn(b"123456789012345678", path.read_bytes())
            self.assertEqual(store.load()["full_name"], "Demo Candidate")
            store.clear()
            self.assertFalse(path.exists())

    def test_separate_browser_reuses_window_and_manual_record_is_distinct(self):
        class ClosedEvent:
            def is_set(self): return False
            def __iadd__(self, handler): return self
        class Browser:
            def __init__(self, url):
                self.url = url
                self.loaded_urls = []
                self.scripts = []
                self.fingerprint = "stable"
                self.events = types.SimpleNamespace(
                    loaded=types.SimpleNamespace(wait=lambda _: True),
                    closed=ClosedEvent())
            def get_current_url(self): return self.url
            def load_url(self, url): self.url = url; self.loaded_urls.append(url)
            def show(self): pass
            def destroy(self): pass
            def run_js(self, script):
                self.scripts.append(script)
                return {"state": "ok", "fingerprint": self.fingerprint, "available": ["full_name"]}

        created = []
        def create_window(*args, **kwargs):
            self.assertIsNone(kwargs.get("js_api"))
            window = Browser(kwargs["url"])
            created.append(window)
            return window
        with tempfile.TemporaryDirectory() as directory:
            manager = WindowManager(Path(directory))
            with patch.dict(sys.modules, {"webview": types.SimpleNamespace(create_window=create_window)}):
                manager.open_official_browser_window("https://careers.example.com/jobs/1")
                manager.open_official_browser_window("https://careers.example.com/jobs/2?session=private")
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].loaded_urls, ["https://careers.example.com/jobs/2?session=private"])
            self.assertEqual(manager.official_page_status()["state"], "ready")
            api = WindowAPI(manager.db_path, manager, "official")
            try:
                first = api.record_official_application({"title": "研发工程师", "company": "甲公司"})
                self.assertEqual(first["state"], "saved")
                self.assertEqual(api.get_apply_record()[0]["attempt_state"], "manual_confirmed")
                self.assertEqual(api.get_apply_record()[0]["link"], "https://careers.example.com/jobs/2")
                self.assertEqual(api.record_official_application({"title": "研发工程师", "company": "甲公司"})["state"],
                                 "duplicate")
                with patch.dict(sys.modules, {"webview": types.SimpleNamespace(create_window=create_window)}):
                    manager.open_official_browser_window("https://careers.example.com/job?id=123&session=private")
                self.assertEqual(api.record_official_application({"title": "研发工程师", "company": "甲公司"})["state"],
                                 "saved")
                with patch.dict(sys.modules, {"webview": types.SimpleNamespace(create_window=create_window)}):
                    manager.open_official_browser_window("https://careers.example.com/#/job/456?token=private")
                self.assertEqual(api.record_official_application({"title": "研发工程师", "company": "甲公司"})["state"],
                                 "saved")
                self.assertEqual(api.get_apply_record()[0]["link"], "https://careers.example.com/#/job/456")
                profile = clean_profile({"full_name": "Private Candidate", "id_number": "123456789012345678"})
                self.assertEqual(manager.official_form_action(profile, fill=True)["state"], "stale_preview")
                self.assertEqual(manager.official_form_action(profile, fill=False)["state"], "ok")
                self.assertNotIn("Private Candidate", created[0].scripts[-1])
                self.assertNotIn("123456789012345678", created[0].scripts[-1])
                self.assertEqual(manager.official_form_action(profile, fill=True)["state"], "ok")
                self.assertIn("Private Candidate", created[0].scripts[-1])
                self.assertNotIn("123456789012345678", created[0].scripts[-1])
                self.assertEqual(manager.official_form_action(profile, fill=True)["state"], "stale_preview")
                manager.official_form_action(profile, fill=False)
                created[0].fingerprint = "changed"
                self.assertEqual(manager.official_form_action(profile, fill=True)["state"], "stale_preview")
                created[0].fingerprint = "stable"
                manager.official_form_action(profile, fill=False)
                created[0].url = "https://careers.example.com/#/job/789"
                self.assertEqual(manager.official_form_action(profile, fill=True)["state"], "stale_preview")
            finally:
                api.close()

    @unittest.skipUnless(NODE, "Node required for DOM execution")
    def test_dom_preview_and_fill_only_unique_blank_fields(self):
        harness = r"""
          const fs=require('fs');const script=fs.readFileSync(0,'utf8');
          global.Event=class {constructor(type){this.type=type;}};
          global.HTMLInputElement=class {
            constructor(label,value='',visible=true,type='text'){
              this.tagName='INPUT';this.type=type;this._value=value;this.name='';this.id='';
              this.autocomplete='';this.placeholder='';this.labels=[{innerText:label}];
              this.disabled=false;this.readOnly=false;this.visible=visible;this.events=[];
            }
            get value(){return this._value;}set value(v){this._value=v;}
            getClientRects(){return this.visible?[1]:[];}
            matches(){return false;}closest(){return null;}getAttribute(){return null;}
            dispatchEvent(e){this.events.push(e.type);}
          };
          global.HTMLTextAreaElement=global.HTMLInputElement;
          global.HTMLSelectElement=global.HTMLInputElement;
          const fields=[new HTMLInputElement('姓名'),new HTMLInputElement('手机号'),
            new HTMLInputElement('邮箱地址','already@example.com'),
            new HTMLInputElement('毕业院校'),new HTMLInputElement('毕业院校'),
            new HTMLInputElement('身份证号','',false),
            new HTMLInputElement('密码','',true,'password'),
            new HTMLInputElement('紧急联系人姓名'),new HTMLInputElement('银行卡号')];
          fields[7].name='full_name';fields[8].name='phone';
          global.document={querySelectorAll:s=>s==='input,textarea,select'?fields:[]};
          global.location={protocol:'https:',hostname:HOST};
          global.getComputedStyle=()=>({visibility:'visible'});
          const result=eval(script);
          process.stdout.write(JSON.stringify({result,values:fields.map(x=>x.value),
            events:fields.map(x=>x.events),submitted:false}));
        """
        profile = {"full_name": "李四", "phone": "13800000000", "email": "new@example.com",
                   "university": "某大学", "id_number": "123456789012345678"}
        def execute(fill, host="careers.example.com"):
            script = build_form_script(profile, "careers.example.com", fill=fill)
            result = subprocess.run([NODE, "-e", harness.replace("HOST", json.dumps(host))],
                                    input=script, text=True, encoding="utf-8", capture_output=True,
                                    check=True, timeout=10)
            return json.loads(result.stdout)
        preview = execute(False)
        self.assertEqual(preview["result"]["available"], ["full_name", "phone"])
        self.assertEqual(preview["result"]["targets"][0]["label"], "姓名")
        self.assertNotIn("李四", build_form_script(profile, "careers.example.com", fill=False))
        self.assertEqual(preview["values"][0], "")
        filled = execute(True)
        self.assertEqual(filled["result"]["filled"], ["full_name", "phone"])
        self.assertEqual(filled["values"][:3], ["李四", "13800000000", "already@example.com"])
        self.assertEqual(filled["events"][0], ["input", "change"])
        self.assertEqual(execute(True, "other.example.com")["result"]["state"], "wrong_site")


if __name__ == "__main__":
    unittest.main()

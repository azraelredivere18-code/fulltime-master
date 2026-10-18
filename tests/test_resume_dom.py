"""Exercise the exact DOM scripts against small Node DOM doubles."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from embedded_browser import build_resume_upload_script
from site_adapters import EmbeddedSitePage, SITES


NODE = shutil.which("node")


def run_dom(script: str, harness: str) -> object:
    result = subprocess.run([NODE, "-e", harness], input=script, text=True, encoding="utf-8",
                            capture_output=True, timeout=10, check=True)
    return json.loads(result.stdout.strip())


@unittest.skipUnless(NODE, "Node is required to execute WebView DOM scripts")
class ResumeDomTests(unittest.TestCase):
    def test_upload_rejects_avatar_and_multiple_file_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "resume.pdf"
            file.write_bytes(b"%PDF-1.4\n")
            script = build_resume_upload_script(file)
            harness = r"""
              const fs=require('fs'); const script=fs.readFileSync(0,'utf8');
              const make=(name,accept='')=>({disabled:false,name,id:name,accept,labels:[],
                parentElement:{innerText:name,parentElement:{innerText:name}},
                getAttribute:()=>'',dispatchEvent:()=>{}});
              const inputs=CASE;
              global.document={querySelectorAll:()=>inputs};
              global.atob=s=>Buffer.from(s,'base64').toString('binary');
              global.File=class {constructor(bytes,name,options){this.name=name;}};
              global.DataTransfer=class {constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}};
              global.Event=class {constructor(name){this.type=name;}};
              process.stdout.write(JSON.stringify(eval(script)));
            """
            self.assertEqual(run_dom(script, harness.replace("CASE", "[make('avatar','image/*')]")),
                             {"state": "not_resume_input"})
            self.assertEqual(run_dom(script, harness.replace("CASE", "[make('简历'),make('avatar')]"))["state"],
                             "ambiguous_input")
            self.assertEqual(run_dom(script, harness.replace("CASE", "[make('附件简历','application/pdf')]")),
                             {"state": "submitted_to_form"})

    def test_resume_confirmation_requires_selected_choice(self):
        class Window:
            outcome = None
            def run_js(self, script):
                harness = r"""
                  const fs=require('fs');const script=fs.readFileSync(0,'utf8');
                  const button={disabled:false,innerText:'确认投递',getClientRects:()=>[1],
                    click:()=>{global.clicked=true;}};
                  const dialog={disabled:false,innerText:'确认投递 选择简历',getClientRects:()=>[1],
                    querySelectorAll:s=>s.includes('input[type=radio]')?[]:[button]};
                  global.document={querySelectorAll:()=>[dialog]};
                  global.clicked=false;
                  process.stdout.write(JSON.stringify({result:eval(script),clicked:global.clicked}));
                """
                self.outcome = run_dom(script, harness)
                return self.outcome["result"]

        class Manager:
            window = Window()
            def current_browser_window(self):
                return self.window

        manager = Manager()
        page = EmbeddedSitePage(manager, SITES["猎聘"])
        self.assertFalse(page._confirm_selected_resume())
        self.assertEqual(manager.window.outcome, {"result": False, "clicked": False})


if __name__ == "__main__":
    unittest.main()

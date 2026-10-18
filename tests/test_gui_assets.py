import re
import unittest
from pathlib import Path


class GuiAssetTests(unittest.TestCase):
    def test_local_html_and_css_resources_exist(self):
        root = Path(__file__).resolve().parents[1] / "gui" / "templates"
        missing = []
        for source in root.rglob("*"):
            if source.suffix not in {".html", ".css"}:
                continue
            markup = source.read_text(encoding="utf-8", errors="replace")
            refs = re.findall(
                r'''(?:src|href)=["']([^"']+)["']|url\(["']?([^\)\'" ]+)''',
                markup,
            )
            for html_ref, css_ref in refs:
                ref = html_ref or css_ref
                if not ref or ref.startswith(("http:", "https:", "data:", "#", "//", "javascript:")):
                    continue
                target = source.parent / ref.split("?", 1)[0].split("#", 1)[0]
                if not target.is_file():
                    missing.append(f"{source.relative_to(root)} -> {ref}")
        self.assertEqual(missing, [])

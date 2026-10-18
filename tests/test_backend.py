import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec
from pathlib import Path

from backend import LocalBackend


def task(keyword, platform="BOSS直聘", **overrides):
    value = {
        "keyword": keyword,
        "city": "上海",
        "search_prompt": "",
        "job_prompt": "",
        "search_re": "",
        "job_re": "",
        "resume": "张三，有五年 Python 开发经验",
        "match_degree": 60,
        "platform": platform,
    }
    value.update(overrides)
    return value


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "data" / "app.sqlite3"
        self.backend = LocalBackend(self.path)

    def tearDown(self):
        self.backend.close()
        self.temp.cleanup()

    def test_daily_slots_survive_restart_and_never_exceed_120(self):
        day = "2026-10-17"
        for number in range(120):
            self.assertEqual(self.backend.reserve_application_slot(
                f"https://www.zhipin.com/job_detail/{number}.html", "上海", day=day), "reserved")
        self.backend.finalize_application_slot(
            "https://www.zhipin.com/job_detail/0.html", "unknown", day=day)
        self.backend.close()
        self.backend = LocalBackend(self.path)
        self.assertEqual(self.backend.daily_application_usage(day)["total"], 120)
        self.assertEqual(self.backend.reserve_application_slot(
            "https://www.zhipin.com/job_detail/121.html", "北京", day=day), "daily_limit")
        self.assertEqual(self.backend.reserve_application_slot(
            "https://www.zhipin.com/job_detail/0.html", "北京", day=day), "duplicate")
        self.assertEqual(self.backend.reserve_application_slot(
            "https://www.zhipin.com/job_detail/121.html", "北京", day="2026-10-18"), "reserved")

    def test_unopened_action_releases_slot_and_legacy_success_counts(self):
        day = "2026-10-17"
        link = "https://www.zhipin.com/job_detail/release.html"
        self.assertEqual(self.backend.reserve_application_slot(link, "上海", day=day), "reserved")
        self.backend.finalize_application_slot(link, "released", day=day)
        self.assertEqual(self.backend.daily_application_usage(day)["total"], 0)
        self.assertEqual(self.backend.reserve_application_slot(link, "北京", day=day), "reserved")
        self.backend.add_apply_record({
            "source": "BOSS直聘", "link": "https://www.zhipin.com/job_detail/legacy.html",
            "submit": "是", "submit_time": "2026-10-17 12:30:00", "search_city": "广州",
        })
        usage = self.backend.daily_application_usage(day)
        self.assertEqual(usage["total"], 2)
        self.assertEqual(usage["by_city"], {"北京": 1, "广州": 1})

    def test_task_order_selection_and_restart(self):
        first = self.backend.save_task(task("Python", "BOSS直聘,猎聘"))
        second = self.backend.save_task(task("销售", "猎聘"))
        self.assertEqual(self.backend.get_task("猎聘")["keyword"], "Python")
        self.assertTrue(self.backend.alter_task("move_down", {"curr": first, "next": second}))
        self.assertEqual([x["id"] for x in self.backend.get_tasks()], [second, first])
        self.assertEqual(self.backend.get_task("猎聘")["keyword"], "销售")
        self.assertFalse(self.backend.alter_task("move_up", {"curr": second, "prev": 999}))
        changed = task("Go", "猎聘", id=second, match_degree=95)
        self.assertTrue(self.backend.update_task(changed))
        self.backend.close()
        self.backend = LocalBackend(self.path)
        self.assertEqual(self.backend.get_tasks()[0]["keyword"], "Go")
        self.assertEqual(self.backend.get_tasks()[0]["match_degree"], 95)
        self.assertTrue(self.backend.alter_task("delete", str(first)))
        self.assertIsNone(self.backend.get_task("BOSS直聘"))

    def test_task_validation_corrects_frontend_range_bug(self):
        with self.assertRaises(ValueError):
            self.backend.save_task(task("", "猎聘"))
        with self.assertRaises(ValueError):
            self.backend.save_task(task("Python", "猎聘", match_degree=96))
        with self.assertRaises(Exception):
            self.backend.save_task(task("Python", "猎聘", search_re="["))

    def test_config_blocklist_and_records_persist(self):
        self.assertEqual(self.backend.get_apply_config("timing.hour"), 9)
        self.backend.set_apply_config("timing.hour", 18)
        self.backend.set_apply_config("boss.filter.salary", "20-30K")
        self.backend.set_app_config("bit.port", "54345")
        self.backend.set_curr_config("task_scope", "全局")
        blocked = self.backend.save_blocklist({"company": "示例公司"})
        self.backend.add_apply_record({"source": "BOSS直聘", "title": "开发", "remarks": "已投递"})
        self.backend.add_chat_record({"source": "BOSS直聘", "msg_reply": "您好"})
        self.backend.close()
        self.backend = LocalBackend(self.path)
        self.assertEqual(self.backend.get_apply_config("timing.hour"), 18)
        self.assertEqual(self.backend.get_apply_config("boss.filter.salary"), "20-30K")
        self.assertEqual(self.backend.get_app_config("bit.port"), "54345")
        self.assertEqual(self.backend.get_curr_config("task_scope"), "全局")
        self.assertEqual(self.backend.get_blocklist()[0]["company"], "示例公司")
        self.assertEqual(self.backend.get_apply_record()[0]["title"], "开发")
        self.assertEqual(self.backend.get_chat_record()[0]["msg_reply"], "您好")
        self.assertTrue(self.backend.alter_blocklist("delete", blocked))
        self.assertEqual(self.backend.get_blocklist(), [])

    def test_blocklist_validates_regex_before_saving(self):
        with self.assertRaisesRegex(ValueError, "正则表达式无效"):
            self.backend.save_blocklist({"company": "(未闭合"})
        self.assertEqual(self.backend.get_blocklist(), [])
        self.backend.save_blocklist({"company": "^(甲|乙)公司$"})
        self.assertEqual(len(self.backend.get_blocklist()), 1)

    def test_concurrent_gui_calls_share_one_store_safely(self):
        def save(index):
            return self.backend.save_task(task(f"职位{index}"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(save, range(24)))
        self.assertEqual(len(set(ids)), 24)
        self.assertEqual(len(self.backend.get_tasks()), 24)

    def test_recovered_platform_options_and_override(self):
        recovered = self.backend.get_platform_setting("boss")
        self.assertEqual(recovered["target"]["name"], "限制投递对象")
        self.assertEqual(recovered["target"]["selectionMode"], "single")
        options = {"salary": {"name": "薪资", "selectionMode": "multiple",
                              "options": [{"code": "20-30K", "name": "20-30K"}]}}
        self.backend.set_platform_setting("boss", options)
        self.assertEqual(self.backend.get_platform_setting("boss"), options)
        with self.assertRaises(ValueError):
            self.backend.get_platform_setting("unknown")

    def test_regex_helpers_match_intent_and_round_trip(self):
        expression = self.backend.keywords_to_regex("Python Java", "实习 外包", "OR")
        self.assertEqual(self.backend.regex_to_keywords(expression), ["Python Java", "实习 外包"])
        import re
        self.assertIsNotNone(re.search(expression, "资深 Python 开发"))
        self.assertIsNone(re.search(expression, "Python 外包"))
        both = self.backend.keywords_to_regex("Python Java", "", "AND")
        self.assertIsNotNone(re.search(both, "Python 和 Java"))
        self.assertIsNone(re.search(both, "Python"))

    def test_docx_resume_text_and_picker_contract(self):
        doc = Path(self.temp.name) / "resume.docx"
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>张三</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>Python 工程师</w:t></w:r></w:p></w:body></w:document>')
        with zipfile.ZipFile(doc, "w") as archive:
            archive.writestr("word/document.xml", xml)
        self.assertEqual(self.backend.extract_resume_text(doc), "张三\nPython 工程师")
        self.assertEqual(self.backend.get_file_content(doc), "张三\nPython 工程师")
        with self.assertRaises(RuntimeError):
            self.backend.get_file_content(["简历 (*.docx;*.pdf)"])

    @unittest.skipUnless(find_spec("pypdf"), "PDF extraction dependency unavailable")
    def test_pdf_resume_text_extraction(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        pdf = Path(self.temp.name) / "resume.pdf"
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 200 Td (Hello Resume) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        with pdf.open("wb") as file:
            writer.write(file)
        self.assertEqual(self.backend.extract_resume_text(pdf), "Hello Resume")


if __name__ == "__main__":
    unittest.main()

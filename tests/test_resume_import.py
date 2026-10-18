import tempfile
import unittest
import zipfile
from pathlib import Path

from app import WindowAPI, WindowManager
from resume_import import extract_resume_candidates


class ResumeImportTests(unittest.TestCase):
    def test_labelled_fields_and_contacts_require_review(self):
        resume = """姓名：张三  性别：男
手机号：13800138000 邮箱：zhang@example.com
出生日期：2002-08-12 政治面貌：共青团员
毕业院校：清华大学 专业：计算机科学与技术 学历：本科
技能特长：Python、数据分析
身份证号：110101200208121234
紧急联系人姓名：李四 手机号：13900139000
"""
        result = extract_resume_candidates(resume)
        values = {row["field"]: row for row in result["candidates"]}
        self.assertEqual(values["full_name"]["value"], "张三")
        self.assertEqual(values["phone"]["value"], "13800138000")
        self.assertEqual(values["email"]["value"], "zhang@example.com")
        self.assertEqual(values["university"]["value"], "清华大学")
        self.assertEqual(values["major"]["value"], "计算机科学与技术")
        self.assertFalse(values["id_number"]["default_selected"])
        self.assertNotIn("13900139000", repr(values))
        self.assertEqual(
            {row["field"]: row["value"] for row in
             extract_resume_candidates("姓名 张三\n电话 13800138000")["candidates"]}["full_name"],
            "张三")

    def test_conflicting_values_and_unreadable_resume_are_not_guessed(self):
        result = extract_resume_candidates("手机号：13800138000\n手机号：13700137000")
        self.assertNotIn("phone", {row["field"] for row in result["candidates"]})
        self.assertTrue(any("手机号出现多个不同值" in warning for warning in result["warnings"]))
        self.assertTrue(extract_resume_candidates(" ")["warnings"])
        self.assertNotIn("full_name", {row["field"] for row in
                         extract_resume_candidates("项目名称：张三的计划")["candidates"]})

    def test_unlabelled_education_is_review_only(self):
        result = extract_resume_candidates(
            "张三\n13800138000\n教育经历\n2020.09-2024.06 清华大学 计算机科学与技术 本科\n项目经历\n开发工具")
        candidates = {row["field"]: row for row in result["candidates"]}
        self.assertEqual(candidates["university"]["value"], "清华大学")
        self.assertEqual(candidates["major"]["value"], "计算机科学与技术")
        self.assertEqual(candidates["education"]["value"], "本科")
        self.assertFalse(candidates["full_name"]["default_selected"])
        self.assertFalse(candidates["university"]["default_selected"])

    def test_docx_import_previews_without_saving_or_changing_upload_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "resume.docx"
            body = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body><w:p><w:r><w:t>姓名：张三</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>邮箱：zhang@example.com</w:t></w:r></w:p></w:body></w:document>')
            with zipfile.ZipFile(file, "w") as archive:
                archive.writestr("word/document.xml", body)
            manager = WindowManager(root)
            api = WindowAPI(manager.db_path, manager, "official")
            try:
                api.set_apply_config("resume_file", str(file))
                result = api.preview_official_resume_import("selected")
                self.assertEqual(result["state"], "preview")
                self.assertEqual(result["filename"], "resume.docx")
                self.assertEqual({row["field"] for row in result["candidates"]}, {"full_name", "email"})
                self.assertEqual(api.get_apply_config("resume_file"), str(file))
                self.assertFalse((root / "official_profile.dpapi").exists())
            finally:
                api.close()


if __name__ == "__main__":
    unittest.main()

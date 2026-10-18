import tempfile
import unittest
from pathlib import Path

from backend import LocalStore
from employment_type import employment_type_reason, job_type


class EmploymentTypeTests(unittest.TestCase):
    def test_internship_task_requires_explicit_listing_evidence(self):
        self.assertEqual(job_type({"title": "产品经理实习生"}), "internship")
        self.assertIsNone(employment_type_reason("internship", {"title": "产品经理实习生"}))
        self.assertIn("未明确", employment_type_reason("internship", {"title": "产品经理"}))
        self.assertIn("实习", employment_type_reason("full_time", {"title": "产品经理 Intern"}))
        self.assertIsNone(employment_type_reason("full_time", {"title": "产品经理"}))

    def test_labelled_detail_type_blocks_wrong_task_without_matching_experience_sentence(self):
        listing = {"title": "管理培训生", "summary": "岗位性质：实习"}
        self.assertEqual(job_type(listing), "internship")
        self.assertIn("实习职位", employment_type_reason("full_time", listing))
        self.assertIsNone(employment_type_reason("internship", listing))
        self.assertEqual(job_type({"title": "数据分析师", "description": "有实习经验者优先"}),
                         "unknown")
        self.assertIn("未明确", employment_type_reason(
            "full_time", {"title": "数据分析师"}, strict_unknown=True))

    def test_task_type_persists_and_legacy_defaults_to_full_time(self):
        with tempfile.TemporaryDirectory() as folder:
            with LocalStore(Path(folder) / "app.sqlite3") as store:
                task_id = store.save_task({"keyword": "产品", "city": "上海", "match_degree": 0,
                                           "employment_type": "internship", "platform": "BOSS直聘"})
                self.assertEqual(store.get_tasks()[0]["employment_type"], "internship")
                task = store.get_tasks()[0]
                task["employment_type"] = "full_time"
                self.assertTrue(store.update_task(task))
                self.assertEqual(store.get_tasks()[0]["employment_type"], "full_time")
                self.assertGreater(task_id, 0)
                with self.assertRaisesRegex(ValueError, "employment_type"):
                    store.save_task({"keyword": "产品", "city": "上海", "match_degree": 0,
                                     "employment_type": "both", "platform": "BOSS直聘"})


if __name__ == "__main__":
    unittest.main()

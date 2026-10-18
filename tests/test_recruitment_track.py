import tempfile
import unittest
from pathlib import Path

from backend import LocalStore
from recruitment_track import recruitment_track, recruitment_track_reason


class RecruitmentTrackTests(unittest.TestCase):
    def test_explicit_campus_and_social_evidence(self):
        self.assertEqual(recruitment_track({"title": "2027届校招管培生"}), "campus")
        self.assertEqual(recruitment_track({"summary": "招聘类型：社会招聘\n工作地点：上海"}), "social")
        self.assertEqual(recruitment_track({"link": "https://example.com/jobs/campus/123"}), "campus")
        self.assertEqual(recruitment_track({"title": "数据分析师", "description": "应届生优先"}), "unknown")
        self.assertEqual(recruitment_track({"title": "校招/社招岗位"}), "unknown")
        self.assertEqual(recruitment_track({"title": "Social Media Specialist"}), "unknown")
        self.assertEqual(recruitment_track({"title": "Campus Ambassador"}), "unknown")
        self.assertEqual(recruitment_track({"title": "Social Recruitment Engineer"}), "social")
        self.assertEqual(recruitment_track({"title": "Campus Recruitment Engineer"}), "campus")
        self.assertEqual(recruitment_track({"title": "社招开发", "description": "招聘类型：校园招聘"}), "unknown")
        self.assertIsNone(recruitment_track_reason("campus", {"title": "校招管培生"}))
        self.assertIn("未明确", recruitment_track_reason("social", {"title": "数据分析师"}))
        self.assertIn("另一", recruitment_track_reason("social", {"title": "校招管培生"}))

    def test_legacy_task_defaults_to_all_and_new_track_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            with LocalStore(Path(directory) / "data.sqlite3") as store:
                task_id = store.save_task({"keyword": "管培生", "city": "上海", "match_degree": 0})
                task = store.get_tasks()[0]
                self.assertEqual(task["recruitment_track"], "all")
                task["id"] = task_id
                task["recruitment_track"] = "campus"
                self.assertTrue(store.update_task(task))
                self.assertEqual(store.get_tasks()[0]["recruitment_track"], "campus")
                with self.assertRaisesRegex(ValueError, "recruitment_track"):
                    store.save_task({"keyword": "管培生", "city": "上海", "match_degree": 0,
                                     "recruitment_track": "unknown"})


if __name__ == "__main__":
    unittest.main()

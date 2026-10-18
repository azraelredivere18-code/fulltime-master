import tempfile
import unittest
from pathlib import Path

from backend import LocalStore
from salary_codec import UNKNOWN_SALARY, readable_salary


class SalaryCodecTests(unittest.TestCase):
    def test_current_boss_font_range_decodes_and_unknown_range_is_not_guessed(self):
        self.assertEqual(readable_salary("\ue032\ue036-\ue033\ue036K·\ue032\ue034薪"), "15-25K·13薪")
        self.assertEqual(readable_salary("\ue038-\ue032\ue033K"), "7-12K")
        self.assertEqual(readable_salary("\ue8f0-\ue8f9K"), UNKNOWN_SALARY)
        self.assertEqual(readable_salary("30-50K"), "30-50K")

    def test_old_records_are_readable_without_changing_stored_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalStore(Path(folder) / "app.sqlite3")
            try:
                record_id = store.add_apply_record({
                    "source": "BOSS直聘", "title": "数据分析师",
                    "salary": "\ue032\ue036-\ue033\ue036K", "link": "https://www.zhipin.com/job_detail/1.html",
                })
                row = next(row for row in store.get_apply_record() if row["id"] == record_id)
                self.assertEqual(row["salary"], "15-25K")
                stored = store._db.execute("SELECT data FROM record WHERE id=?", (record_id,)).fetchone()[0]
                self.assertIn("\ue032", stored)
            finally:
                store.close()

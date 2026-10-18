import unittest

from sales_roles import classify_sales_role


class SalesRolesTests(unittest.TestCase):
    def test_clear_sales_titles(self):
        for title in ("高薪销售", "电话销售", "销售代表", "地推", "Sales Manager"):
            with self.subTest(title=title):
                self.assertEqual(classify_sales_role(title).status, "sales")

    def test_support_roles_and_non_sales_work(self):
        for title in ("销售运营", "售前工程师", "销售数据分析师", "外协订单专员（管培岗）"):
            with self.subTest(title=title):
                self.assertEqual(classify_sales_role(title, "整理订单和数据").status, "non_sales")

    def test_ambiguous_title_requires_duties(self):
        self.assertEqual(classify_sales_role("客户经理").status, "unknown")
        self.assertEqual(classify_sales_role("客户经理", "开发新客户，达成签约及销售指标").status, "sales")
        self.assertEqual(classify_sales_role("客户经理", "维护现有客户，处理服务问题").status,
                         "non_sales")


if __name__ == "__main__":
    unittest.main()

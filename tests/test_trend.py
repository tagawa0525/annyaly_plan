"""月次トレンド分析のテスト"""

import sqlite3
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from utils.trend import utilization_trend, budget_trend, progress_trend
from utils.kpi import budget_burn
from init_db import DDL, VIEWS


class TrendTestBase(unittest.TestCase):
    """Trend test base with multi-month data"""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DDL)
        self.db.executescript(VIEWS)
        self.db.commit()
        self._setup_base_data()

    def tearDown(self):
        self.db.close()

    def _setup_base_data(self):
        # Fiscal year
        self.db.execute(
            "INSERT INTO fiscal_year VALUES (?, ?, ?, ?, ?)",
            (2026, "2026-04-01", "2027-03-31", 200000000, 15),
        )

        # Calendar: Apr-Sep
        for m in range(4, 10):
            ym = f"2026-{m:02d}"
            self.db.execute(
                "INSERT INTO monthly_calendar VALUES (?, ?)", (ym, 20)
            )

        # Members
        self.db.execute(
            """INSERT INTO members VALUES
            ('M001', '田中太郎', 'internal', 'PM', 'senior', 800000, NULL, 1.0, 0, '2020-01-01', NULL, NULL, NULL)"""
        )
        self.db.execute(
            """INSERT INTO members VALUES
            ('M002', '佐藤次郎', 'internal', 'SE', 'mid', 600000, NULL, 1.0, 0, '2020-06-01', NULL, NULL, NULL)"""
        )

        # Projects
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P001', 'A社基幹システム刷新', 'A社', 'in_progress', 'high', '2026-04-01', '2027-03-31',
             'M001', 'signed', '2026-04-01', '2026-04-01', NULL, 50000000, NULL, NULL)"""
        )
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P002', 'B社会計システム導入', 'B社', 'in_progress', 'medium', '2026-06-01', '2027-03-31',
             'M001', 'signed', '2026-06-01', '2026-06-01', NULL, 30000000, NULL, NULL)"""
        )

        # Project budgets
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P001', 40000000, 5000000, 5000000)"
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P002', 20000000, 5000000, 5000000)"
        )

        # Member capacity: Apr-Sep
        for m in range(4, 10):
            ym = f"2026-{m:02d}"
            for member_id in ["M001", "M002"]:
                self.db.execute(
                    "INSERT INTO member_capacity VALUES (?, ?, 0, 0)",
                    (member_id, ym),
                )

        # Assignments plan: M001=0.5, M002=0.8 on P001 for Apr-Sep
        for m in range(4, 10):
            ym = f"2026-{m:02d}"
            self.db.execute(
                "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
                ("M001", "P001", ym, 0.5, "PM"),
            )
            self.db.execute(
                "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
                ("M002", "P001", ym, 0.8, "SE"),
            )

        # Budget plan: P001 monthly
        for m in range(4, 10):
            ym = f"2026-{m:02d}"
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P001", ym, 3000000, 500000, 400000, 5000000),
            )

        # Budget actual: P001 Apr and May
        self.db.execute(
            "INSERT INTO budget_actual VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("P001", "2026-04", 2800000, 450000, 380000, "sap", None),
        )
        self.db.execute(
            "INSERT INTO budget_actual VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("P001", "2026-05", 3100000, 520000, 410000, "sap", None),
        )

        # Progress: P001 Apr=8%, May=18%, Jun=30%
        self.db.execute(
            "INSERT INTO progress VALUES (?, ?, ?, ?)",
            ("P001", "2026-04", 8, None),
        )
        self.db.execute(
            "INSERT INTO progress VALUES (?, ?, ?, ?)",
            ("P001", "2026-05", 18, None),
        )
        self.db.execute(
            "INSERT INTO progress VALUES (?, ?, ?, ?)",
            ("P001", "2026-06", 30, None),
        )

        self.db.commit()


# ========================
# テスト: budget_burn の year_month 対応
# ========================


class TestBudgetBurnYearMonth(TrendTestBase):
    def test_cumulative_no_month(self):
        """従来動作: year_month=None で全期間累積"""
        results = budget_burn(self.db)
        p001 = [r for r in results if r["project_id"] == "P001"][0]
        # Apr + May actuals
        self.assertEqual(p001["actual_labor"], 2800000 + 3100000)

    def test_cumulative_up_to_month(self):
        """year_month指定: その月までの累積"""
        results = budget_burn(self.db, year_month="2026-04")
        p001 = [r for r in results if r["project_id"] == "P001"][0]
        # Apr only
        self.assertEqual(p001["actual_labor"], 2800000)

    def test_cumulative_up_to_may(self):
        """year_month指定: 5月までの累積"""
        results = budget_burn(self.db, year_month="2026-05")
        p001 = [r for r in results if r["project_id"] == "P001"][0]
        # Apr + May
        self.assertEqual(p001["actual_labor"], 2800000 + 3100000)

    def test_cumulative_future_month(self):
        """year_month指定: 実績なしの月"""
        results = budget_burn(self.db, year_month="2026-09")
        p001 = [r for r in results if r["project_id"] == "P001"][0]
        # All actuals (Apr + May, no data after that)
        self.assertEqual(p001["actual_labor"], 2800000 + 3100000)


# ========================
# テスト: 稼働率トレンド
# ========================


class TestUtilizationTrend(TrendTestBase):
    def test_basic_trend(self):
        """複数月の稼働率推移を取得"""
        results = utilization_trend(self.db, "2026-04", "2026-06")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["year_month"], "2026-04")
        self.assertEqual(results[2]["year_month"], "2026-06")

    def test_rate_present(self):
        """稼働率が含まれる"""
        results = utilization_trend(self.db, "2026-04", "2026-04")
        self.assertEqual(len(results), 1)
        # M001=0.5, M002=0.8 → avg = 0.65
        self.assertGreater(results[0]["rate"], 0)

    def test_empty_range(self):
        """範囲外の月は空"""
        results = utilization_trend(self.db, "2025-01", "2025-03")
        # No data for 2025, should return entries with 0 rates
        self.assertEqual(len(results), 3)


# ========================
# テスト: 予算消化トレンド
# ========================


class TestBudgetTrend(TrendTestBase):
    def test_basic_trend(self):
        """複数月の予算消化推移"""
        results = budget_trend(self.db, "2026-04", "2026-06")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["year_month"], "2026-04")

    def test_cumulative_growth(self):
        """累積が月を追うごとに増加"""
        results = budget_trend(self.db, "2026-04", "2026-05")
        # Apr cumulative < May cumulative
        self.assertLessEqual(
            results[0]["actual_cumulative"], results[1]["actual_cumulative"]
        )

    def test_planned_cumulative(self):
        """計画累積が含まれる"""
        results = budget_trend(self.db, "2026-04", "2026-04")
        # P001: Apr planned = 3000000 + 500000 + 400000 = 3900000
        self.assertGreater(results[0]["planned_cumulative"], 0)


# ========================
# テスト: 進捗トレンド
# ========================


class TestProgressTrend(TrendTestBase):
    def test_basic_trend(self):
        """複数月の進捗推移"""
        results = progress_trend(self.db, "2026-04", "2026-06")
        # P001 should have data
        p001 = [r for r in results if r["project_id"] == "P001"]
        self.assertEqual(len(p001), 1)
        self.assertIn("2026-04", p001[0]["months"])
        self.assertIn("2026-06", p001[0]["months"])

    def test_progress_values(self):
        """進捗値が正しい"""
        results = progress_trend(self.db, "2026-04", "2026-06")
        p001 = [r for r in results if r["project_id"] == "P001"][0]
        self.assertEqual(p001["months"]["2026-04"], 8)
        self.assertEqual(p001["months"]["2026-05"], 18)
        self.assertEqual(p001["months"]["2026-06"], 30)

    def test_project_not_started(self):
        """未開始案件は対象月以前のデータなし"""
        # P002 starts 2026-06, so Apr/May should have no data
        results = progress_trend(self.db, "2026-04", "2026-06")
        p002 = [r for r in results if r["project_id"] == "P002"]
        if p002:
            self.assertIsNone(p002[0]["months"].get("2026-04"))


if __name__ == "__main__":
    unittest.main()

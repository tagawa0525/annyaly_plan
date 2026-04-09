"""売上予測の精緻化テスト"""

import sqlite3
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from utils.kpi import revenue_forecast_weighted
from init_db import DDL, VIEWS


class ForecastTestBase(unittest.TestCase):
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
        # Fiscal year: target 200M
        self.db.execute(
            "INSERT INTO fiscal_year VALUES (?, ?, ?, ?, ?)",
            (2026, "2026-04-01", "2027-03-31", 200000000, 15),
        )

        # Calendar
        for m in range(4, 13):
            self.db.execute(
                "INSERT INTO monthly_calendar VALUES (?, ?)",
                (f"2026-{m:02d}", 20),
            )
        for m in range(1, 4):
            self.db.execute(
                "INSERT INTO monthly_calendar VALUES (?, ?)",
                (f"2027-{m:02d}", 20),
            )

        # Members (required for FK)
        self.db.execute(
            """INSERT INTO members VALUES
            ('M001', '田中太郎', 'internal', 'PM', 'senior', 800000, NULL, 1.0, 0, '2020-01-01', NULL, NULL, NULL)"""
        )

        # Projects: 1 signed, 1 delayed, 1 planned
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P001', 'A社システム', 'A社', 'in_progress', 'high', '2026-04-01', '2027-03-31',
             'M001', 'signed', '2026-04-01', '2026-04-01', NULL, 50000000, NULL, NULL)"""
        )
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P002', 'B社システム', 'B社', 'in_progress', 'medium', '2026-04-01', '2027-03-31',
             'M001', 'delayed', '2026-04-01', '2026-06-01', NULL, 30000000, NULL, NULL)"""
        )
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P003', 'C社システム', 'C社', 'planned', 'low', '2026-04-01', '2027-03-31',
             'M001', 'planned', '2026-04-01', '2026-04-01', NULL, 20000000, NULL, NULL)"""
        )

        # Project budgets
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P001', 40000000, 5000000, 5000000)"
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P002', 20000000, 5000000, 5000000)"
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P003', 15000000, 3000000, 2000000)"
        )

        # Budget plan with revenue:
        # P001 (signed): 1,000,000/month x 12 = 12,000,000
        # P002 (delayed): 500,000/month x 12 = 6,000,000
        # P003 (planned): 300,000/month x 12 = 3,600,000
        for m in range(4, 13):
            ym = f"2026-{m:02d}"
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P001", ym, 3000000, 500000, 400000, 1000000),
            )
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P002", ym, 1500000, 300000, 200000, 500000),
            )
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P003", ym, 1000000, 200000, 100000, 300000),
            )
        for m in range(1, 4):
            ym = f"2027-{m:02d}"
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P001", ym, 3000000, 500000, 400000, 1000000),
            )
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P002", ym, 1500000, 300000, 200000, 500000),
            )
            self.db.execute(
                "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
                ("P003", ym, 1000000, 200000, 100000, 300000),
            )

        self.db.commit()


# ========================
# テスト: 契約状態別の集計
# ========================


class TestByStatus(ForecastTestBase):
    def test_by_status_keys(self):
        """結果にby_statusが含まれる"""
        result = revenue_forecast_weighted(self.db)
        self.assertIn("by_status", result)
        statuses = {s["contract_status"] for s in result["by_status"]}
        self.assertEqual(statuses, {"signed", "delayed", "planned"})

    def test_missing_status_returned_with_zero(self):
        """案件が存在しない契約状態も0件・0円で返される"""
        self.db.execute(
            "DELETE FROM budget_plan WHERE project_id = 'P003'"
        )
        self.db.execute(
            "DELETE FROM project_budgets WHERE project_id = 'P003'"
        )
        self.db.execute(
            "DELETE FROM projects WHERE id = 'P003'"
        )
        self.db.commit()

        result = revenue_forecast_weighted(self.db)
        planned = [s for s in result["by_status"] if s["contract_status"] == "planned"][0]
        self.assertEqual(planned["project_count"], 0)
        self.assertEqual(planned["planned_revenue"], 0)

    def test_signed_revenue(self):
        """signed案件の売上合計"""
        result = revenue_forecast_weighted(self.db)
        signed = [s for s in result["by_status"] if s["contract_status"] == "signed"][0]
        # P001: 1,000,000 x 12 = 12,000,000
        self.assertEqual(signed["planned_revenue"], 12000000)
        self.assertEqual(signed["project_count"], 1)

    def test_delayed_revenue(self):
        """delayed案件の売上合計"""
        result = revenue_forecast_weighted(self.db)
        delayed = [s for s in result["by_status"] if s["contract_status"] == "delayed"][0]
        # P002: 500,000 x 12 = 6,000,000
        self.assertEqual(delayed["planned_revenue"], 6000000)

    def test_planned_revenue(self):
        """planned案件の売上合計"""
        result = revenue_forecast_weighted(self.db)
        planned = [s for s in result["by_status"] if s["contract_status"] == "planned"][0]
        # P003: 300,000 x 12 = 3,600,000
        self.assertEqual(planned["planned_revenue"], 3600000)

    def test_revenue_target(self):
        """売上目標が返される"""
        result = revenue_forecast_weighted(self.db)
        self.assertEqual(result["revenue_target"], 200000000)


# ========================
# テスト: シナリオ別予測
# ========================


class TestScenarios(ForecastTestBase):
    def test_scenario_keys(self):
        """3シナリオが含まれる"""
        result = revenue_forecast_weighted(self.db)
        self.assertIn("scenarios", result)
        self.assertIn("optimistic", result["scenarios"])
        self.assertIn("standard", result["scenarios"])
        self.assertIn("pessimistic", result["scenarios"])

    def test_optimistic_scenario(self):
        """楽観シナリオ: signed=100%, planned=100%, delayed=80%"""
        result = revenue_forecast_weighted(self.db)
        opt = result["scenarios"]["optimistic"]
        # signed: 12,000,000 * 1.0 = 12,000,000
        # delayed: 6,000,000 * 0.8 = 4,800,000
        # planned: 3,600,000 * 1.0 = 3,600,000
        # total: 20,400,000
        self.assertEqual(opt["forecast_revenue"], 20400000)

    def test_standard_scenario(self):
        """標準シナリオ: signed=100%, planned=70%, delayed=50%"""
        result = revenue_forecast_weighted(self.db)
        std = result["scenarios"]["standard"]
        # signed: 12,000,000 * 1.0 = 12,000,000
        # delayed: 6,000,000 * 0.5 = 3,000,000
        # planned: 3,600,000 * 0.7 = 2,520,000
        # total: 17,520,000
        self.assertEqual(std["forecast_revenue"], 17520000)

    def test_pessimistic_scenario(self):
        """悲観シナリオ: signed=100%, planned=40%, delayed=20%"""
        result = revenue_forecast_weighted(self.db)
        pess = result["scenarios"]["pessimistic"]
        # signed: 12,000,000 * 1.0 = 12,000,000
        # delayed: 6,000,000 * 0.2 = 1,200,000
        # planned: 3,600,000 * 0.4 = 1,440,000
        # total: 14,640,000
        self.assertEqual(pess["forecast_revenue"], 14640000)

    def test_achievement_rate(self):
        """達成率が含まれる"""
        result = revenue_forecast_weighted(self.db)
        std = result["scenarios"]["standard"]
        # 17,520,000 / 200,000,000 = 0.088
        self.assertIn("achievement_rate", std)
        self.assertAlmostEqual(std["achievement_rate"], 0.088, places=3)

    def test_ordering(self):
        """楽観 >= 標準 >= 悲観"""
        result = revenue_forecast_weighted(self.db)
        s = result["scenarios"]
        self.assertGreaterEqual(
            s["optimistic"]["forecast_revenue"],
            s["standard"]["forecast_revenue"],
        )
        self.assertGreaterEqual(
            s["standard"]["forecast_revenue"],
            s["pessimistic"]["forecast_revenue"],
        )


if __name__ == "__main__":
    unittest.main()

"""アサイン整合性チェックのテスト"""

import sqlite3
from pathlib import Path
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from utils.validation import (
    check_allocation_exceeded,
    check_dispatch_outside_contract,
    check_assignment_to_closed_project,
    check_unassigned_active_project,
    check_pto_exceeded,
    check_missing_capacity,
    check_missing_calendar,
    run_all_validations,
)
from init_db import DDL, VIEWS


class ValidationTestBase(unittest.TestCase):
    """Test base with setup/teardown for in-memory DB"""

    def setUp(self):
        """Create in-memory database with schema"""
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DDL)
        self.db.executescript(VIEWS)
        self.db.commit()
        self._setup_base_data()

    def tearDown(self):
        """Close database"""
        self.db.close()

    def _setup_base_data(self):
        """Initialize base data (fiscal year, calendar, members, projects)"""
        # Fiscal year
        self.db.execute(
            "INSERT INTO fiscal_year VALUES (?, ?, ?, ?, ?)",
            (2026, "2026-04-01", "2027-03-31", 200000000, 15),
        )

        # Calendar (12 months)
        for m in range(1, 13):
            year_month = f"2026-{m:02d}"
            working_days = 20  # Default
            self.db.execute(
                "INSERT INTO monthly_calendar VALUES (?, ?)",
                (year_month, working_days),
            )

        # Members
        self.db.execute(
            """INSERT INTO members VALUES
            ('M001', '田中太郎', 'internal', 'PM', 'senior', 800000, NULL, 1.0, 0, '2020-01-01', NULL, NULL, NULL)
            """
        )
        self.db.execute(
            """INSERT INTO members VALUES
            ('M002', '佐藤次郎', 'internal', 'SE', 'mid', 600000, NULL, 1.0, 0, '2020-06-01', NULL, NULL, NULL)
            """
        )
        self.db.execute(
            """INSERT INTO members VALUES
            ('D001', '鈴木花子', 'dispatch', 'SE', 'mid', 0, 4000, 1.0, 0, NULL, '2026-06-01', '2026-12-31', NULL)
            """
        )

        # Projects
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P001', 'A社基幹システム刷新', 'A社', 'in_progress', 'high', '2026-04-01', '2027-03-31',
             'M001', 'signed', '2026-04-01', '2026-04-01', NULL, 50000000, NULL, NULL)
            """
        )
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P002', 'B社会計システム導入', 'B社', 'planned', 'medium', '2026-08-01', '2027-03-31',
             'M001', 'delayed', '2026-06-01', '2026-08-01', NULL, 30000000, NULL, NULL)
            """
        )
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P003', 'C社ECサイト構築', 'C社', 'completed', 'medium', '2025-01-01', '2026-03-31',
             'M002', 'signed', '2025-01-01', '2025-01-01', NULL, 20000000, NULL, NULL)
            """
        )

        # Project budgets
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P001', 40000000, 5000000, 5000000)",
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P002', 20000000, 5000000, 5000000)",
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P003', 15000000, 3000000, 2000000)",
        )

        # Member capacity (basic data for all members x all months)
        for m in range(1, 13):
            year_month = f"2026-{m:02d}"
            for member_id in ["M001", "M002", "D001"]:
                self.db.execute(
                    "INSERT INTO member_capacity VALUES (?, ?, 0, 0)",
                    (member_id, year_month),
                )

        self.db.commit()


# ========================
# テスト1: 個人月別アロケーション超過
# ========================


class TestAllocationExceeded(ValidationTestBase):
    def test_normal_allocation(self):
        """正常: 1.0以下"""
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.5, "PM"),
        )
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        self.db.commit()

        issues = check_allocation_exceeded(self.db, "2026-04")
        self.assertEqual(len(issues), 0)

    def test_allocation_at_limit(self):
        """正常: ちょうど1.0"""
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        self.db.commit()

        issues = check_allocation_exceeded(self.db, "2026-04")
        self.assertEqual(len(issues), 0)

    def test_allocation_exceeded(self):
        """異常: 1.0超過"""
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.7, "PM"),
        )
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        self.db.commit()

        issues = check_allocation_exceeded(self.db, "2026-04")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "警告")
        self.assertIn("M001", issues[0]["message"])
        self.assertIn("1.1", issues[0]["message"])

    def test_allocation_at_max(self):
        """異常: 上限1.5は1.0超なので警告"""
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.5, "PM"),
        )
        self.db.commit()

        issues = check_allocation_exceeded(self.db, "2026-04")
        # 1.5 > 1.0 なので警告が出る
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "警告")


# ========================
# テスト2: 派遣の契約期間外アサイン
# ========================


class TestDispatchOutsideContract(ValidationTestBase):
    def test_dispatch_within_contract(self):
        """正常: 契約期間内"""
        # D001: 2026-06-01 ～ 2026-12-31
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-06", 1.0, "SE"),
        )
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-12", 1.0, "SE"),
        )
        self.db.commit()

        issues = check_dispatch_outside_contract(self.db)
        self.assertEqual(len(issues), 0)

    def test_dispatch_before_contract(self):
        """異常: 契約開始前にアサイン"""
        # D001: 2026-06-01 契約開始なのに、2026-04, 2026-05 にアサイン
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-04", 1.0, "SE"),
        )
        self.db.commit()

        issues = check_dispatch_outside_contract(self.db)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "警告")
        self.assertTrue(
            "D001" in issues[0]["message"] or "鈴木花子" in issues[0]["message"]
        )

    def test_dispatch_after_contract(self):
        """異常: 契約終了後にアサイン"""
        # D001: 2026-12-31 契約終了なのに、2027-01 にアサイン
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2027-01", 1.0, "SE"),
        )
        self.db.commit()

        issues = check_dispatch_outside_contract(self.db)
        self.assertEqual(len(issues), 1)


# ========================
# テスト3: 終了案件へのアサイン
# ========================


class TestAssignmentToClosed(ValidationTestBase):
    def test_assignment_to_active_project(self):
        """正常: 進行中の案件へアサイン"""
        # P001 is in_progress
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        self.db.commit()

        issues = check_assignment_to_closed_project(self.db)
        self.assertEqual(len(issues), 0)

    def test_assignment_to_completed_project(self):
        """異常: 完了済み案件へアサイン"""
        # P003 is completed
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P003", "2026-04", 1.0, "PM"),
        )
        self.db.commit()

        issues = check_assignment_to_closed_project(self.db)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["level"], "警告")
        self.assertTrue(
            "P003" in issues[0]["message"] or "C社ECサイト" in issues[0]["message"]
        )

    def test_assignment_to_cancelled_project(self):
        """異常: キャンセル案件へアサイン"""
        self.db.execute(
            """INSERT INTO projects VALUES
            ('P004', 'D社システム', 'D社', 'cancelled', 'low', '2026-05-01', '2026-06-30',
             NULL, 'planned', '2026-05-01', '2026-05-01', NULL, 10000000, NULL, NULL)
            """
        )
        self.db.execute(
            "INSERT INTO project_budgets VALUES ('P004', 5000000, 2000000, 1000000)",
        )
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P004", "2026-05", 0.5, "PM"),
        )
        self.db.commit()

        issues = check_assignment_to_closed_project(self.db)
        self.assertEqual(len(issues), 1)


# ========================
# テスト4: 未アサイン案件
# ========================


class TestUnassignedProject(ValidationTestBase):
    def test_active_project_with_assignment(self):
        """正常: 進行中案件にアサインあり"""
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        self.db.commit()

        issues = check_unassigned_active_project(self.db, "2026-04")
        # P001 has assignment, P002 is not started yet (planned status), no issue
        self.assertEqual(len([i for i in issues if "P001" in str(i)]), 0)

    def test_active_project_without_assignment(self):
        """異常: 進行中案件にアサインなし"""
        # P001 is in_progress but no assignment in 2026-04
        issues = check_unassigned_active_project(self.db, "2026-04")
        p001_issues = [i for i in issues if "P001" in str(i)]
        self.assertEqual(len(p001_issues), 1)
        self.assertEqual(p001_issues[0]["level"], "注意")

    def test_planned_project_no_assignment_yet_ok(self):
        """正常: 計画段階の案件はまだアサイン不要"""
        # P002 は planned かつ actual_work_start が 2026-08-01 のため、
        # 開始前の 2026-04 時点では未アサイン警告の対象にしない
        issues = check_unassigned_active_project(self.db, "2026-04")
        p002_issues = [i for i in issues if "P002" in str(i)]
        self.assertEqual(len(p002_issues), 0)


# ========================
# テスト5: 有給超過
# ========================


class TestPtoExceeded(ValidationTestBase):
    def test_normal_pto(self):
        """正常: PTO日数 <= working_days"""
        # Default: planned_pto_days=0, working_days=20
        issues = check_pto_exceeded(self.db)
        self.assertEqual(len(issues), 0)

    def test_pto_exceeded(self):
        """異常: PTO日数 > working_days"""
        # Update M001's April pto to 25 (exceed 20)
        self.db.execute(
            "UPDATE member_capacity SET planned_pto_days = 25 WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        self.db.commit()

        issues = check_pto_exceeded(self.db)
        pto_issues = [i for i in issues if "M001" in str(i) and "2026-04" in str(i)]
        self.assertGreaterEqual(len(pto_issues), 1)
        self.assertEqual(pto_issues[0]["level"], "警告")

    def test_pto_equal_working_days(self):
        """正常: PTO日数 = working_days (境界値)"""
        self.db.execute(
            "UPDATE member_capacity SET planned_pto_days = 20 WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        self.db.commit()

        issues = check_pto_exceeded(self.db)
        pto_issues = [i for i in issues if "M001" in str(i) and "2026-04" in str(i)]
        self.assertEqual(len(pto_issues), 0)


# ========================
# テスト6: キャパシティ未定義
# ========================


class TestMissingCapacity(ValidationTestBase):
    def test_capacity_defined_for_all(self):
        """正常: 全 active メンバーの全月に capacity がある"""
        # Already populated in fixture
        issues = check_missing_capacity(self.db)
        self.assertEqual(len(issues), 0)

    def test_missing_capacity_for_month(self):
        """異常: active メンバーで月の capacity が未定義"""
        # Delete M001's April capacity
        self.db.execute(
            "DELETE FROM member_capacity WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        self.db.commit()

        issues = check_missing_capacity(self.db)
        capacity_issues = [
            i for i in issues if "M001" in str(i) and "2026-04" in str(i)
        ]
        self.assertEqual(len(capacity_issues), 1)
        self.assertEqual(capacity_issues[0]["level"], "注意")

    def test_missing_capacity_for_internal_member(self):
        """異常: internal メンバーは capacity が必須"""
        self.db.execute(
            "DELETE FROM member_capacity WHERE member_id = 'M002' AND year_month = '2026-06'",
        )
        self.db.commit()

        issues = check_missing_capacity(self.db)
        self.assertGreaterEqual(len([i for i in issues if "M002" in str(i)]), 1)


# ========================
# テスト7: カレンダー未定義
# ========================


class TestMissingCalendar(ValidationTestBase):
    def test_calendar_defined(self):
        """正常: 全 year_month にカレンダーがある"""
        issues = check_missing_calendar(self.db)
        self.assertEqual(len(issues), 0)

    def test_missing_calendar_for_assignment(self):
        """異常: assignments_plan の year_month が calendar にない"""
        # Add assignment in a month without calendar
        # Use 2027-01 which doesn't have calendar by default
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2027-01", 0.5, "PM"),
        )
        self.db.commit()

        issues = check_missing_calendar(self.db)
        cal_issues = [i for i in issues if "2027-01" in str(i)]
        self.assertEqual(len(cal_issues), 1)
        self.assertEqual(cal_issues[0]["level"], "警告")


# ========================
# テスト8: 全チェック統合
# ========================


class TestAllValidations(ValidationTestBase):
    def test_no_issues(self):
        """正常: 問題なし"""
        # P001はin_progressなのでアサイン必須
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.5, "PM"),
        )
        self.db.commit()
        issues = run_all_validations(self.db, "2026-04")
        self.assertEqual(len(issues), 0)

    def test_multiple_issues(self):
        """異常: 複数の問題を検出"""
        # 1. Allocation exceeded
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.7, "PM"),
        )
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        # 2. Assignment to completed project
        self.db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M002", "P003", "2026-04", 0.5, "SE"),
        )
        self.db.commit()

        issues = run_all_validations(self.db, "2026-04")
        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(any(i["level"] == "警告" for i in issues))


if __name__ == "__main__":
    unittest.main()

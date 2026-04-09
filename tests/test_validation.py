"""アサイン整合性チェックのテスト"""

import sqlite3
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
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


@pytest.fixture
def db() -> sqlite3.Connection:
    """In-memory SQLite database with schema initialized"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    conn.executescript(VIEWS)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def db_with_base_data(db: sqlite3.Connection) -> sqlite3.Connection:
    """Database with basic master data and calendar"""
    # Fiscal year
    db.execute(
        "INSERT INTO fiscal_year VALUES (?, ?, ?, ?, ?)",
        (2026, "2026-04-01", "2027-03-31", 200000000, 15),
    )

    # Calendar (12 months)
    for m in range(1, 13):
        year_month = f"2026-{m:02d}"
        working_days = 20  # Default
        db.execute(
            "INSERT INTO monthly_calendar VALUES (?, ?)",
            (year_month, working_days),
        )

    # Members
    db.execute(
        """INSERT INTO members VALUES
        ('M001', '田中太郎', 'internal', 'PM', 'senior', 800000, NULL, 1.0, 0, '2020-01-01', NULL, NULL, NULL)
        """
    )
    db.execute(
        """INSERT INTO members VALUES
        ('M002', '佐藤次郎', 'internal', 'SE', 'mid', 600000, NULL, 1.0, 0, '2020-06-01', NULL, NULL, NULL)
        """
    )
    db.execute(
        """INSERT INTO members VALUES
        ('D001', '鈴木花子', 'dispatch', 'SE', 'mid', 0, 4000, 1.0, 0, NULL, '2026-06-01', '2026-12-31', NULL)
        """
    )

    # Projects
    db.execute(
        """INSERT INTO projects VALUES
        ('P001', 'A社基幹システム刷新', 'A社', 'in_progress', 'high', '2026-04-01', '2027-03-31',
         'M001', 'signed', '2026-04-01', '2026-04-01', NULL, 50000000, NULL, NULL)
        """
    )
    db.execute(
        """INSERT INTO projects VALUES
        ('P002', 'B社会計システム導入', 'B社', 'planned', 'medium', '2026-08-01', '2027-03-31',
         'M001', 'delayed', '2026-06-01', '2026-08-01', NULL, 30000000, NULL, NULL)
        """
    )
    db.execute(
        """INSERT INTO projects VALUES
        ('P003', 'C社ECサイト構築', 'C社', 'completed', 'medium', '2025-01-01', '2026-03-31',
         'M002', 'signed', '2025-01-01', '2025-01-01', NULL, 20000000, NULL, NULL)
        """
    )

    # Project budgets
    db.execute(
        "INSERT INTO project_budgets VALUES ('P001', 40000000, 5000000, 5000000)",
    )
    db.execute(
        "INSERT INTO project_budgets VALUES ('P002', 20000000, 5000000, 5000000)",
    )
    db.execute(
        "INSERT INTO project_budgets VALUES ('P003', 15000000, 3000000, 2000000)",
    )

    # Member capacity (basic data for all members x all months)
    for m in range(1, 13):
        year_month = f"2026-{m:02d}"
        for member_id in ["M001", "M002", "D001"]:
            db.execute(
                "INSERT INTO member_capacity VALUES (?, ?, 0, 0)",
                (member_id, year_month),
            )

    db.commit()
    return db


# ========================
# テスト1: 個人月別アロケーション超過
# ========================


class TestAllocationExceeded:
    def test_normal_allocation(self, db_with_base_data):
        """正常: 1.0以下"""
        db = db_with_base_data
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.5, "PM"),
        )
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        db.commit()

        issues = check_allocation_exceeded(db, "2026-04")
        assert len(issues) == 0

    def test_allocation_at_limit(self, db_with_base_data):
        """正常: ちょうど1.0"""
        db = db_with_base_data
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        db.commit()

        issues = check_allocation_exceeded(db, "2026-04")
        assert len(issues) == 0

    def test_allocation_exceeded(self, db_with_base_data):
        """異常: 1.0超過"""
        db = db_with_base_data
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.7, "PM"),
        )
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        db.commit()

        issues = check_allocation_exceeded(db, "2026-04")
        assert len(issues) == 1
        assert issues[0]["level"] == "警告"
        assert "M001" in issues[0]["message"]
        assert "1.1" in issues[0]["message"]

    def test_allocation_at_max(self, db_with_base_data):
        """正常: 上限1.5"""
        db = db_with_base_data
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.5, "PM"),
        )
        db.commit()

        issues = check_allocation_exceeded(db, "2026-04")
        assert len(issues) == 0


# ========================
# テスト2: 派遣の契約期間外アサイン
# ========================


class TestDispatchOutsideContract:
    def test_dispatch_within_contract(self, db_with_base_data):
        """正常: 契約期間内"""
        db = db_with_base_data
        # D001: 2026-06-01 ～ 2026-12-31
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-06", 1.0, "SE"),
        )
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-12", 1.0, "SE"),
        )
        db.commit()

        issues = check_dispatch_outside_contract(db)
        assert len(issues) == 0

    def test_dispatch_before_contract(self, db_with_base_data):
        """異常: 契約開始前にアサイン"""
        db = db_with_base_data
        # D001: 2026-06-01 契約開始なのに、2026-04, 2026-05 にアサイン
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2026-04", 1.0, "SE"),
        )
        db.commit()

        issues = check_dispatch_outside_contract(db)
        assert len(issues) == 1
        assert issues[0]["level"] == "警告"
        assert "D001" in issues[0]["message"] or "鈴木花子" in issues[0]["message"]

    def test_dispatch_after_contract(self, db_with_base_data):
        """異常: 契約終了後にアサイン"""
        db = db_with_base_data
        # D001: 2026-12-31 契約終了なのに、2027-01 にアサイン
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("D001", "P001", "2027-01", 1.0, "SE"),
        )
        db.commit()

        issues = check_dispatch_outside_contract(db)
        assert len(issues) == 1


# ========================
# テスト3: 終了案件へのアサイン
# ========================


class TestAssignmentToClosed:
    def test_assignment_to_active_project(self, db_with_base_data):
        """正常: 進行中の案件へアサイン"""
        db = db_with_base_data
        # P001 is in_progress
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        db.commit()

        issues = check_assignment_to_closed_project(db)
        assert len(issues) == 0

    def test_assignment_to_completed_project(self, db_with_base_data):
        """異常: 完了済み案件へアサイン"""
        db = db_with_base_data
        # P003 is completed
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P003", "2026-04", 1.0, "PM"),
        )
        db.commit()

        issues = check_assignment_to_closed_project(db)
        assert len(issues) == 1
        assert issues[0]["level"] == "警告"
        assert "P003" in issues[0]["message"] or "C社ECサイト" in issues[0]["message"]

    def test_assignment_to_cancelled_project(self, db_with_base_data):
        """異常: キャンセル案件へアサイン"""
        db = db_with_base_data
        db.execute(
            """INSERT INTO projects VALUES
            ('P004', 'D社システム', 'D社', 'cancelled', 'low', '2026-05-01', '2026-06-30',
             NULL, 'planned', '2026-05-01', '2026-05-01', NULL, 10000000, NULL, NULL)
            """
        )
        db.execute(
            "INSERT INTO project_budgets VALUES ('P004', 5000000, 2000000, 1000000)",
        )
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P004", "2026-05", 0.5, "PM"),
        )
        db.commit()

        issues = check_assignment_to_closed_project(db)
        assert len(issues) == 1


# ========================
# テスト4: 未アサイン案件
# ========================


class TestUnassignedProject:
    def test_active_project_with_assignment(self, db_with_base_data):
        """正常: 進行中案件にアサインあり"""
        db = db_with_base_data
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 1.0, "PM"),
        )
        db.commit()

        issues = check_unassigned_active_project(db, "2026-04")
        # P001 has assignment, P002 is not started yet (planned status), no issue
        assert len([i for i in issues if "P001" in str(i)]) == 0

    def test_active_project_without_assignment(self, db_with_base_data):
        """異常: 進行中案件にアサインなし"""
        db = db_with_base_data
        # P001 is in_progress but no assignment in 2026-04
        issues = check_unassigned_active_project(db, "2026-04")
        p001_issues = [i for i in issues if "P001" in str(i)]
        assert len(p001_issues) == 1
        assert p001_issues[0]["level"] == "注意"

    def test_planned_project_no_assignment_yet_ok(self, db_with_base_data):
        """正常: 計画段階の案件はまだアサイン不要"""
        db = db_with_base_data
        # P002 is planned, so maybe no assignment is expected in early months
        # Actually, let me check the logic - 'planned' and 'in_progress' should be checked
        # P002 starts 2026-08-01 (actual_work_start), so 2026-04 is before start
        issues = check_unassigned_active_project(db, "2026-04")
        p002_issues = [i for i in issues if "P002" in str(i)]
        # Should be 0 because actual_work_start is 2026-08-01, after 2026-04
        assert len(p002_issues) == 0


# ========================
# テスト5: 有給超過
# ========================


class TestPtoExceeded:
    def test_normal_pto(self, db_with_base_data):
        """正常: PTO日数 <= working_days"""
        db = db_with_base_data
        # Default: planned_pto_days=0, working_days=20
        issues = check_pto_exceeded(db)
        assert len(issues) == 0

    def test_pto_exceeded(self, db_with_base_data):
        """異常: PTO日数 > working_days"""
        db = db_with_base_data
        # Update M001's April pto to 25 (exceed 20)
        db.execute(
            "UPDATE member_capacity SET planned_pto_days = 25 WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        db.commit()

        issues = check_pto_exceeded(db)
        pto_issues = [i for i in issues if "M001" in str(i) and "2026-04" in str(i)]
        assert len(pto_issues) >= 1
        assert pto_issues[0]["level"] == "警告"

    def test_pto_equal_working_days(self, db_with_base_data):
        """正常: PTO日数 = working_days (境界値)"""
        db = db_with_base_data
        db.execute(
            "UPDATE member_capacity SET planned_pto_days = 20 WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        db.commit()

        issues = check_pto_exceeded(db)
        pto_issues = [i for i in issues if "M001" in str(i) and "2026-04" in str(i)]
        assert len(pto_issues) == 0


# ========================
# テスト6: キャパシティ未定義
# ========================


class TestMissingCapacity:
    def test_capacity_defined_for_all(self, db_with_base_data):
        """正常: 全 active メンバーの全月に capacity がある"""
        db = db_with_base_data
        # Already populated in fixture
        issues = check_missing_capacity(db)
        assert len(issues) == 0

    def test_missing_capacity_for_month(self, db_with_base_data):
        """異常: active メンバーで月の capacity が未定義"""
        db = db_with_base_data
        # Delete M001's April capacity
        db.execute(
            "DELETE FROM member_capacity WHERE member_id = 'M001' AND year_month = '2026-04'",
        )
        db.commit()

        issues = check_missing_capacity(db)
        capacity_issues = [
            i for i in issues if "M001" in str(i) and "2026-04" in str(i)
        ]
        assert len(capacity_issues) == 1
        assert capacity_issues[0]["level"] == "注意"

    def test_missing_capacity_for_internal_member(self, db_with_base_data):
        """異常: internal メンバーは capacity が必須"""
        db = db_with_base_data
        db.execute(
            "DELETE FROM member_capacity WHERE member_id = 'M002' AND year_month = '2026-06'",
        )
        db.commit()

        issues = check_missing_capacity(db)
        assert len([i for i in issues if "M002" in str(i)]) >= 1


# ========================
# テスト7: カレンダー未定義
# ========================


class TestMissingCalendar:
    def test_calendar_defined(self, db_with_base_data):
        """正常: 全 year_month にカレンダーがある"""
        db = db_with_base_data
        issues = check_missing_calendar(db)
        assert len(issues) == 0

    def test_missing_calendar_for_assignment(self, db_with_base_data):
        """異常: assignments_plan の year_month が calendar にない"""
        db = db_with_base_data
        # Delete 2026-04 from calendar
        db.execute("DELETE FROM monthly_calendar WHERE year_month = '2026-04'",)
        db.commit()

        # Add assignment in 2026-04
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.5, "PM"),
        )
        db.commit()

        issues = check_missing_calendar(db)
        cal_issues = [i for i in issues if "2026-04" in str(i)]
        assert len(cal_issues) == 1
        assert cal_issues[0]["level"] == "警告"


# ========================
# テスト8: 全チェック統合
# ========================


class TestAllValidations:
    def test_no_issues(self, db_with_base_data):
        """正常: 問題なし"""
        db = db_with_base_data
        issues = run_all_validations(db, "2026-04")
        assert len(issues) == 0

    def test_multiple_issues(self, db_with_base_data):
        """異常: 複数の問題を検出"""
        db = db_with_base_data
        # 1. Allocation exceeded
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P001", "2026-04", 0.7, "PM"),
        )
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M001", "P002", "2026-04", 0.4, "PM"),
        )
        # 2. Assignment to completed project
        db.execute(
            "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
            ("M002", "P003", "2026-04", 0.5, "SE"),
        )
        db.commit()

        issues = run_all_validations(db, "2026-04")
        assert len(issues) >= 2
        assert any(i["level"] == "警告" for i in issues)

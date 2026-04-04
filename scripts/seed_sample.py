"""サンプルデータの投入スクリプト"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "project_mgmt.db"


def seed(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")

    # 再実行可能にするため、子テーブルから順に全データ削除
    for table in [
        "progress",
        "budget_actual",
        "budget_plan",
        "assignments_actual",
        "assignments_plan",
        "milestones",
        "project_required_skills",
        "project_budgets",
        "member_capacity",
        "member_skills",
        "projects",
        "members",
        "monthly_calendar",
        "fiscal_year",
    ]:
        conn.execute(f"DELETE FROM {table}")

    conn.execute("PRAGMA foreign_keys = ON")

    # --- 年度設定 ---
    conn.execute("""
        INSERT INTO fiscal_year VALUES
        (2026, '2026-04-01', '2027-03-31', 200000000, 15)
    """)

    # --- 月別カレンダー（2026年度: 4月〜翌3月） ---
    calendar = [
        ("2026-04", 22),  # 4月
        ("2026-05", 19),  # 5月（GW）
        ("2026-06", 22),  # 6月
        ("2026-07", 22),  # 7月
        ("2026-08", 20),  # 8月（お盆）
        ("2026-09", 21),  # 9月（祝日多め）
        ("2026-10", 22),  # 10月
        ("2026-11", 20),  # 11月（祝日）
        ("2026-12", 20),  # 12月（年末）
        ("2027-01", 19),  # 1月（年始）
        ("2027-02", 20),  # 2月
        ("2027-03", 22),  # 3月
    ]
    conn.executemany(
        "INSERT INTO monthly_calendar (year_month, working_days) VALUES (?, ?)",
        calendar,
    )

    # --- 人員マスタ（正社員2名 + 派遣1名） ---
    members = [
        (
            "M001",
            "田中太郎",
            "internal",
            "PM",
            "senior",
            800000,
            None,
            1.0,
            20,
            "2020-04-01",
            None,
            None,
            None,
        ),
        (
            "M002",
            "佐藤次郎",
            "internal",
            "SE",
            "mid",
            600000,
            None,
            1.0,
            10,
            "2022-04-01",
            None,
            None,
            None,
        ),
        (
            "D001",
            "鈴木花子",
            "dispatch",
            "SE",
            "mid",
            650000,
            4000,
            1.0,
            0,
            None,
            "2026-06-01",
            "2027-03-31",
            "A社向け増員",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO members
        (id, name, type, role, grade, unit_cost, hourly_rate, max_capacity,
         avg_overtime_hours, join_date, contract_start, contract_end, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        members,
    )

    # --- メンバースキル ---
    skills = [
        ("M001", "Java", "senior"),
        ("M001", "AWS", "senior"),
        ("M001", "PM", "senior"),
        ("M002", "Java", "mid"),
        ("M002", "Python", "mid"),
        ("M002", "SQL", "mid"),
        ("D001", "Java", "mid"),
        ("D001", "SQL", "mid"),
    ]
    conn.executemany("INSERT INTO member_skills VALUES (?, ?, ?)", skills)

    # --- メンバーキャパシティ（12ヶ月分） ---
    capacity_rows = []
    for ym, _ in calendar:
        # M001: 8月に有給3日、他は月1日。残業はデフォルト(20h)を使用
        pto_m001 = 3 if ym == "2026-08" else 1
        capacity_rows.append(("M001", ym, pto_m001, None))

        # M002: 12月に有給5日、他は月1日。残業はデフォルト(10h)
        pto_m002 = 5 if ym == "2026-12" else 1
        capacity_rows.append(("M002", ym, pto_m002, None))

        # D001: 6月からの契約。有給なし、残業なし
        if ym >= "2026-06":
            capacity_rows.append(("D001", ym, 0, 0))

    conn.executemany(
        "INSERT INTO member_capacity VALUES (?, ?, ?, ?)",
        capacity_rows,
    )

    # --- 案件マスタ（通常・遅延・年度跨ぎの3件） ---
    projects = [
        # P001: 通常案件
        (
            "P001",
            "A社基幹システム刷新",
            "A株式会社",
            "in_progress",
            "high",
            "2026-04-01",
            "2027-03-31",
            "M001",
            "signed",
            "2026-04-01",
            "2026-04-01",
            None,
            None,
            None,
            None,
        ),
        # P002: 契約遅延案件（4月開始予定が8月に遅延）
        (
            "P002",
            "B社会計システム導入",
            "B株式会社",
            "planned",
            "high",
            "2026-04-01",
            "2027-03-31",
            "M001",
            "delayed",
            "2026-04-01",
            "2026-08-01",
            "先方の社内稟議が遅延。8月締結見込み",
            None,
            None,
            None,
        ),
        # P003: 年度跨ぎ案件
        (
            "P003",
            "C社ECサイト構築",
            "C株式会社",
            "in_progress",
            "medium",
            "2026-10-01",
            "2027-09-30",
            "M002",
            "signed",
            "2026-10-01",
            "2026-10-01",
            None,
            8000000,
            9000000,
            None,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO projects
        (id, name, client, status, priority, start_date, end_date, pm,
         contract_status, original_work_start, actual_work_start, delay_note,
         budget_this_fy, budget_next_fy, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        projects,
    )

    # --- 予算内訳 ---
    budgets = [
        ("P001", 10000000, 3000000, 2000000),  # total: 15,000,000
        ("P002", 8000000, 3000000, 1000000),  # total: 12,000,000
        ("P003", 10000000, 5000000, 2000000),  # total: 17,000,000
    ]
    conn.executemany(
        "INSERT INTO project_budgets (project_id, labor_cost, outsource_cost, expense) VALUES (?, ?, ?, ?)",
        budgets,
    )

    # --- 案件の必要スキル ---
    required_skills = [
        ("P001", "Java", "senior", 2),
        ("P001", "AWS", "mid", 1),
        ("P001", "PM", "senior", 1),
        ("P002", "Java", "mid", 2),
        ("P002", "SQL", "mid", 1),
        ("P003", "Python", "mid", 2),
        ("P003", "SQL", "mid", 1),
    ]
    conn.executemany(
        "INSERT INTO project_required_skills VALUES (?, ?, ?, ?)",
        required_skills,
    )

    # --- マイルストーン ---
    milestones = [
        ("P001-MS01", "P001", "要件定義完了", "2026-06-30", "in_progress", 30),
        ("P001-MS02", "P001", "基本設計完了", "2026-09-30", "not_started", 0),
        ("P001-MS03", "P001", "結合テスト完了", "2027-01-31", "not_started", 0),
        ("P002-MS01", "P002", "要件定義完了", "2026-10-31", "not_started", 0),
        ("P002-MS02", "P002", "基本設計完了", "2027-01-31", "not_started", 0),
        ("P003-MS01", "P003", "要件定義完了", "2026-12-31", "not_started", 0),
        ("P003-MS02", "P003", "リリース", "2027-06-30", "not_started", 0),
    ]
    conn.executemany(
        "INSERT INTO milestones VALUES (?, ?, ?, ?, ?, ?)",
        milestones,
    )

    # --- アサイン計画（12ヶ月分） ---
    plan_rows = []
    for ym, _ in calendar:
        # M001: P001に0.5 (通年)
        plan_rows.append(("M001", "P001", ym, 0.5, "PM"))

        # M001: P002に0.3 (8月以降、遅延で着手可能になってから)
        if ym >= "2026-08":
            plan_rows.append(("M001", "P002", ym, 0.3, "PM"))

        # M002: P001に0.8 (4-9月)、P003に0.8 (10月以降)
        if ym < "2026-10":
            plan_rows.append(("M002", "P001", ym, 0.8, "SE"))
        else:
            plan_rows.append(("M002", "P001", ym, 0.3, "SE"))
            plan_rows.append(("M002", "P003", ym, 0.6, "SE"))

        # D001: P001に1.0 (6月以降、契約開始後)
        if ym >= "2026-06":
            plan_rows.append(("D001", "P001", ym, 1.0, "SE"))

    conn.executemany(
        "INSERT INTO assignments_plan VALUES (?, ?, ?, ?, ?)",
        plan_rows,
    )

    # --- 予算計画（12ヶ月分） ---
    budget_plan_rows = []
    for ym, _ in calendar:
        # P001: 月125万（人件費83万/外注25万/経費17万）、売上150万
        budget_plan_rows.append(("P001", ym, 830000, 250000, 170000, 1500000))

        # P002: 8月以降のみ（遅延）、月150万（人件費100万/外注37.5万/経費12.5万）
        if ym >= "2026-08":
            budget_plan_rows.append(("P002", ym, 1000000, 375000, 125000, 1800000))

        # P003: 10月以降、月140万
        if ym >= "2026-10":
            budget_plan_rows.append(("P003", ym, 830000, 420000, 170000, 1600000))

    conn.executemany(
        "INSERT INTO budget_plan VALUES (?, ?, ?, ?, ?, ?)",
        budget_plan_rows,
    )

    # --- 4月の実績データ（サンプル） ---

    # アサイン実績（4月分のみ）
    actual_assignments = [
        ("M001", "P001", "2026-04", 88, "PM", "teamspirit", None),
        ("M002", "P001", "2026-04", 140, "SE", "teamspirit", None),
    ]
    conn.executemany(
        "INSERT INTO assignments_actual VALUES (?, ?, ?, ?, ?, ?, ?)",
        actual_assignments,
    )

    # コスト実績（4月分のみ）
    actual_budget = [
        ("P001", "2026-04", 800000, 280000, 150000, "sap", None),
    ]
    conn.executemany(
        "INSERT INTO budget_actual VALUES (?, ?, ?, ?, ?, ?, ?)",
        actual_budget,
    )

    # 進捗（4月分のみ）
    progress_rows = [
        ("P001", "2026-04", 8, "要件定義進行中"),
    ]
    conn.executemany(
        "INSERT INTO progress VALUES (?, ?, ?, ?)",
        progress_rows,
    )

    conn.commit()
    print("Sample data seeded successfully.")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        seed(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

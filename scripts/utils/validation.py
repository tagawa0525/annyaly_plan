"""アサイン整合性チェック - ロジック"""

import sqlite3


def check_allocation_exceeded(
    conn: sqlite3.Connection, year_month: str
) -> list[dict]:
    """#1 個人月別アロケーション超過 (SUM(allocation) > 1.0)"""
    issues = []
    rows = conn.execute(
        """
        SELECT
            m.id,
            m.name,
            SUM(ap.allocation) AS total_allocation
        FROM members m
        LEFT JOIN assignments_plan ap
            ON m.id = ap.member_id AND ap.year_month = ?
        GROUP BY m.id, m.name
        HAVING SUM(ap.allocation) > 1.0
    """,
        (year_month,),
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "警告",
                "type": "個人月別アロケーション超過",
                "message": f"{r['name']} ({r['id']}): 合計 {r['total_allocation']:.1f}（1.0超過）",
                "year_month": year_month,
            }
        )

    return issues


def check_dispatch_outside_contract(conn: sqlite3.Connection) -> list[dict]:
    """#2 派遣の契約期間外アサイン"""
    issues = []
    rows = conn.execute(
        """
        SELECT DISTINCT
            m.id,
            m.name,
            ap.year_month,
            m.contract_start,
            m.contract_end
        FROM members m
        JOIN assignments_plan ap ON m.id = ap.member_id
        WHERE m.type = 'dispatch'
          AND (
              (
                  date(ap.year_month || '-01', '+1 month', '-1 day') < m.contract_start
                  AND m.contract_start IS NOT NULL
              )
              OR (
                  ap.year_month || '-01' > m.contract_end
                  AND m.contract_end IS NOT NULL
              )
          )
    """
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "警告",
                "type": "派遣の契約期間外アサイン",
                "message": f"{r['name']} ({r['id']}): {r['year_month']}のアサインが契約外"
                f"（契約: {r['contract_start']}～{r['contract_end']}）",
                "year_month": r["year_month"],
            }
        )

    return issues


def check_assignment_to_closed_project(conn: sqlite3.Connection) -> list[dict]:
    """#3 終了案件へのアサイン"""
    issues = []
    rows = conn.execute(
        """
        SELECT
            p.id,
            p.name,
            ap.year_month,
            p.status
        FROM projects p
        JOIN assignments_plan ap ON p.id = ap.project_id
        WHERE p.status IN ('completed', 'cancelled')
    """
    ).fetchall()

    for row in rows:
        r = dict(row)
        status_label = "完了" if r["status"] == "completed" else "キャンセル"
        issues.append(
            {
                "level": "警告",
                "type": "終了案件へのアサイン",
                "message": f"{r['name']} ({r['id']}): {r['year_month']}にアサイン（{status_label}案件）",
                "year_month": r["year_month"],
            }
        )

    return issues


def check_unassigned_active_project(
    conn: sqlite3.Connection, year_month: str
) -> list[dict]:
    """#4 未アサイン案件 (in_progress/planned で対象月のアサインなし)"""
    issues = []

    rows = conn.execute(
        """
        SELECT
            p.id,
            p.name,
            p.status
        FROM projects p
        WHERE p.status IN ('in_progress', 'planned')
          AND p.actual_work_start <= date(? || '-01', '+1 month', '-1 day')
          AND p.id NOT IN (
              SELECT DISTINCT project_id FROM assignments_plan WHERE year_month = ?
          )
    """,
        (year_month, year_month),
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "注意",
                "type": "未アサイン案件",
                "message": f"{r['name']} ({r['id']}): {year_month}にアサイン者なし",
                "year_month": year_month,
            }
        )

    return issues


def check_pto_exceeded(conn: sqlite3.Connection) -> list[dict]:
    """#5 有給超過 (planned_pto_days > working_days)"""
    issues = []
    rows = conn.execute(
        """
        SELECT
            mc.member_id,
            m.name,
            mc.year_month,
            mc.planned_pto_days,
            cal.working_days
        FROM member_capacity mc
        JOIN members m ON mc.member_id = m.id
        JOIN monthly_calendar cal ON mc.year_month = cal.year_month
        WHERE mc.planned_pto_days > cal.working_days
    """
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "警告",
                "type": "有給超過",
                "message": f"{r['name']} ({r['member_id']}): {r['year_month']} PTO {r['planned_pto_days']}日"
                f"（営業日 {r['working_days']}日超過）",
                "year_month": r["year_month"],
            }
        )

    return issues


def check_missing_capacity(conn: sqlite3.Connection) -> list[dict]:
    """#6 キャパシティ未定義 (active members with no capacity for given month)"""
    issues = []
    rows = conn.execute(
        """
        WITH months AS (
            SELECT DISTINCT year_month FROM assignments_plan
            UNION
            SELECT DISTINCT year_month FROM member_capacity
        )
        SELECT
            m.id,
            m.name,
            months.year_month
        FROM months
        JOIN members m
            ON (
                m.type = 'internal'
                OR (
                    m.type = 'dispatch'
                    AND m.contract_start <= date(months.year_month || '-01', '+1 month', '-1 day')
                    AND (
                        m.contract_end IS NULL
                        OR m.contract_end >= months.year_month || '-01'
                    )
                )
            )
        LEFT JOIN member_capacity mc
            ON mc.member_id = m.id
           AND mc.year_month = months.year_month
        WHERE mc.member_id IS NULL
        ORDER BY months.year_month, m.id
    """
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "注意",
                "type": "キャパシティ未定義",
                "message": f"{r['name']} ({r['id']}): {r['year_month']}の capacity が未定義",
                "year_month": r["year_month"],
            }
        )

    return issues


def check_missing_calendar(conn: sqlite3.Connection) -> list[dict]:
    """#7 カレンダー未定義 (year_month in assignments_plan but not in calendar)"""
    issues = []
    rows = conn.execute(
        """
        SELECT DISTINCT ap.year_month
        FROM assignments_plan ap
        WHERE ap.year_month NOT IN (
            SELECT year_month FROM monthly_calendar
        )
    """
    ).fetchall()

    for row in rows:
        r = dict(row)
        issues.append(
            {
                "level": "警告",
                "type": "カレンダー未定義",
                "message": f"{r['year_month']}: 営業カレンダーが未登録",
                "year_month": r["year_month"],
            }
        )

    return issues


def run_all_validations(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """全チェックを実行"""
    all_issues = []

    # Year-month specific checks
    all_issues.extend(check_allocation_exceeded(conn, year_month))
    all_issues.extend(check_unassigned_active_project(conn, year_month))

    # Global checks (no year_month parameter)
    all_issues.extend(check_dispatch_outside_contract(conn))
    all_issues.extend(check_assignment_to_closed_project(conn))
    all_issues.extend(check_pto_exceeded(conn))
    all_issues.extend(check_missing_capacity(conn))
    all_issues.extend(check_missing_calendar(conn))

    return all_issues

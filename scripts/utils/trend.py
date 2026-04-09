"""月次トレンド分析ロジック"""

import sqlite3

from utils.kpi import dept_utilization, budget_burn, progress_gap


def _month_range(start_month: str, end_month: str) -> list[str]:
    """YYYY-MM 形式の月リストを生成"""
    months = []
    y, m = map(int, start_month.split("-"))
    ey, em = map(int, end_month.split("-"))
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def utilization_trend(
    conn: sqlite3.Connection, start_month: str, end_month: str
) -> list[dict]:
    """稼働率トレンド: 各月の部署平均稼働率を計算

    dept_utilization は実績データがあれば実績を優先するため、
    返す rate は計画/実績の混合値。

    Returns: [{year_month, rate}, ...]
    """
    results = []
    for ym in _month_range(start_month, end_month):
        rate = dept_utilization(conn, ym)
        results.append(
            {
                "year_month": ym,
                "rate": rate,
            }
        )
    return results


def budget_trend(
    conn: sqlite3.Connection, start_month: str, end_month: str
) -> list[dict]:
    """予算消化トレンド: 各月までの累積予算消化を計算

    Returns: [{year_month, planned_cumulative, actual_cumulative, burn_rate}, ...]
    """
    results = []
    for ym in _month_range(start_month, end_month):
        # 計画累積: budget_plan のその月までの合計
        planned_row = conn.execute(
            """
            SELECT COALESCE(SUM(
                planned_labor_cost + planned_outsource_cost + planned_expense
            ), 0) AS total
            FROM budget_plan
            WHERE year_month <= ?
        """,
            (ym,),
        ).fetchone()
        planned_cumulative = dict(planned_row)["total"]

        # 実績累積: budget_burn with year_month
        burns = budget_burn(conn, year_month=ym)
        actual_cumulative = sum(b["actual_total"] for b in burns)
        budget_total = sum(b["budget_total"] for b in burns)

        burn_rate = (
            round(actual_cumulative / budget_total, 3) if budget_total > 0 else 0
        )

        results.append(
            {
                "year_month": ym,
                "planned_cumulative": planned_cumulative,
                "actual_cumulative": actual_cumulative,
                "burn_rate": burn_rate,
            }
        )
    return results


def progress_trend(
    conn: sqlite3.Connection, start_month: str, end_month: str
) -> list[dict]:
    """進捗トレンド: 各案件の月別進捗率

    Returns: [{project_id, project_name, months: {ym: pct, ...}}, ...]
    """
    months = _month_range(start_month, end_month)

    # Get all active projects
    projects = conn.execute(
        """
        SELECT id, name FROM projects
        WHERE status IN ('in_progress', 'planned')
        ORDER BY id
    """
    ).fetchall()

    results = []
    for proj in projects:
        p = dict(proj)
        month_data = {}
        for ym in months:
            row = conn.execute(
                """
                SELECT overall_completion_pct
                FROM progress
                WHERE project_id = ? AND year_month = ?
            """,
                (p["id"], ym),
            ).fetchone()
            if row:
                month_data[ym] = dict(row)["overall_completion_pct"]
            else:
                month_data[ym] = None

        # Only include if there's at least one non-None value
        if any(v is not None for v in month_data.values()):
            results.append(
                {
                    "project_id": p["id"],
                    "project_name": p["name"],
                    "months": month_data,
                }
            )

    return results

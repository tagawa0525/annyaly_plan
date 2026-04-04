"""KPI計算ロジック"""

import sqlite3


def utilization_by_member(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """個人別稼働率（実効キャパシティベース）

    計画ベース: assignments_plan を使用
    実績がある月: assignments_actual を優先
    """
    rows = conn.execute(
        """
        WITH planned AS (
            SELECT member_id, SUM(allocation) AS total_allocation
            FROM assignments_plan
            WHERE year_month = ?
            GROUP BY member_id
        ),
        actual AS (
            SELECT member_id, SUM(allocation) AS total_allocation
            FROM v_assignments_actual
            WHERE year_month = ?
            GROUP BY member_id
        )
        SELECT
            m.id,
            m.name,
            m.type,
            COALESCE(a.total_allocation, p.total_allocation, 0) AS total_allocation,
            COALESCE(vc.effective_capacity, m.max_capacity, 0) AS effective_capacity,
            CASE
                WHEN COALESCE(vc.effective_capacity, m.max_capacity, 0) <= 0 THEN 0.0
                ELSE ROUND(
                    COALESCE(a.total_allocation, p.total_allocation, 0)
                    / COALESCE(vc.effective_capacity, m.max_capacity, 0),
                    3
                )
            END AS utilization_rate,
            CASE
                WHEN a.total_allocation IS NOT NULL THEN 'actual'
                WHEN p.total_allocation IS NOT NULL THEN 'plan'
                ELSE 'none'
            END AS data_source
        FROM members m
        LEFT JOIN planned p ON m.id = p.member_id
        LEFT JOIN actual a ON m.id = a.member_id
        LEFT JOIN v_effective_capacity vc ON m.id = vc.member_id AND vc.year_month = ?
        ORDER BY utilization_rate DESC
    """,
        (year_month, year_month, year_month),
    ).fetchall()
    return [dict(r) for r in rows]


def dept_utilization(conn: sqlite3.Connection, year_month: str) -> float:
    """部署全体の平均稼働率"""
    members = utilization_by_member(conn, year_month)
    if not members:
        return 0.0
    rates = [
        m["utilization_rate"]
        for m in members
        if m["total_allocation"] > 0 or m["data_source"] != "none"
    ]
    return round(sum(rates) / len(rates), 3) if rates else 0.0


def budget_burn(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    """予算消化率（区分別）

    累計実績 / 予算総額 を区分別に計算。
    """
    where = "WHERE pb.project_id = ?" if project_id else ""
    params: tuple = (project_id,) if project_id else ()

    rows = conn.execute(
        f"""
        SELECT
            p.id AS project_id,
            p.name AS project_name,
            pb.labor_cost AS budget_labor,
            pb.outsource_cost AS budget_outsource,
            pb.expense AS budget_expense,
            pb.total AS budget_total,
            COALESCE(ba.sum_labor, 0) AS actual_labor,
            COALESCE(ba.sum_outsource, 0) AS actual_outsource,
            COALESCE(ba.sum_expense, 0) AS actual_expense,
            COALESCE(ba.sum_labor, 0) + COALESCE(ba.sum_outsource, 0) + COALESCE(ba.sum_expense, 0) AS actual_total,
            CASE WHEN pb.labor_cost > 0
                THEN ROUND(CAST(COALESCE(ba.sum_labor, 0) AS REAL) / pb.labor_cost, 3)
                ELSE 0 END AS burn_rate_labor,
            CASE WHEN pb.outsource_cost > 0
                THEN ROUND(CAST(COALESCE(ba.sum_outsource, 0) AS REAL) / pb.outsource_cost, 3)
                ELSE 0 END AS burn_rate_outsource,
            CASE WHEN pb.expense > 0
                THEN ROUND(CAST(COALESCE(ba.sum_expense, 0) AS REAL) / pb.expense, 3)
                ELSE 0 END AS burn_rate_expense,
            CASE WHEN pb.total > 0
                THEN ROUND(CAST(COALESCE(ba.sum_labor, 0) + COALESCE(ba.sum_outsource, 0) + COALESCE(ba.sum_expense, 0) AS REAL) / pb.total, 3)
                ELSE 0 END AS burn_rate_total
        FROM projects p
        JOIN project_budgets pb ON p.id = pb.project_id
        LEFT JOIN (
            SELECT project_id,
                SUM(actual_labor_cost) AS sum_labor,
                SUM(actual_outsource_cost) AS sum_outsource,
                SUM(actual_expense) AS sum_expense
            FROM budget_actual
            GROUP BY project_id
        ) ba ON p.id = ba.project_id
        {where}
        ORDER BY burn_rate_total DESC
    """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def progress_gap(conn: sqlite3.Connection, year_month: str) -> list[dict]:
    """進捗乖離の計算

    時間按分の期待完了率 vs 実際の完了率。
    契約遅延案件は actual_work_start を基準に計算。
    """
    rows = conn.execute(
        """
        SELECT
            p.id AS project_id,
            p.name AS project_name,
            p.actual_work_start,
            p.end_date,
            p.contract_status,
            pr.overall_completion_pct,
            -- 実質経過率
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(? || '-01') - julianday(p.actual_work_start) AS REAL)
                    / (julianday(p.end_date) - julianday(p.actual_work_start)),
                    3
                )
            END AS elapsed_rate,
            -- 期待完了率
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(? || '-01') - julianday(p.actual_work_start) AS REAL)
                    / (julianday(p.end_date) - julianday(p.actual_work_start)) * 100,
                    1
                )
            END AS expected_completion_pct,
            -- 乖離
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(? || '-01') - julianday(p.actual_work_start) AS REAL)
                    / (julianday(p.end_date) - julianday(p.actual_work_start)) * 100
                    - pr.overall_completion_pct,
                    1
                )
            END AS gap
        FROM projects p
        LEFT JOIN progress pr ON p.id = pr.project_id AND pr.year_month = ?
        WHERE p.status IN ('in_progress', 'planned')
          AND p.actual_work_start <= date(? || '-01', '+1 month', '-1 day')
        ORDER BY gap DESC
    """,
        (year_month, year_month, year_month, year_month, year_month),
    ).fetchall()
    return [dict(r) for r in rows]


def compression_ratio(conn: sqlite3.Connection) -> list[dict]:
    """契約遅延案件の圧縮率"""
    rows = conn.execute("""
        SELECT
            id AS project_id,
            name AS project_name,
            original_work_start,
            actual_work_start,
            end_date,
            CASE
                WHEN (julianday(end_date) - julianday(actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    (julianday(end_date) - julianday(original_work_start))
                    / (julianday(end_date) - julianday(actual_work_start)),
                    2
                )
            END AS ratio,
            delay_note
        FROM projects
        WHERE contract_status = 'delayed'
        ORDER BY ratio DESC
    """).fetchall()
    return [dict(r) for r in rows]


def revenue_forecast(conn: sqlite3.Connection, fiscal_year: int = 2026) -> dict:
    """売上着地予測"""
    row = conn.execute(
        """
        SELECT
            fy.revenue_target,
            COALESCE(SUM(bp.planned_revenue), 0) AS total_planned_revenue,
            ROUND(CAST(COALESCE(SUM(bp.planned_revenue), 0) AS REAL) / fy.revenue_target, 3) AS achievement_rate
        FROM fiscal_year fy
        LEFT JOIN budget_plan bp ON 1=1
        WHERE fy.fiscal_year = ?
    """,
        (fiscal_year,),
    ).fetchone()
    return dict(row) if row else {}

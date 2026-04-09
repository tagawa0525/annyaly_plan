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


def budget_burn(
    conn: sqlite3.Connection,
    project_id: str | None = None,
    year_month: str | None = None,
) -> list[dict]:
    """予算消化率（区分別）

    累計実績 / 予算総額 を区分別に計算。
    year_month 指定時はその月までの累積、None なら全期間累積。
    """
    where_clauses = []
    params: list = []

    ba_conditions: list[str] = []
    ba_params: list = []

    if project_id:
        where_clauses.append("pb.project_id = ?")
        params.append(project_id)
        ba_conditions.append("project_id = ?")
        ba_params.append(project_id)

    if year_month:
        ba_conditions.append("year_month <= ?")
        ba_params.append(year_month)

    ba_where = ("WHERE " + " AND ".join(ba_conditions)) if ba_conditions else ""
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

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
            {ba_where}
            GROUP BY project_id
        ) ba ON p.id = ba.project_id
        {where}
        ORDER BY burn_rate_total DESC
    """,
        ba_params + params,
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
            -- 実質経過率（月末基準）
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(date(? || '-01', '+1 month', '-1 day')) - julianday(p.actual_work_start) AS REAL)
                    / (julianday(p.end_date) - julianday(p.actual_work_start)),
                    3
                )
            END AS elapsed_rate,
            -- 期待完了率（月末基準）
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(date(? || '-01', '+1 month', '-1 day')) - julianday(p.actual_work_start) AS REAL)
                    / (julianday(p.end_date) - julianday(p.actual_work_start)) * 100,
                    1
                )
            END AS expected_completion_pct,
            -- 乖離
            CASE
                WHEN (julianday(p.end_date) - julianday(p.actual_work_start)) <= 0 THEN NULL
                ELSE ROUND(
                    CAST(julianday(date(? || '-01', '+1 month', '-1 day')) - julianday(p.actual_work_start) AS REAL)
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
            CASE
                WHEN fy.revenue_target <= 0 THEN NULL
                ELSE ROUND(CAST(COALESCE(SUM(bp.planned_revenue), 0) AS REAL) / fy.revenue_target, 3)
            END AS achievement_rate
        FROM fiscal_year fy
        LEFT JOIN budget_plan bp
            ON bp.year_month >= substr(fy.period_start, 1, 7)
            AND bp.year_month <= substr(fy.period_end, 1, 7)
        WHERE fy.fiscal_year = ?
    """,
        (fiscal_year,),
    ).fetchone()
    return dict(row) if row else {}


# シナリオ別の重み定義
SCENARIOS = {
    "optimistic": {"signed": 1.0, "planned": 1.0, "delayed": 0.8},
    "standard": {"signed": 1.0, "planned": 0.7, "delayed": 0.5},
    "pessimistic": {"signed": 1.0, "planned": 0.4, "delayed": 0.2},
}


def revenue_forecast_weighted(
    conn: sqlite3.Connection, fiscal_year: int = 2026
) -> dict:
    """確度別売上予測（3シナリオ）

    契約状態（signed/planned/delayed）に応じた重み付けで
    楽観・標準・悲観の3シナリオを算出。
    """
    # 売上目標
    fy_row = conn.execute(
        "SELECT revenue_target, period_start, period_end FROM fiscal_year WHERE fiscal_year = ?",
        (fiscal_year,),
    ).fetchone()
    if not fy_row:
        return {}
    fy = dict(fy_row)
    revenue_target = fy["revenue_target"]
    period_start = fy["period_start"][:7]
    period_end = fy["period_end"][:7]

    # 契約状態別の集計
    rows = conn.execute(
        """
        SELECT
            p.contract_status,
            COUNT(DISTINCT p.id) AS project_count,
            COALESCE(SUM(bp.planned_revenue), 0) AS planned_revenue
        FROM projects p
        LEFT JOIN budget_plan bp
            ON bp.project_id = p.id
            AND bp.year_month >= ?
            AND bp.year_month <= ?
        WHERE p.status NOT IN ('cancelled')
        GROUP BY p.contract_status
        ORDER BY p.contract_status
    """,
        (period_start, period_end),
    ).fetchall()
    by_status = [dict(r) for r in rows]

    # 状態別の売上をdictに変換
    revenue_by_status = {s["contract_status"]: s["planned_revenue"] for s in by_status}

    # シナリオ別予測
    scenarios = {}
    for name, weights in SCENARIOS.items():
        forecast = 0
        for status, weight in weights.items():
            forecast += int(round(revenue_by_status.get(status, 0) * weight))
        achievement = (
            round(forecast / revenue_target, 3) if revenue_target > 0 else None
        )
        scenarios[name] = {
            "forecast_revenue": forecast,
            "achievement_rate": achievement,
        }

    return {
        "revenue_target": revenue_target,
        "by_status": by_status,
        "scenarios": scenarios,
    }
